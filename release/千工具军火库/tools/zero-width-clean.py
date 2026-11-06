#!/usr/bin/env python3
"""zero-width-clean.py — 零宽/隐形字符清理工具。

清除文本中的零宽空格、零宽连接符、软连字符、方向标记等隐形字符，
可用 --list 先列出每个隐形字符的位置（1-based）、码点、名称与上下文，
再输出清理后的干净文本。

覆盖的字符：
  U+200B ZERO WIDTH SPACE        零宽空格
  U+200C ZERO WIDTH NON-JOINER   零宽不连字
  U+200D ZERO WIDTH JOINER       零宽连接符
  U+00AD SOFT HYPHEN             软连字符
  U+2060 WORD JOINER             文字连接符
  U+FEFF ZERO WIDTH NO-BREAK SPACE (BOM)
  U+200E/U+200F LRM/RLM          方向标记
  U+2061..U+2064                 隐形运算符（函数应用等）
  U+180E MONGOLIAN VOWEL SEPARATOR

示例命令：
  python zero-width-clean.py -i input.txt -o clean.txt
  cat suspicious.txt | python zero-width-clean.py --list
  python zero-width-clean.py --text "a​b­c" --list --replace ""
"""

import argparse
import sys

INVISIBLE = {
    "\u200b": "ZERO WIDTH SPACE",
    "\u200c": "ZERO WIDTH NON-JOINER",
    "\u200d": "ZERO WIDTH JOINER",
    "\u00ad": "SOFT HYPHEN",
    "\u2060": "WORD JOINER",
    "\ufeff": "ZERO WIDTH NO-BREAK SPACE (BOM)",
    "\u200e": "LEFT-TO-RIGHT MARK",
    "\u200f": "RIGHT-TO-LEFT MARK",
    "\u2061": "FUNCTION APPLICATION",
    "\u2062": "INVISIBLE TIMES",
    "\u2063": "INVISIBLE SEPARATOR",
    "\u2064": "INVISIBLE PLUS",
    "\u180e": "MONGOLIAN VOWEL SEPARATOR",
}


def find(text: str):
    """返回 [(index0, char, name)]。"""
    return [(i, ch, INVISIBLE[ch]) for i, ch in enumerate(text) if ch in INVISIBLE]


def context(text: str, i: int, width: int = 8) -> str:
    lo, hi = max(0, i - width), min(len(text), i + width + 1)
    seg = text[lo:hi].replace("\n", "\\n")
    return ("…" if lo > 0 else "") + seg + ("…" if hi < len(text) else "")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="清除零宽空格、零宽连接符、软连字符等隐形字符。")
    ap.add_argument("-i", "--input", help="输入文件（缺省读 stdin）")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout）")
    ap.add_argument("--text", help="直接指定待处理文本")
    ap.add_argument("--list", action="store_true",
                    help="先在 stderr 列出所有隐形字符位置")
    ap.add_argument("--replace", default="",
                    help="替换成的内容（缺省为空串，即删除）")
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

    hits = find(data)
    if args.list:
        if not hits:
            sys.stderr.write("[zero-width-clean] 未发现隐形字符。\n")
        for i, ch, name in hits:
            sys.stderr.write("[zero-width-clean] 位置 %d  U+%04X %s  上下文: %r\n"
                             % (i + 1, ord(ch), name, context(data, i)))
    clean = "".join(ch if ch not in INVISIBLE else args.replace for ch in data)
    sys.stderr.write("[zero-width-clean] %d 字符 -> %d 字符，清除/替换 %d 处。\n"
                     % (len(data), len(clean), len(hits)))

    if args.output:
        with open(args.output, "w", encoding=args.encoding, newline="") as f:
            f.write(clean)
    else:
        sys.stdout.write(clean)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
