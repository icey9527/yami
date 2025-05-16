import re
import sys
from pathlib import Path
import os



def extract_special_text(file_path, ignore_prefixes=None):
    """
    提取文件中特定格式的文本：在"□□□"开头和"■■■"结尾之间的非空行
    
    参数:
        file_path: 文件路径
        ignore_prefixes: 需要忽略的前缀列表
        
    返回:
        (extracted_strings, string_info) 元组
    """
    # 匹配中日文字符的正则表达式
    pattern = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff]')

    ignore_prefixes = ['#F']
    
    extracted_strings = []
    string_info = []
    
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        
    if not lines:
        print(f"警告: 文件 {file_path} 为空。")
        return [], []
    
    in_extraction_zone = False
    i = 0
    total_lines = len(lines)
    
    while i < total_lines:
        line = lines[i].strip()
        
        # 检测开始标记
        if line.startswith("□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□"):
            in_extraction_zone = True
            i += 1
            continue
            
        # 检测结束标记
        elif line.startswith("■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■"):
            in_extraction_zone = False
            i += 1
            continue
            
        # 在提取区域内处理文本
        if in_extraction_zone and line and re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff]').search(line):
            # 检查是否需要忽略
            should_ignore = any(line.startswith(prefix) for prefix in ignore_prefixes)
            
            if not should_ignore:
                extracted_strings.append(line)
                string_info.append(f"{os.path.basename(file_path)} {i+1}")  # 行号从1开始计数
                
        i += 1
    
    return extracted_strings, string_info


def write_to_files(all_lines, line_info):
    """将结果写入 all.txt 和 line.txt"""
    with open('all.txt', 'w', encoding='utf-8') as all_file, \
         open('line.txt', 'w', encoding='utf-8') as line_file:
        for line, info in zip(all_lines, line_info):
            all_file.write(line + '\n')
            line_file.write(info + '\n')

def write_back_to_source(directory):
    """根据 all.txt 和 line.txt 反向写入原文件"""
    try:
        with open('all.txt', 'r', encoding='utf-8') as all_file, \
             open('line.txt', 'r', encoding='utf-8') as line_file:
            all_lines = all_file.read().splitlines()
            line_info = line_file.read().splitlines()
    except FileNotFoundError:
        print("Error: all.txt or line.txt not found. Run extract mode first.")
        return

    # 按文件分组
    file_data = {}
    for content, info in zip(all_lines, line_info):
        file_path, line_num = info.rsplit(' ', 1)
        line_num = int(line_num)
        
        full_path = Path(directory) / file_path
        if full_path not in file_data:
            file_data[full_path] = []
        file_data[full_path].append((line_num, content))
    
    # 更新每个文件
    for file_path, changes in file_data.items():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 应用修改
            for line_num, content in changes:
                if 0 < line_num <= len(lines):
                    lines[line_num-1] = content + '\n'
            
            # 写回文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            print(f"Updated {file_path} with {len(changes)} changes")
        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")

def process_directory(directory, mode):
    all_lines = []
    line_info = []
    
    for path in Path(directory).rglob('*.txt'):
        if path.is_file():
            relative_path = str(path.relative_to(directory))
            lines, info = extract_special_text(path, relative_path)
            all_lines.extend(lines)
            line_info.extend(info)
    
    if mode == '-e':
        write_to_files(all_lines, line_info)
        print(f"Extracted {len(all_lines)} lines to all.txt and line.txt")
    elif mode == '-w':
        write_back_to_source(directory)

def main():
    if len(sys.argv) != 3:
        print("Usage: python script.py [-e|-w] directory")
        print("  -e : Extract text to all.txt and line.txt")
        print("  -w : Write back changes from all.txt to source files")
        sys.exit(1)
    
    mode = sys.argv[1]
    directory = sys.argv[2]
    
    if mode not in ['-e', '-w']:
        print("Invalid mode. Use -e to extract or -w to write back.")
        sys.exit(1)
    
    if not Path(directory).is_dir():
        print(f"Directory not found: {directory}")
        sys.exit(1)
    
    process_directory(directory, mode)

if __name__ == "__main__":
    main()