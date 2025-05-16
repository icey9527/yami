import struct
import os
import sys
import re

def xor_encrypt(data: bytes, key_byte: int = 0xff) -> bytearray:
    encrypted_data = bytearray(data)
    for i in range(len(encrypted_data)):
        encrypted_data[i] ^= (i & key_byte)
    return encrypted_data

def compress(data):
    window = bytearray(4096)
    write_pos = 0xfee
    bit_buffer = []
    output = []
    data_buffer = []
    current = 0

    while current < len(data):
        best_offset, best_len = find_best_match(window, write_pos, data, current)
        if best_len >= 3:
            bit_buffer.append(0)
            offset_low = best_offset & 0xff
            offset_high = (best_offset >> 8) & 0x0f
            length_code = (best_len - 3) & 0x0f
            byte1 = offset_low
            byte2 = (offset_high << 4) | length_code
            data_buffer.append(byte1)
            data_buffer.append(byte2)
            for i in range(best_len):
                window[write_pos] = data[current + i]
                write_pos = (write_pos + 1) % 4096
            current += best_len
        else:
            bit_buffer.append(1)
            literal = data[current]
            data_buffer.append(literal)
            window[write_pos] = literal
            write_pos = (write_pos + 1) % 4096
            current += 1

        while len(bit_buffer) >= 8:
            byte = 0
            for i in range(8):
                if i < len(bit_buffer) and bit_buffer[i]:
                    byte |= (1 << i)
            output.append(byte)
            bit_buffer = bit_buffer[8:]
            output.extend(data_buffer)
            data_buffer.clear()

    if bit_buffer:
        while len(bit_buffer) < 8:
            bit_buffer.append(0)
        byte = 0
        for i in range(8):
            if bit_buffer[i]:
                byte |= (1 << i)
        output.append(byte)

    output.extend(data_buffer)

    return bytes(output)

def find_best_match(window, write_pos, data, current):
    max_len = 0
    best_start = 0
    max_possible_len = min(len(data) - current, 18)

    if max_possible_len < 3:
        return (0, 0)

    #for offset in range(1, 4096):
    if len(sys.argv) > 3:
        头 = 4096
        尾 = 0
    else:
        头 = 0
        尾 = 4096        

    for offset in range(头, 尾):
        start = (write_pos - offset) % 4096
        current_len = 0
        while current_len < max_possible_len and current + current_len < len(data):
            window_pos = (start + current_len) % 4096
            if window[window_pos] == data[current + current_len]:
                current_len += 1
            else:
                break
        if current_len > max_len and offset >=8:
            max_len = current_len
            best_start = start
            if max_len == max_possible_len:
                break

    return (best_start, max_len) if max_len >= 3 else (0, 0)

def raed_bin(input, dir = '.'):
    input = os.path.join(dir, input)
    if os.path.exists(input):
        with open(input, 'rb') as f:
            raw_data = f.read()
            f.close()
            return raw_data
    else:
        return bytes() 

def pack_block_compress(table1, table2, table3, opcode, str1, str2, 描述文本):

    描述文本_ = 描述文本.encode(编码, errors='ignore')
    if len(描述文本_) > 0x2C:
        print(f'描述文本过长：{描述文本}')
        sys.exit()
    
    raw_data = table1 + table2 + table3 + opcode + str1 + str2

    compressed_data =  compress(raw_data)
    compressed_data = xor_encrypt(compressed_data)

    header = bytearray(0x1C8)
    header[:6] = b'Scw5.x'
    struct.pack_into('B', header, 0x13, 5)
    struct.pack_into('<I', header, 0x14,  0xFFFFFFFF)
    struct.pack_into('<I', header, 0x18, len(raw_data))    
    struct.pack_into('<I', header, 0x1C, len(compressed_data))
    struct.pack_into('<I', header, 0x20, 1)
    struct.pack_into('<I', header, 0x24, len(table1) // 8)
    struct.pack_into('<I', header, 0x28, len(table2) // 8)
    struct.pack_into('<I', header, 0x2C, len(table3) // 8)
    struct.pack_into('<I', header, 0x30, len(opcode))
    struct.pack_into('<I', header, 0x34, len(str1))
    struct.pack_into('<I', header, 0x38, len(str2))
    header[0xC8 : 0xC8 + len(描述文本_)] = 描述文本_

    return bytes(header) + compressed_data

def create_idx(item):
    if os.path.exists(item):
        with open(item, 'r', encoding='utf-8') as f:
            content = f.read()
            splits = re.split(r'\s*■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■\s*', content)
            new_splits = [splits[0]]
            delimiter = '□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□'
            for split in splits[1:]:
                if delimiter not in split:
                    print(f'{item}——{split}：译文拆分失败！')
                    sys.exit()
                text = split.split(delimiter, 1)[1].strip()
                if text == '':
                    text = '　' #单空格情况实在是匹配不到，所以只能这样了
                    
                new_splits.append(text)        
            f.close()
            
        return new_splits
    else:
        return None

def pack_block_construct(item):
    item_dir = os.path.join(work_dir, item)

    split = create_idx(f'{os.path.join(work_dir, item)}.txt')

    if split is None:
        str1_data = bytes()
        table2_data = bytes()
        描述文本 = item      
    else:
        result = ((m := re.search(r'；；(.*?)\n；；(\d+)', split[0])) and (m.group(1), int(m.group(2))) or None)
        if result is None:
            print(f"{input}：未发现描述文本或文本数！")
            sys.exit()
        描述文本, 文本数 = result
        str_1_idx = split[1:]
        str_1_idx_current = len(str_1_idx)
        
        if 文本数 != str_1_idx_current:
            print(f"{input}：文本数不匹配！\n应为{文本数} ！实则{str_1_idx_current}！")
            sys.exit()
    
        str_dict = {}
        str1_data = bytearray()
        table2_data = bytearray(str_1_idx_current * 8)
        current_address = 0

        for key in str_1_idx:
            if key in str_dict:
                    str_dict[key].append(current_address)
            else:
                    str_dict[key] = [current_address]
            current_address += 8

        for key, addres in str_dict.items():
            string_data = key.encode(编码, errors='ignore') + b'\x00'
            string_len = len(string_data)
            for addr in addres:
                struct.pack_into('<I', table2_data, addr, len(str1_data))
                struct.pack_into('<I', table2_data, addr + 4, string_len)
            str1_data += string_data

    #    现在用的是优化逻辑，注释掉的是原本的构建逻辑
    #    for string in str_1_idx:
    #        string_data = string.encode(编码, errors='ignore') + b'\x00'
    #        
    #        struct.pack_into('<I', table2_data, current_address, len(str1_data))
    #        struct.pack_into('<I', table2_data, current_address + 4, len(string_data))
    #
    #        str1_data += string_data
    #        
    #        current_address += 8

    table1_data = raed_bin('table1.bin', item_dir)
    table3_data = raed_bin('table3.bin', item_dir)
    opcode_data = raed_bin('opcode.bin', item_dir)
    str2_data = raed_bin('str2.bin', item_dir)

    block = pack_block_compress(table1_data, table2_data, table3_data, opcode_data, str1_data, str2_data, 描述文本)

    return block

def pack():
    items =  [d for d in os.listdir(work_dir) if os.path.isdir(os.path.join(work_dir, d))]
    current_address = 0
    list = bytearray(len(items) * 0x68)
    data = bytearray()

    for item in items:

        item_block = pack_block_construct(item)

        item_name = item.encode(编码, errors='ignore')
        list[current_address : current_address + len(item_name)] = item_name
        struct.pack_into('<I', list, current_address + 0x40, len(data))
        struct.pack_into('<I', list, current_address + 0x44, len(item_block))
        struct.pack_into('<I', list, current_address + 0x48, 1)
        struct.pack_into('<I', list, current_address + 0x4C, 1)
        data.extend(item_block)

        print(f'{current_address // 0x68}：{item}')
        current_address += 0x68

    list_compress = compress(list)

    header = bytearray(0x48)
    header[:9] = b'DataPack5'
    header[0x10:0x16] = b'LILITH'
    struct.pack_into('<H', header, 0x30, 1)
    struct.pack_into('<H', header, 0x32, 5)
    struct.pack_into('<I', header, 0x34, len(list_compress))
    struct.pack_into('<I', header, 0x3C, len(items))
    
    struct.pack_into('<I', header, 0x44, len(header) )
    
    header.extend(list_compress)

    struct.pack_into('<I', header, 0x40, len(header))


    header.extend(data)
    
    with open(out_pack, 'wb') as f:
        f.write(header)
        f.close()



if __name__ == "__main__":
    编码 = 'cp932'
    work_dir = sys.argv[1]
    out_pack = sys.argv[2]
    pack()
