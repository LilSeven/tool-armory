#!/usr/bin/env python3
"""bidi-clean.py — 双向（Bidi）文本控制字符清除工具。

清除 U+202E（RLO）等 Unicode 双向控制字符。这类字符可让代码/文本在屏幕上
呈现与真实字符顺序相反的视觉效果（Trojan Source、文件名伪装等视觉欺骗），
本工具将其整体删除或替换，并可在 stderr 列出每处位置与码点。

覆盖的字符：
  U+202A LRE  U+202B RLE  U+202C PDF  U+202D LRO  U+202E RLO
  U+2066 LRI  U+2067 RLI  U+2068 FSI  U+2069 PDI
  U+200E LRM  U+200F RLM  U+061C ALM（阿拉伯字母方向标记）

示例命令：
  python bidi-clean.py -i input.txt -o clean.txt
  cat suspicious.txt | python bidi-clean.py --list
  python bidi-clean.py --text "abc‮xzy‬" --list

退出码：0 成功；1 读取失败；2 参数错误。
"""
import argparse
import sys
from collections import Counter

BIDI_CHARS = {
    "\u202a": "LRE (LEFT-TO-RIGHT EMBEDDING)",
    "\u202b": "RLE (RIGHT-TO-LEFT EMBEDDING)",
    "\u202c": "PDF (POP DIRECTIONAL FORMATTING)",
    "\u202d": "LRO (LEFT-TO-RIGHT OVERRIDE)",
    "\u202e": "RLO (RIGHT-TO-LEFT OVERRIDE)",
    "\u2066": "LRI (LEFT-TO-RIGHT ISOLATE)",
    "\u2067": "RLI (RIGHT-TO-LEFT ISOLATE)",
    "\u2068": "FSI (FIRST STRONG ISOLATE)",
    "\u2069": "PDI (POP DIRECTIONAL ISOLATE)",
    "\u200e": "LRM (LEFT-TO-RIGHT MARK)",
    "\u200f": "RLM (RIGHT-TO-LEFT MARK)",
    "\u061c": "ALM (ARABIC LETTER MARK)",
}


def find(text: str):
    """返回 [(index0, char, name)]。"""
    return [(i, ch, BIDI_CHARS[ch]) for i, ch in enumerate(text) if ch in BIDI_CHARS]


def context(text: str, i: int, width: int = 10) -> str:
    lo, hi = max(0, i - width), min(len(text), i + width + 1)
    seg = text[lo:hi].replace("\n", "\\n")
    return ("…" if lo > 0 else "") + seg + ("…" if hi < len(text) else "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="清除 U+202E 等双向文本控制字符，消除文本视觉欺骗隐患")
    ap.add_argument("-i", "--input", help="输入文件（缺省读 stdin）")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout）")
    ap.add_argument("--text", help="直接指定待处理文本")
    ap.add_argument("--list", action="store_true",
                    help="在 stderr 列出每个双向控制字符的位置与码点")
    ap.add_argument("--replace", default="",
                    help="替换成的内容（缺省为空串，即直接删除）")
    ap.add_argument("--encoding", default="utf-8", help="输入/输出编码（缺省 utf-8）")
    args = ap.parse_args(argv)

    try:
        if args.text is not None:
            data = args.text
        elif args.input:
            with open(args.input, "r", encoding=args.encoding, errors="replace",
                      newline="") as f:
                data = f.read()
        else:
            try:
                sys.stdin.reconfigure(encoding=args.encoding, errors="replace",
                                      newline="")
            except Exception:
                pass
            data = sys.stdin.read()
    except OSError as e:
        print(f"错误: 读取失败: {e}", file=sys.stderr)
        return 1

    hits = find(data)
    if args.list:
        if not hits:
            print("[bidi-clean] 未发现双向控制字符。", file=sys.stderr)
        for i, ch, name in hits:
            print("[bidi-clean] 位置 %d  U+%04X %s  上下文: %r"
                  % (i + 1, ord(ch), name, context(data, i)), file=sys.stderr)
    clean = "".join(ch if ch not in BIDI_CHARS else args.replace for ch in data)
    print("[bidi-clean] %d 字符 -> %d 字符，清除/替换 %d 处。"
          % (len(data), len(clean), len(hits)), file=sys.stderr)

    try:
        if args.output:
            with open(args.output, "w", encoding=args.encoding, newline="") as f:
                f.write(clean)
        else:
            sys.stdout.write(clean)
    except OSError as e:
        print(f"错误: 写出失败: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
