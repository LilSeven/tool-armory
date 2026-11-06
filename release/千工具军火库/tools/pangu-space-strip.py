# -*- coding: utf-8 -*-
"""中西文空格去除（pangu-space-strip）

用途：
    反向去除中西文之间的空格，适配出版物紧排风格（如「使用Python编写」）。
    默认去除「汉字/中文标点」与「英文字母/数字」之间的空格（双向）；
    --han-only 模式只去除汉字与汉字之间的空格（含全角空格、不间断空格）。

示例命令：
    python pangu-space-strip.py input.txt                    # 处理文件，输出到 stdout
    python pangu-space-strip.py input.txt -o out.txt         # 输出到文件
    python pangu-space-strip.py --han-only input.txt         # 仅去除汉字之间的空格
    python pangu-space-strip.py --in-place input.txt         # 原地覆写
    cat input.txt | python pangu-space-strip.py              # 从 stdin 读入
"""
import argparse
import re
import sys

# 汉字（含扩展 A 与兼容区）
HAN = '\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
# 「中文侧」：汉字 + 常用中文标点（作为空格判定边界）
CJK_SIDE = ('[' + HAN + '，。！？；：、…—～·（）《》〈〉“”‘’「」『』【】]'
            )
# 空白类：半角空格、不间断空格、全角空格、窄空格
SP = '[ \u00a0\u2009\u3000]+'
WEST = 'A-Za-z0-9'


def strip_mixed(text: str) -> str:
    """去除中文侧与西文（字母/数字）之间的空格，双向。"""
    text = re.sub('(' + CJK_SIDE + ')(' + SP + ')([' + WEST + '])', r'\1\3', text)
    text = re.sub('([' + WEST + '])(' + SP + ')(' + CJK_SIDE + ')', r'\1\3', text)
    return text


def strip_han(text: str) -> str:
    """仅去除汉字与汉字之间的空格。"""
    return re.sub('([' + HAN + '])(' + SP + ')([' + HAN + '])', r'\1\3', text)


def process(text: str, han_only: bool = False) -> str:
    return strip_han(text) if han_only else strip_mixed(text)


def main() -> int:
    ap = argparse.ArgumentParser(
        description='中西文空格去除：适配出版物紧排风格，支持仅去汉字间空格')
    ap.add_argument('input', nargs='?', help='输入文件（缺省读 stdin）')
    ap.add_argument('-o', '--output', help='输出文件（缺省写 stdout）')
    ap.add_argument('--han-only', action='store_true', help='仅去除汉字之间的空格')
    ap.add_argument('--in-place', action='store_true', help='原地覆写输入文件')
    args = ap.parse_args()

    try:
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', newline='')
    except Exception:
        pass

    if args.input:
        with open(args.input, 'r', encoding='utf-8', errors='replace',
                  newline='') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = process(text, han_only=args.han_only)

    if args.in_place and args.input:
        with open(args.input, 'w', encoding='utf-8', newline='') as f:
            f.write(result)
    elif args.output:
        with open(args.output, 'w', encoding='utf-8', newline='') as f:
            f.write(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
