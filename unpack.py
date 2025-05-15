import struct
import os
import sys
import argparse
import io # To treat bytearray as a file

# --- Reused from .py.txt and scw.py ---

def ExtractString(data, IdxQ, str_data):
    c_addr = 0
    string_ = []
    for i in range(IdxQ):
        #name = read_string(f, c_addr)
        start = struct.unpack('<I', data[c_addr : c_addr+ 4])[0]
        end = struct.unpack('<I', data[c_addr + 8 : c_addr + 12])[0]
        string = str_data[start:start+end].decode(编码)
        if '\n\n' in string:
            print(string)
        string_.append(string.replace('\x00', ''))
        c_addr += 16

    return string_


def xor_decrypt(data: bytes, key_byte: int = 0xff) -> bytearray:
    decrypted_data = bytearray(data)
    for i in range(len(decrypted_data)):
        decrypted_data[i] ^= (i & key_byte)
    return decrypted_data

class LzDecompressor:
    def __init__(self, input_data: bytes):
        self.input_data = input_data
        self.input_pos = 0
        self.output_buffer = bytearray()
        self.window = bytearray(0x1000)
        self.window_pos = 0xfee
        self.c_bit_buffer = 0

    def decompress(self) -> bytearray:
        self.window = bytearray(0x1000)
        self.window_pos = 0xfee
        self.input_pos = 0
        self.output_buffer = bytearray()
        self.c_bit_buffer = 0

        while True:
            while True:
                self.c_bit_buffer >>= 1
                if (self.c_bit_buffer & 0x100) == 0:
                    if self.input_pos >= len(self.input_data):
                        return self.output_buffer
                    new_byte = self.input_data[self.input_pos]
                    self.input_pos += 1
                    self.c_bit_buffer = (0xff << 8) | new_byte

                is_literal = self.c_bit_buffer & 1

                if is_literal == 0:
                    break

                if self.input_pos >= len(self.input_data):
                    return self.output_buffer

                literal_byte = self.input_data[self.input_pos]
                self.input_pos += 1
                self.output_buffer.append(literal_byte)
                self.window[self.window_pos] = literal_byte
                self.window_pos = (self.window_pos + 1) & 0xfff

            if self.input_pos >= len(self.input_data):
                 return self.output_buffer

            byte1 = self.input_data[self.input_pos]
            if self.input_pos + 1 >= len(self.input_data):
                return self.output_buffer

            byte2 = self.input_data[self.input_pos + 1]
            self.input_pos += 2

            offset = byte1 | ((byte2 & 0xf0) << 4)
            length = (byte2 & 0x0f) + 2

            for iVar4 in range(length + 1):
                byte_to_copy = self.window[(offset + iVar4) & 0xfff]
                self.output_buffer.append(byte_to_copy)
                self.window[self.window_pos] = byte_to_copy
                self.window_pos = (self.window_pos + 1) & 0xfff

# --- Reused and adapted from r.py ---

def read_string_from_bytesio(f_io: io.BytesIO, size: int) -> str:
    """Reads a null-terminated string up to a given size from a BytesIO object."""
    string_bytes = bytearray()
    for _ in range(size):
        char = f_io.read(1)
        if char == b'\x00' or not char:
            break
        string_bytes.extend(char)
    # Consume remaining bytes for the fixed size field
    f_io.read(size - len(string_bytes) - (1 if len(string_bytes) < size else 0)) # Read up to null or size limit
    try:
        return string_bytes.decode('shift-jis').rstrip('\x00') # Try Shift-JIS, remove trailing nulls
    except UnicodeDecodeError:
        try:
             return string_bytes.decode('gbk').rstrip('\x00') # Try GBK
        except UnicodeDecodeError:
             return string_bytes.decode('latin1').rstrip('\x00') # Fallback to latin1


def read_uint32_from_bytesio(f_io: io.BytesIO) -> int:
    """Reads a little-endian unsigned 32-bit integer from a BytesIO object."""
    data = f_io.read(4)
    if len(data) < 4:
        raise EOFError("Not enough data to read uint32")
    return struct.unpack('<I', data)[0]

# --- Constants ---

PAK_HEADER_SIZE = 0x1C
FILE_ENTRY_SIZE = 0x28 # Size of each entry in the decompressed index
FILE_HEADER_SIZE = 0xC8
MAGIC_NUMBER = 0x3000003
COMPRESSED_FLAG = 0xFFFFFFFF
XOR_KEY = 0xFF

# --- Main Extraction Logic ---

def extract_pak(pak_filepath: str, output_dir: str):
    """
    Extracts files from a pak archive.

    Args:
        pak_filepath: Path to the input pak file.
        output_dir: Directory to save the extracted files.
    """
    if not os.path.exists(pak_filepath):
        print(f"错误：未找到输入文件 '{pak_filepath}'")
        return

    os.makedirs(output_dir, exist_ok=True)

    try:
        with open(pak_filepath, 'rb') as f:
            # 1. 读取 pak 文件主头部
            pak_header = f.read(PAK_HEADER_SIZE)
            if len(pak_header) < PAK_HEADER_SIZE:
                print(f"错误：文件过小，无法读取完整的 pak 主头部。")
                return

            try:
                # pak 主头部结构 (基于之前的分析):
                # 0x10: compressed_index_size (uint32_t)
                # 0x14: num_files (uint32_t)
                # 0x18: data_block_absolute_offset (uint32_t)
                compressed_index_size = struct.unpack('<I', pak_header[0x10:0x14])[0]
                num_files = struct.unpack('<I', pak_header[0x14:0x18])[0]
                data_block_absolute_offset = struct.unpack('<I', pak_header[0x18:0x1C])[0]

            except struct.error as e:
                print(f"错误：解析 pak 主头部失败：{e}")
                return

            print(f"--- Pak 主头部信息 ---")
            print(f"压缩索引表大小 (0x10): {compressed_index_size} 字节")
            print(f"文件数量 (0x14): {num_files}")
            print(f"数据块绝对偏移量 (0x18): 0x{data_block_absolute_offset:X}")
            print("-" * 30)

            # 2. 读取、解密和解压索引表
            compressed_index_start_offset = PAK_HEADER_SIZE
            f.seek(compressed_index_start_offset)
            compressed_index_data = f.read(compressed_index_size)
            if len(compressed_index_data) < compressed_index_size:
                print(f"错误：读取压缩索引表数据时文件提前结束。")
                return

            print(f"读取了 {len(compressed_index_data)} 字节的压缩索引表数据。")

            xor_decrypted_index_data = xor_decrypt(compressed_index_data, XOR_KEY)
            print("索引表 XOR 解密完成。")

            decompressor = LzDecompressor(xor_decrypted_index_data)
            decompressed_index_data = decompressor.decompress()
            print(f"索引表 LZ 解压完成。大小: {len(decompressed_index_data)} 字节。")

            # 3. 解析解压后的索引表
            print("--- 解析索引表 ---")
            index_io = io.BytesIO(decompressed_index_data)
            files_info = []

            for i in range(num_files):
                try:
                    # 索引表条目结构 (基于 r.py 分析):
                    # 0x00 - 0x1F (32 bytes): 文件名 (null 终止)
                    # 0x20 - 0x23 (4 bytes): 文件在数据块中的相对偏移量
                    # 0x24 - 0x27 (4 bytes): 文件未压缩大小

                    filename = read_string_from_bytesio(index_io, 32)
                    file_relative_offset = read_uint32_from_bytesio(index_io)
                    file_uncompressed_size_index = read_uint32_from_bytesio(index_io)

                    files_info.append({
                        'filename': filename,
                        'relative_offset': file_relative_offset,
                        'uncompressed_size_index': file_uncompressed_size_index
                    })
                    # print(f"文件 {i}: '{filename}', 相对偏移: 0x{file_relative_offset:X}, 未压缩大小: {file_uncompressed_size_index}")

                except EOFError:
                    print(f"警告：解析索引表时提前到达文件末尾，可能索引表损坏。已读取 {i} 个文件信息。")
                    break
                except Exception as e:
                    print(f"错误：解析索引表条目 {i} 失败：{e}")
                    # Skip this entry and try the next
                    index_io.seek(index_io.tell() + (FILE_ENTRY_SIZE - (index_io.tell() % FILE_ENTRY_SIZE))) # Attempt to seek to the start of the next entry
                    continue

            print(f"成功解析了 {len(files_info)} 个文件信息。")
            print("--- 提取文件数据 ---")

            # 4. 提取和处理每个文件数据
            for i, file_info in enumerate(files_info):
                filename = file_info['filename']
                relative_offset = file_info['relative_offset']
                uncompressed_size_index = file_info['uncompressed_size_index']

                file_absolute_offset = data_block_absolute_offset + relative_offset
                

                print(f"正在处理文件 {i+1}\{len(files_info)}: '{filename}' (偏移: 0x{file_absolute_offset:X})")

                try:
                    f.seek(file_absolute_offset)
                    file_header = f.read(FILE_HEADER_SIZE)
                    if len(file_header) < FILE_HEADER_SIZE:
                        print(f"警告：文件 '{filename}' 头部过小，无法读取完整的 0x{FILE_HEADER_SIZE:X} 字节头部。跳过。")
                        continue

                    # 文件数据块头部结构 (基于 scw.py 分析):
                    # 0x10: magic_number (0x3000003)
                    # 0x14: compression_flag (-1 for compressed)
                    # 0x18: compressed_size_plus_1
                    # 0x1C: uncompressed_size_header

                    magic_number = struct.unpack('<I', file_header[0x10:0x14])[0]
                    compression_flag = struct.unpack('<I', file_header[0x14:0x18])[0]
                    compressed_size_plus_1 = struct.unpack('<I', file_header[0x18:0x1C])[0]
                    uncompressed_size_final = struct.unpack('<I', file_header[0x1C:0x20])[0]
                    tabel1_IdxQ = struct.unpack('<I', file_header[0x28:0x2c])[0]
                    tabel2_IdxQ = struct.unpack('<I', file_header[0x2c:0x30])[0]
                    tabel3_IdxQ = struct.unpack('<I', file_header[0x30:0x34])[0]
                    opcode_size = struct.unpack('<I', file_header[0x34:0x38])[0]
                    str1_size =  struct.unpack('<I', file_header[0x38:0x3c])[0]
                    str2_size =  struct.unpack('<I', file_header[0x3c:0x40])[0]

                    #if magic_number != MAGIC_NUMBER:
                    #    print(f"警告：文件 '{filename}' 头部魔数无效 (0x{magic_number:X})，期望 0x{MAGIC_NUMBER:X}。跳过。")
                    #    continue




                    is_compressed = (compression_flag == COMPRESSED_FLAG)
                    

                    if is_compressed:
                        data_payload_size = compressed_size_plus_1
                        data_payload_offset = file_absolute_offset + FILE_HEADER_SIZE
                        print(f"  文件 '{filename}' 是压缩的。压缩大小: {data_payload_size} 字节, 期望未压缩大小: {uncompressed_size_final} 字节。")
                    else:
                        data_payload_offset = file_absolute_offset
                        data_payload_size = file_uncompressed_size_index # For uncompressed, payload size is uncompressed size
                        print(f"  文件 '{filename}' 是未压缩的。大小: {data_payload_size} 字节。")

                    
                    f.seek(data_payload_offset)
                    data_payload = f.read(data_payload_size)

                    if len(data_payload) < data_payload_size:
                         print(f"警告：文件 '{filename}' 数据负载过小，期望 {data_payload_size} 字节，实际读取 {len(data_payload)} 字节。可能数据损坏。")
                         # Proceed with partial data, decompression might fail
                         pass # Continue processing with available data

                    processed_data = data_payload

                    if is_compressed and len(data_payload) > 0: # Only process if data was actually read
                        try:
                            xor_decrypted_data = xor_decrypt(data_payload)
                            processed_data = LzDecompressor(xor_decrypted_data).decompress()
                            if len(processed_data) != uncompressed_size_final:
                                print(f"警告：文件 '{filename}' 解压后大小 ({len(processed_data)}) 与期望大小 ({uncompressed_size_final}) 不匹配。")
                        except Exception as de_e:
                            print(f"错误：文件 '{filename}' 解压失败：{de_e}。保存原始（XOR 解密后）数据。")
                            processed_data = xor_decrypted_data # Save XOR decrypted data on decompression failure

                    # Ensure output directory for this file exists (handles subdirectories in filenames)
                    output_filepath = os.path.join(output_dir, filename)
                    os.makedirs(output_filepath, exist_ok=True)

                    if is_compressed:
                        print(f"  已保存到 '{output_filepath}'")

                        tabel1 = tabel1_IdxQ * 4 * 4
                        tabel2 = tabel1 + tabel2_IdxQ * 4 * 4
                        tabel3 = tabel2 + tabel3_IdxQ * 4 * 4
                        opcode = tabel3 + opcode_size
                        str1 = opcode + str1_size
                        str2 = str1 + str2_size
                        
                        if len(processed_data[:tabel1]) > 0:
                            with open(os.path.join(output_filepath, 'table1.bin'), 'wb') as outfile:
                                outfile.write(processed_data[:tabel1])
                        
                        if len(processed_data[tabel2:tabel3]) > 0:
                            with open(os.path.join(output_filepath, 'table3.bin'), 'wb') as outfile:
                                outfile.write(processed_data[tabel2:tabel3])
                        
                        if len(processed_data[tabel3:opcode]) > 0:
                            with open(os.path.join(output_filepath, 'opcode.bin'), 'wb') as outfile:
                                outfile.write(processed_data[tabel3:opcode])

                        if len(processed_data[str1:str2]) > 0:
                            with open(os.path.join(output_filepath, 'str2.bin'), 'wb') as outfile:
                                outfile.write(processed_data[str1:str2])
                        
                        string = ExtractString(processed_data[tabel1:tabel2], tabel2_IdxQ, processed_data[opcode:str1])
                        
                        if len(string) > 0:
                            with open(os.path.join(output_dir, f'{filename}.txt'), 'w', encoding='utf-8') as outfile:
                                outfile.write(f'；；{file_header[0x88:0xc8].decode(编码).replace('\x00', '')}\n')
                                outfile.write(f'；；{tabel2_IdxQ}\n\n')
                                a = 0
                                for str in string:
                                    a +=1
                                    #outfile.write(f'{a}:{str}\n\n')
                                    outfile.write(f'\n■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■\n{str}')
                                    outfile.write(f'\n□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□\n{str}')

                                
                        
                    else:
                        with open(output_filepath, 'wb') as outfile:
                            outfile.write(processed_data)
                        print(f"  已保存到 '{output_filepath}'")

                except Exception as file_e:
                    print(f"错误：处理文件 '{filename}' (偏移: 0x{file_absolute_offset:X}) 时发生错误：{file_e}")
                    continue # Continue with the next file


    except FileNotFoundError:
        print(f"错误：未找到输入文件 '{pak_filepath}'")
    except Exception as e:
        print(f"发生意外错误：{e}")


# --- Command Line Interface ---

if __name__ == "__main__":
    编码 = 'cp932'
    parser = argparse.ArgumentParser(description="从 pak 封包文件中提取并解压文件。")
    parser.add_argument("input_file", help="输入 pak 文件的路径。")
    parser.add_argument("output_dir", help="保存提取文件的输出文件夹路径。")

    args = parser.parse_args()

    input_pak_path = args.input_file
    output_folder_path = args.output_dir

    print(f"开始处理封包文件 '{input_pak_path}'...")
    extract_pak(input_pak_path, output_folder_path)
    print("处理完成")