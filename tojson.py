import re
import json
from collections import OrderedDict

# 定义分隔符（与原始脚本一致）
BLACK_DELIMITER = '■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■'
WHITE_DELIMITER = '□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□□'

def txt_to_dict(filepath):
    """
    将黑白方块分隔的txt文件转换为有序字典
    格式: {原文1: 译文1, 原文2: 译文2, ...}
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    result = OrderedDict()
    
    # 按黑色方块分割大块（每个大块包含原文+白色方块+译文）
    blocks = re.split(re.escape(BLACK_DELIMITER), content)
    
    for block in blocks:
        # 按白色方块分割原文和译文
        parts = re.split(re.escape(WHITE_DELIMITER), block.strip(), 1)
        if len(parts) == 2:
            original = parts[0].strip()
            translated = parts[1].strip()
            if original:  # 忽略空原文
                result[original] = translated
    
    return result

def save_as_json(data, output_path):
    """保存字典为JSON文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="将黑白方块分隔的txt文件转为JSON")
    parser.add_argument('input_file', help='输入文件路径（.txt格式）')
    parser.add_argument('-o', '--output', default='output.json', 
                       help='输出JSON路径（默认: output.json）')
    
    args = parser.parse_args()
    
    if not args.input_file.endswith('.txt'):
        print("错误：请指定.txt文件")
        exit(1)
    
    print(f"正在转换文件: {args.input_file} -> {args.output}")
    try:
        data = txt_to_dict(args.input_file)
        save_as_json(data, args.output)
        print(f"成功转换 {len(data)} 条数据！")
    except Exception as e:
        print(f"转换失败: {e}")