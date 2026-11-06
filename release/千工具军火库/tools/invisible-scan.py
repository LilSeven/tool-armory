#!/usr/bin/env python3
"""不可见字符扫描(invisible-scan)

扫描文本中的零宽与不可见字符:U+200B(U+200B..U+200F)、U+2028/U+2029、
U+202A..U+202E(双向控制)、U+2060..U+206F、U+FEFF(BOM/零宽不换行空格)、
软连字符 U+00AD 等,报告行号、列号、码点与名称。

用法:
  python invisible-scan.py <输入文件> [--fix 输出文件]
  cat in.txt | python invisible-scan.py

示例:
  python invisible-scan.py doc.txt
  python invisible-scan.py doc.txt --fix cleaned.txt   # 同时剥离这些字符
未发现时退出码 0 并提示;--fix 把清除后的文本写出。
"""
import argparse
import sys
import unicodedata

# Windows 控制台/管道默认 GBK,强制 UTF-8
for _s in (sys.stdout, sys.stderr, sys.stdin):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", newline="")

INVISIBLE = {
    0x200B: "ZERO WIDTH SPACE",
    0x200C: "ZERO WIDTH NON-JOINER",
    0x200D: "ZERO WIDTH JOINER",
    0x200E: "LEFT-TO-RIGHT MARK",
    0x200F: "RIGHT-TO-LEFT MARK",
    0x00AD: "SOFT HYPHEN",
    0x2028: "LINE SEPARATOR",
    0x2029: "PARAGRAPH SEPARATOR",
    0x202A: "LEFT-TO-RIGHT EMBEDDING",
    0x202B: "RIGHT-TO-LEFT EMBEDDING",
    0x202C: "POP DIRECTIONAL FORMATTING",
    0x202D: "LEFT-TO-RIGHT OVERRIDE",
    0x202E: "RIGHT-TO-LEFT OVERRIDE",
    0x2060: "WORD JOINER",
    0x2061: "FUNCTION APPLICATION",
    0x2062: "INVISIBLE TIMES",
    0x2063: "INVISIBLE SEPARATOR",
    0x2064: "INVISIBLE PLUS",
    0x2066: "LEFT-TO-RIGHT ISOLATE",
    0x2067: "RIGHT-TO-LEFT ISOLATE",
    0x2068: "FIRST STRONG ISOLATE",
    0x2069: "POP DIRECTIONAL ISOLATE",
    0xFEFF: "ZERO WIDTH NO-BREAK SPACE (BOM)",
    0x180E: "MONGOLIAN VOWEL SEPARATOR",
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="不可见字符扫描")
    ap.add_argument("input", nargs="?", help="输入文件,缺省读 stdin")
    ap.add_argument("--fix", metavar="OUT", help="剥离这些字符后写入 OUT")
    args = ap.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    hits = []
    cleaned_parts = []
    for lineno, line in enumerate(text.splitlines(keepends=True), 1):
        col = 0
        for ch in line:
            cp = ord(ch)
            if cp in INVISIBLE:
                hits.append((lineno, col + 1, cp, INVISIBLE[cp]))
            else:
                cleaned_parts.append(ch)
            col += 1

    if hits:
        print("发现 %d 处不可见字符:" % len(hits))
        for lineno, col, cp, name in hits:
            print("  行 %d 列 %d  U+%04X  %s" % (lineno, col, cp, name))
    else:
        print("未发现不可见字符。")

    if args.fix:
        with open(args.fix, "w", encoding="utf-8", newline="") as f:
            f.write(''.join(cleaned_parts))
        print("已清理并写入: %s" % args.fix, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
