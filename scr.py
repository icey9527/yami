import struct
import os
import sys
import argparse
import io # To treat bytearray as a file

# --- Reused from .py.txt and scw.py ---

def ExtractString(data: bytes, IdxQ: int, str_data: bytes) -> list[str]:
    """
    Extracts strings from a data block based on index and string data.

    Args:
        data: The data block containing string index information.
        IdxQ: The number of string entries.
        str_data: The data block containing the actual string data.

    Returns:
        A list of extracted strings.
    """
    strings = []
    c_addr = 0
    for _ in range(IdxQ):
        if c_addr + 12 > len(data):
            print(f"警告: 字符串索引数据不足, 预期至少 {c_addr + 12} 字节, 实际 {len(data)} 字节.")
            break
        # string entry structure: start_offset (I), unknown (I), end_offset (I), unknown (I)
        start = struct.unpack('<I', data[c_addr : c_addr + 4])[0]
        end = struct.unpack('<I', data[c_addr + 8 : c_addr + 12])[0] # This seems to be length based on usage
        
        if start + end > len(str_data):
             print(f"警告: 字符串数据不足, 尝试读取从 {start} 开始的 {end} 字节, 实际数据大小 {len(str_data)} 字节. 跳过此字符串.")
             c_addr += 16
             continue

        string_bytes = str_data[start : start + end]
        try:
            # Attempt decoding with likely encodings, falling back if necessary
            string = string_bytes.decode('cp932').replace('\x00', '')
        except UnicodeDecodeError:
            try:
                string = string_bytes.decode('gbk').replace('\x00', '')
            except UnicodeDecodeError:
                string = string_bytes.decode('latin1').replace('\x00', '') # Fallback

        if '\n\n' in string:
            print(f"发现包含 '\\n\\n' 的字符串: {string[:50]}...") # Print a snippet if it's very long

        strings.append(string)
        c_addr += 16

    return strings


def xor_decrypt(data: bytes, key_byte: int = 0xff) -> bytearray:
    """
    Performs XOR decryption on byte data.

    Args:
        data: The byte data to decrypt.
        key_byte: The byte value to use as the key (default is 0xff).

    Returns:
        A bytearray containing the decrypted data.
    """
    decrypted_data = bytearray(data)
    for i in range(len(decrypted_data)):
        decrypted_data[i] ^= (i & key_byte)
    return decrypted_data

class LzDecompressor:
    """
    Custom LZ decompression class based on reversed logic.
    Handles the specific LZ compression used in the pak files.
    """
    def __init__(self, input_data: bytes):
        self.input_data = input_data
        self.input_pos = 0
        self.output_buffer = bytearray()
        self.window = bytearray(0x1000) # Sliding window of size 0x1000
        self.window_pos = 0xfee       # Current position in the sliding window
        self.c_bit_buffer = 0         # Bit buffer for reading flags

    def decompress(self) -> bytearray:
        """
        Performs the LZ decompression.

        Returns:
            A bytearray containing the decompressed data.
        """
        # Re-initialize state for decompression
        self.window = bytearray(0x1000)
        self.window_pos = 0xfee
        self.input_pos = 0
        self.output_buffer = bytearray()
        self.c_bit_buffer = 0

        while True:
            # Read a bit flag
            self.c_bit_buffer >>= 1
            if (self.c_bit_buffer & 0x100) == 0:
                if self.input_pos >= len(self.input_data):
                    return self.output_buffer # End of input data
                new_byte = self.input_data[self.input_pos]
                self.input_pos += 1
                self.c_bit_buffer = (0xff << 8) | new_byte # Fill bit buffer

            is_literal = self.c_bit_buffer & 1 # Check the flag bit

            if is_literal == 0:
                # It's a match (offset/length pair)
                if self.input_pos + 1 >= len(self.input_data):
                     return self.output_buffer # Not enough data for offset/length
                
                byte1 = self.input_data[self.input_pos]
                byte2 = self.input_data[self.input_pos + 1]
                self.input_pos += 2

                offset = ((byte2 & 0xf0) << 4) | byte1 # 12-bit offset
                length = (byte2 & 0x0f) + 2          # 4-bit length + 2

                # Copy from the sliding window
                copy_offset = offset
                for _ in range(length + 1): # Copy length + 1 bytes
                    byte_to_copy = self.window[(copy_offset) & 0xfff]
                    self.output_buffer.append(byte_to_copy)
                    self.window[self.window_pos] = byte_to_copy
                    self.window_pos = (self.window_pos + 1) & 0xfff
                    copy_offset += 1 # Increment copy offset for the window

            else:
                # It's a literal byte
                if self.input_pos >= len(self.input_data):
                    return self.output_buffer # Not enough data for literal

                literal_byte = self.input_data[self.input_pos]
                self.input_pos += 1
                self.output_buffer.append(literal_byte)
                self.window[self.window_pos] = literal_byte
                self.window_pos = (self.window_pos + 1) & 0xfff


# --- Reused and adapted from r.py ---

def read_string_from_bytesio(f_io: io.BytesIO, size: int) -> str:
    """
    Reads a null-terminated string up to a given size from a BytesIO object.
    Attempts decoding with Shift-JIS, GBK, and Latin-1.

    Args:
        f_io: The BytesIO object to read from.
        size: The maximum number of bytes to read for the string.

    Returns:
        The decoded string, with trailing nulls removed.
    """
    string_bytes = bytearray()
    read_count = 0
    while read_count < size:
        char = f_io.read(1)
        if not char or char == b'\x00':
            break
        string_bytes.extend(char)
        read_count += 1

    # Consume remaining bytes for the fixed size field
    f_io.seek(f_io.tell() + (size - read_count - (1 if read_count < size else 0))) # Adjust seek based on actual read

    try:
        return string_bytes.decode('shift-jis').rstrip('\x00')
    except UnicodeDecodeError:
        try:
             return string_bytes.decode('gbk').rstrip('\x00')
        except UnicodeDecodeError:
             return string_bytes.decode('latin1').rstrip('\x00')


def read_uint32_from_bytesio(f_io: io.BytesIO) -> int:
    """
    Reads a little-endian unsigned 32-bit integer from a BytesIO object.

    Args:
        f_io: The BytesIO object to read from.

    Returns:
        The decoded unsigned 32-bit integer.

    Raises:
        EOFError: If not enough data is available to read a uint32.
    """
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

            # pak 主头部结构:
            # 0x10: compressed_index_size (uint32_t)
            # 0x14: num_files (uint32_t)
            # 0x18: data_block_absolute_offset (uint32_t)
            try:
                compressed_index_size, num_files, data_block_absolute_offset = struct.unpack('<III', pak_header[0x10:0x1C])
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
                print(f"错误：读取压缩索引表数据时文件提前结束。预期 {compressed_index_size} 字节, 实际读取 {len(compressed_index_data)} 字节。")
                return

            print(f"读取了 {len(compressed_index_data)} 字节的压缩索引表数据。")

            xor_decrypted_index_data = xor_decrypt(compressed_index_data, XOR_KEY)
            print("索引表 XOR 解密完成。")

            decompressor = LzDecompressor(xor_decrypted_index_data)
            decompressed_index_data = decompressor.decompress()
            print(f"索引表 LZ 解压完成。大小: {len(decompressed_index_data)} 字节。")

            # 验证解压后的索引表大小
            expected_decompressed_index_size = num_files * FILE_ENTRY_SIZE
            if len(decompressed_index_data) < expected_decompressed_index_size:
                 print(f"警告：解压后的索引表大小 ({len(decompressed_index_data)}) 小于预期大小 ({expected_decompressed_index_size})。可能索引表损坏或文件数量不正确。将尝试解析可用数据。")

            # 3. 解析解压后的索引表
            print("--- 解析索引表 ---")
            index_io = io.BytesIO(decompressed_index_data)
            files_info = []

            for i in range(num_files):
                if index_io.tell() + FILE_ENTRY_SIZE > len(decompressed_index_data):
                    print(f"警告：解析索引表时数据不足，无法读取完整的条目 {i}。已读取 {len(files_info)} 个文件信息。")
                    break # Stop if not enough data for a full entry

                try:
                    # 索引表条目结构:
                    # 0x00 - 0x1F (32 bytes): 文件名 (null 终止)
                    # 0x20 - 0x23 (4 bytes): 文件在数据块中的相对偏移量
                    # 0x24 - 0x27 (4 bytes): 文件未压缩大小 (在索引中)

                    filename = read_string_from_bytesio(index_io, 32)
                    file_relative_offset = read_uint32_from_bytesio(index_io)
                    file_uncompressed_size_index = read_uint32_from_bytesio(index_io)

                    files_info.append({
                        'filename': filename,
                        'relative_offset': file_relative_offset,
                        'uncompressed_size_index': file_uncompressed_size_index
                    })

                except EOFError:
                    print(f"警告：解析索引表条目 {i} 时提前到达数据末尾。已读取 {len(files_info)} 个文件信息。")
                    break
                except Exception as e:
                    print(f"错误：解析索引表条目 {i} 失败：{e}。跳过此条目。")
                    # Attempt to seek past the expected entry size to try the next one
                    index_io.seek(index_io.tell() + (FILE_ENTRY_SIZE - (index_io.tell() % FILE_ENTRY_SIZE)))
                    continue

            print(f"成功解析了 {len(files_info)} 个文件信息。")
            print("--- 提取文件数据 ---")

            # 4. 提取和处理每个文件数据
            for i, file_info in enumerate(files_info):
                filename = file_info['filename']
                relative_offset = file_info['relative_offset']
                uncompressed_size_index = file_info['uncompressed_size_index']

                file_absolute_offset = data_block_absolute_offset + relative_offset
                
                print(f"正在处理文件 {i+1}/{len(files_info)}: '{filename}' (偏移: 0x{file_absolute_offset:X})")

                try:
                    f.seek(file_absolute_offset)
                    file_header = f.read(FILE_HEADER_SIZE)
                    if len(file_header) < FILE_HEADER_SIZE:
                        print(f"警告：文件 '{filename}' 头部过小，无法读取完整的 0x{FILE_HEADER_SIZE:X} 字节头部。跳过。")
                        continue

                    # 文件数据块头部结构:
                    # 0x10: magic_number (0x3000003)
                    # 0x14: compression_flag (-1 for compressed)
                    # 0x18: compressed_size_plus_1 (includes header size if not compressed?)
                    # 0x1C: uncompressed_size_header (uncompressed size from header)
                    # 0x28: tabel1_IdxQ (uint32_t) - Count for table 1
                    # 0x2c: tabel2_IdxQ (uint32_t) - Count for table 2 (string indices)
                    # 0x30: tabel3_IdxQ (uint32_t) - Count for table 3
                    # 0x34: code_size (uint32_t) - Size of code/string data block
                    # 0x38: str1_size (uint32_t) - Size of string data 1 (used by table 2)
                    # 0x3c: str2_size (uint32_t) - Size of string data 2

                    if len(file_header) < 0x40: # Ensure we can read up to str2_size
                         print(f"警告：文件 '{filename}' 头部太短，无法读取完整的元数据。跳过。")
                         continue

                    magic_number = struct.unpack('<I', file_header[0x10:0x14])[0]
                    compression_flag = struct.unpack('<I', file_header[0x14:0x18])[0]
                    compressed_size_plus_1 = struct.unpack('<I', file_header[0x18:0x1C])[0]
                    uncompressed_size_header = struct.unpack('<I', file_header[0x1C:0x20])[0]
                    tabel1_IdxQ = struct.unpack('<I', file_header[0x28:0x2c])[0]
                    tabel2_IdxQ = struct.unpack('<I', file_header[0x2c:0x30])[0]
                    tabel3_IdxQ = struct.unpack('<I', file_header[0x30:0x34])[0]
                    code_size = struct.unpack('<I', file_header[0x34:0x38])[0]
                    str1_size =  struct.unpack('<I', file_header[0x38:0x3c])[0]
                    str2_size =  struct.unpack('<I', file_header[0x3c:0x40])[0]


                    is_compressed = (compression_flag == COMPRESSED_FLAG)
                    
                    data_payload_offset = file_absolute_offset + FILE_HEADER_SIZE
                    if is_compressed:
                        data_payload_size = compressed_size_plus_1
                        print(f"  文件 '{filename}' 是压缩的。压缩大小: {data_payload_size} 字节, 头部未压缩大小: {uncompressed_size_header} 字节, 索引未压缩大小: {uncompressed_size_index} 字节。")
                    else:
                        # For uncompressed files, the payload starts immediately at the file offset
                        # and its size is given by the index uncompressed size.
                        data_payload_offset = file_absolute_offset
                        data_payload_size = uncompressed_size_index
                        print(f"  文件 '{filename}' 是未压缩的。大小: {data_payload_size} 字节。")

                    
                    f.seek(data_payload_offset)
                    data_payload = f.read(data_payload_size)

                    if len(data_payload) < data_payload_size:
                         print(f"警告：文件 '{filename}' 数据负载过小，期望 {data_payload_size} 字节，实际读取 {len(data_payload)} 字节。可能数据损坏。将尝试处理部分数据。")
                         # Continue processing with partial data

                    processed_data = data_payload

                    if is_compressed and len(data_payload) > 0:
                        try:
                            xor_decrypted_data = xor_decrypt(data_payload)
                            processed_data = LzDecompressor(xor_decrypted_data).decompress()

                            # Note: The original script uses uncompressed_size_final from header (0x1C)
                            # for comparison. Let's stick to that for strict adherence.
                            if len(processed_data) != uncompressed_size_header:
                                print(f"警告：文件 '{filename}' 解压后大小 ({len(processed_data)}) 与头部期望大小 ({uncompressed_size_header}) 不匹配。")

                        except Exception as de_e:
                            print(f"错误：文件 '{filename}' 解压失败：{de_e}。保存原始（XOR 解密后）数据。")
                            processed_data = xor_decrypted_data # Save XOR decrypted data on decompression failure

                    # Ensure output directory for this file exists (handles subdirectories in filenames)
                    output_filepath_base = os.path.join(output_dir, filename)
                    os.makedirs(output_filepath_base, exist_ok=True)

                    if is_compressed:
                        # Save extracted components based on header sizes
                        table1_size = tabel1_IdxQ * 4 * 4
                        table2_size = tabel2_IdxQ * 4 * 4 # This is the size of the string index table
                        table3_size = tabel3_IdxQ * 4 * 4

                        current_offset = 0

                        # Extract Table 1
                        if current_offset + table1_size <= len(processed_data):
                            with open(os.path.join(output_filepath_base, 'table1.bin'), 'wb') as outfile:
                                outfile.write(processed_data[current_offset : current_offset + table1_size])
                            current_offset += table1_size
                        else:
                             print(f"警告: 文件 '{filename}' 数据不足以提取 Table 1. 预期 {table1_size}, 实际从 {current_offset} 开始只有 {len(processed_data) - current_offset} 字节.")


                        # Extract Table 2 (String Indices) and Strings
                        table2_data = b""
                        if current_offset + table2_size <= len(processed_data):
                             table2_data = processed_data[current_offset : current_offset + table2_size]
                             # The original script did NOT save table2.bin, only used its data for string extraction.
                             # Sticking to original behavior: do not save table2.bin
                             current_offset += table2_size
                        else:
                             print(f"警告: 文件 '{filename}' 数据不足以提取 Table 2 (字符串索引). 预期 {table2_size}, 实际从 {current_offset} 开始只有 {len(processed_data) - current_offset} 字节.")


                        # Extract Table 3
                        if current_offset + table3_size <= len(processed_data):
                            with open(os.path.join(output_filepath_base, 'table3.bin'), 'wb') as outfile:
                                outfile.write(processed_data[current_offset : current_offset + table3_size])
                            current_offset += table3_size
                        else:
                             print(f"警告: 文件 '{filename}' 数据不足以提取 Table 3. 预期 {table3_size}, 实际从 {current_offset} 开始只有 {len(processed_data) - current_offset} 字节.")


                        # Extract Code/String Data Block
                        code_data = b""
                        if current_offset + code_size <= len(processed_data):
                             code_data = processed_data[current_offset : current_offset + code_size]
                             with open(os.path.join(output_filepath_base, 'code.bin'), 'wb') as outfile:
                                outfile.write(code_data)
                             current_offset += code_size
                        else:
                             print(f"警告: 文件 '{filename}' 数据不足以提取 Code/String Data. 预期 {code_size}, 实际从 {current_offset} 开始只有 {len(processed_data) - current_offset} 字节.")


                        # Extract String Data 1 (used by Table 2)
                        str1_data = b""
                        if current_offset + str1_size <= len(processed_data):
                             str1_data = processed_data[current_offset : current_offset + str1_size]
                             # The original script did NOT save str1.bin, only used its data for string extraction.
                             # Sticking to original behavior: do not save str1.bin
                             current_offset += str1_size
                        else:
                             print(f"警告: 文件 '{filename}' 数据不足以提取 String Data 1. 预期 {str1_size}, 实际从 {current_offset} 开始只有 {len(processed_data) - current_offset} 字节.")


                        # Extract String Data 2
                        if current_offset + str2_size <= len(processed_data):
                            with open(os.path.join(output_filepath_base, 'str2.bin'), 'wb') as outfile:
                                outfile.write(processed_data[current_offset : current_offset + str2_size])
                            current_offset += str2_size
                        else:
                             print(f"警告: 文件 '{filename}' 数据不足以提取 String Data 2. 预期 {str2_size}, 实际从 {current_offset} 开始只有 {len(processed_data) - current_offset} 字节.")

                        # Extract Strings using Table 2 and String Data 1
                        if table2_data and str1_data: # Only attempt if we have the necessary data
                            extracted_strings = ExtractString(table2_data, tabel2_IdxQ, str1_data)
                            output_txt_filepath = os.path.join(output_dir, f'{filename}.txt')
                            try:
                                with open(output_txt_filepath, 'w', encoding='utf-8') as outfile:
                                    outfile.write(f'；；{file_header[0x88:0xc8].decode('cp932').replace('\x00', '')}\n\n\n')
                                    for string in extracted_strings:
                                        outfile.write(f'{string}\n\n')
                                print(f"  已提取字符串到 '{output_txt_filepath}'")
                            except Exception as txt_e:
                                print(f"错误：保存文件 '{output_txt_filepath}' 时发生错误：{txt_e}")
                        elif tabel2_IdxQ > 0:
                             print(f"警告: 文件 '{filename}' 包含字符串索引 ({tabel2_IdxQ} 个), 但缺少 Table 2 数据或 String Data 1, 无法提取字符串.")


                    else:
                        # Save uncompressed file directly
                        output_filepath = os.path.join(output_dir, filename)
                        try:
                            with open(output_filepath, 'wb') as outfile:
                                outfile.write(processed_data)
                            print(f"  已保存到 '{output_filepath}'")
                        except Exception as save_e:
                            print(f"错误：保存文件 '{output_filepath}' 时发生错误：{save_e}")


                except Exception as file_e:
                    print(f"错误：处理文件 '{filename}' (偏移: 0x{file_absolute_offset:X}) 时发生错误：{file_e}")
                    continue # Continue with the next file


    except FileNotFoundError:
        print(f"错误：未找到输入文件 '{pak_filepath}'")
    except Exception as e:
        print(f"发生意外错误：{e}")


# --- Command Line Interface ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 pak 封包文件中提取并解压文件。")
    parser.add_argument("input_file", help="输入 pak 文件的路径。")
    parser.add_argument("output_dir", help="保存提取文件的输出文件夹路径。")

    args = parser.parse_args()

    input_pak_path = args.input_file
    output_folder_path = args.output_dir

    print(f"开始处理封包文件 '{input_pak_path}'...")
    extract_pak(input_pak_path, output_folder_path)
    print("处理完成")