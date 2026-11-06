#!/usr/bin/env python3
"""fullwidth-swap.py — 全角/半角字母数字标点互转工具。

基于 unicodedata 判定字符类别，在全角 ASCII 形式（U+FF01..U+FF5E、
全角空格 U+3000）与半角 ASCII（U+0021..U+007E、空格）之间双向转换；
中日韩文字（CJK 统一表意文字等）一律原样保留，不受影响。

示例命令：
  python fullwidth-swap.py --to-half -i input.txt -o half.txt
  echo "ＡＢＣ１２３：你好，世界！" | python fullwidth-swap.py --to-half
  echo "ABC123: Hello!" | python fullwidth-swap.py --to-full
  python fullwidth-swap.py --to-half --text "Ｈｅｌｌｏ，世界１２３"

说明：
  --to-half  全角 -> 半角（U+FF01..FF5E 减 0xFEE0；U+3000 -> 空格）
  --to-full  半角 -> 全角（U+0021..007E 加 0xFEE0；空格 -> U+3000）
  两个方向都只触碰上述范围，其余字符（含中文、日文假名、emoji）不动。
"""

import argparse
import sys
import unicodedata

FW_OFFSET = 0xFEE0  # 全角 ASCII 区与半角区的固定偏移


def to_half(text: str) -> str:
    out = []
    for ch in text:
        o = ord(ch)
        if ch == "\u3000":                 # 全角空格
            out.append(" ")
        elif 0xFF01 <= o <= 0xFF5E:        # 全角 ！..～
            out.append(chr(o - FW_OFFSET))
        else:                              # 中文等其余字符原样保留
            out.append(ch)
    return "".join(out)


def to_full(text: str) -> str:
    out = []
    for ch in text:
        o = ord(ch)
        if ch == " ":
            out.append("\u3000")
        elif 0x21 <= o <= 0x7E:            # 可打印半角 ASCII
            out.append(chr(o + FW_OFFSET))
        else:
            out.append(ch)
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="全角/半角字母数字标点双向互转，中文不受影响。")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--to-half", action="store_true", help="全角转半角")
    g.add_argument("--to-full", action="store_true", help="半角转全角")
    ap.add_argument("-i", "--input", help="输入文件（缺省读 stdin）")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout）")
    ap.add_argument("--text", help="直接指定待处理文本")
    ap.add_argument("--encoding", default="utf-8",
                    help="输入/输出编码（缺省 utf-8）")
    args = ap.parse_args()

    try:
        sys.stdin.reconfigure(encoding=args.encoding, errors="replace", newline="")
    except Exception:
        pass

    if args.text is not None:
        data = args.text
    elif args.input:
        with open(args.input, "r", encoding=args.encoding, errors="replace") as f:
            data = f.read()
    else:
        data = sys.stdin.read()

    result = to_half(data) if args.to_half else to_full(data)
    conv = sum(1 for a, b in zip(data, result) if a != b)

    sys.stderr.write("[fullwidth-swap] %s：%d 字符，转换 %d 处（CJK 保持不变）。\n"
                     % ("全角->半角" if args.to_half else "半角->全角",
                        len(data), conv))

    if args.output:
        with open(args.output, "w", encoding=args.encoding, newline="") as f:
            f.write(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
