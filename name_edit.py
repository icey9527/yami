import re
import os
import sys
import argparse

# 定义分隔符
BLACK_DELIMITER = '■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■' 
WHITE_DELIMITER = '□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□' 
NAME_PATTERN = re.compile(r'#F(.*?)#F') # 匹配 #F...#F 中的内容
NAMES_FILE = 'names.txt' # 存放所有人名列表和译文的文件

def extract_names(directory):
    """
    从指定目录下的txt文件原文部分提取所有不重复人名，并写入names.txt文件。
    names.txt 使用黑白方块格式，原文和译文部分都只有提取到的名字（不带#F）。
    """
    print(f"正在从文件提取人名到 '{NAMES_FILE}'...")
    all_unique_names = set()

    for root, _, files in os.walk(directory):
        for filename in files:
            # 忽略 names.txt 文件本身
            if filename.endswith('.txt') and filename != NAMES_FILE:
                filepath = os.path.join(root, filename)
                # print(f"处理文件: {filepath}") # 调试用，正式运行时可注释

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # 根据黑色方块分割成块
                    blocks = re.split(BLACK_DELIMITER, content)
                    
                    # 遍历每个块，提取原文中的人名（不带#F）
                    for block in blocks:
                        parts = block.split(WHITE_DELIMITER, 1)
                        if len(parts) == 2:
                            original_text = parts[0]
                            matches = NAME_PATTERN.findall(original_text)
                            for name in matches:
                                all_unique_names.add(name) # 提取到的名字本身，不带#F

                except Exception as e:
                    print(f"处理文件 {filepath} 时出错: {e}")

    # 将提取到的不重复人名写入names.txt文件，使用黑白方块格式
    if all_unique_names:
        try:
            with open(NAMES_FILE, 'w', encoding='utf-8') as f_names:
                sorted_names = sorted(list(all_unique_names)) # 按字母顺序排序后写入
                for i, name in enumerate(sorted_names):
                    # 写入原文部分（只有名字，不带#F）
                    f_names.write(f"{name}\n")
                    # 写入白色分隔符
                    f_names.write(WHITE_DELIMITER + "\n")
                    # 写入译文部分（初始与原文相同，只有名字，不带#F，供用户修改）
                    f_names.write(f"{name}\n")
                    # 如果不是最后一个名字，写入黑色分隔符
                    if i < len(sorted_names) - 1:
                        f_names.write(BLACK_DELIMITER + "\n")
            print(f"提取到 {len(all_unique_names)} 个不重复人名，已写入 '{NAMES_FILE}'")
            print(f"请编辑 '{NAMES_FILE}' 文件中的白色方块下方部分来修改人名译文。")
        except Exception as e:
            print(f"写入 '{NAMES_FILE}' 时出错: {e}")
    else:
         print("未在任何文件的原文中找到人名。")


def write_names(directory):
    """
    读取names.txt文件，建立人名映射，然后根据映射更新其他txt文件的译文部分。
    如果在原文中遇到names.txt中没有映射的人名，则报错停止。
    在写入时自动为译文人名添加#F包裹。
    """
    print(f"正在根据 '{NAMES_FILE}' 更新文件...")
    name_map = {}

    # 检查 names.txt 是否存在
    if not os.path.exists(NAMES_FILE):
        print(f"错误: 未找到人名文件 '{NAMES_FILE}'。请先运行提取模式 (-e)。")
        sys.exit(1) # 报错停止

    # 读取 names.txt 文件，建立人名映射
    try:
        with open(NAMES_FILE, 'r', encoding='utf-8') as f_names:
            names_content = f_names.read()

        name_blocks = re.split(re.escape(BLACK_DELIMITER) , names_content)
        for i, name_block in enumerate(name_blocks):
            parts = name_block.split(WHITE_DELIMITER, 1)  
            if len(parts) != 2:
                print(f"错误: '{NAMES_FILE}' 中第 {i+1} 个人名块格式不正确，无法按白色方块分隔。请检查文件格式。")
                sys.exit(1) # 格式错误，报错停止

            original_name = parts[0].strip() # 获取原文名字（不带#F）
            new_name = parts[1].strip()     # 获取译文名字（不带#F）

            if not original_name:
                 print(f"错误: '{NAMES_FILE}' 中第 {i+1} 个人名块原文部分为空。请检查文件格式。")
                 sys.exit(1) # 格式错误，报错停止

            name_map[original_name] = new_name

        if not name_map:
            print(f"警告: 未从 '{NAMES_FILE}' 中解析到有效的人名映射。")
            # 如果names.txt为空或解析失败，但用户执行写入，可能不是错误，只是没有名字需要替换
            # 但如果后续文件中有名字，而map为空，就会报错，所以这里不sys.exit(1)

    except Exception as e:
        print(f"读取或解析 '{NAMES_FILE}' 时出错: {e}")
        sys.exit(1) # 读取names.txt出错，报错停止

    # 遍历指定目录下的其他txt文件，进行人名替换
    for root, _, files in os.walk(directory):
        for filename in files:
             # 忽略 names.txt 文件本身
            if filename.endswith('.txt') and filename != NAMES_FILE:
                filepath = os.path.join(root, filename)
                # print(f"处理文件进行写入: {filepath}") # 调试用，正式运行时可注释

                try:
                    with open(filepath, 'r', encoding='utf-8') as f_orig:
                        original_content = f_orig.read()

                    # 根据黑色方块分割原文件内容
                    original_blocks = re.split( BLACK_DELIMITER , original_content)
                    new_content_blocks = []
                    # 添加第一个块（文件头），如果存在的话
                    if original_blocks:
                        new_content_blocks.append(original_blocks[0])

                    # 逐块处理并替换译文中的人名
                    # 从第二个块开始遍历
                    for i in range(1, len(original_blocks)):
                        parts = original_blocks[i].split(WHITE_DELIMITER, 1)

                        if len(parts) != 2:
                            # print(f"警告: 文件 '{filepath}' 的块 {i} 分隔失败，保留原块内容。") # 避免过多输出
                            new_content_blocks.append(original_blocks[i])
                            continue

                        original_text = parts[0]
                        
                        translated_text = parts[1]
                        current_translated_text = translated_text # 用于逐步替换

                        # 查找原文部分的所有人名（带#F）
                        original_name_patterns_in_block = NAME_PATTERN.findall(original_text)

                        # 遍历找到的人名，进行替换
                        for original_name_raw in original_name_patterns_in_block: # 提取到的是不带#F的名字
                            if original_name_raw in name_map:
                                new_name_raw = name_map[original_name_raw]
                                # 构建要替换成的新字符串（带#F）
                                new_name_string = f"#F{new_name_raw}#F"

                                # 在译文部分查找第一个 #F...#F 模式并替换
                                # 使用 re.sub 的 count=1 确保只替换第一个匹配项
                                current_translated_text, count = re.subn(NAME_PATTERN, new_name_string, current_translated_text, count=1)

                                if count == 0:
                                     # 如果原文中有名字，但在译文中没有找到#F...#F模式进行替换，说明格式有问题
                                     print(f"错误: 文件 '{filepath}' 的块 {i} 的原文中包含人名 '{original_name_raw}'，但在译文部分未找到 #F...#F 模式进行替换。请检查文件格式。")
                                     sys.exit(1) # 报错停止

                            else:
                                # 如果原文中的人名不在name_map中，则报错停止
                                print(f"错误: 文件 '{filepath}' 的块 {i} 的原文中包含人名 '{original_name_raw}'，但在 '{NAMES_FILE}' 中未找到对应的映射。请将此人名添加到 '{NAMES_FILE}' 并提供译文。")
                                sys.exit(1) # 报错停止

                        # 重构块：原文 + 白色分隔符 + 修改后的译文
                        reconstructed_block = original_text +   WHITE_DELIMITER + current_translated_text
                        new_content_blocks.append(reconstructed_block)

                    # 拼接所有块并写回原文件
                    final_content = ""
                    if new_content_blocks:
                        final_content +=  ( BLACK_DELIMITER ).join(new_content_blocks)


                    with open(filepath, 'w', encoding='utf-8') as f_orig:
                        f_orig.write(final_content)
                    print(f"成功更新文件: {filepath}")

                except Exception as e:
                    print(f"处理文件 {filepath} 时出错: {e}")


def main():
    parser = argparse.ArgumentParser(description="根据黑白方块分隔符提取或写入文本中的人名。")
    parser.add_argument('directory', help='包含txt文件的目录。')
    parser.add_argument('-e', '--extract', action='store_true', help='提取人名并创建names.txt文件。')
    parser.add_argument('-w', '--write', action='store_true', help='根据names.txt文件写入修改后的人名到原文件。')

    args = parser.parse_args()

    if not args.extract and not args.write:
        print("请指定模式：-e (提取) 或 -w (写入)。")
        parser.print_help()
        sys.exit(1)

    if not os.path.isdir(args.directory):
        print(f"错误: 目录不存在: {args.directory}")
        sys.exit(1)

    if args.extract:
        extract_names(args.directory)

    if args.write:
        write_names(args.directory)

if __name__ == "__main__":
    main()