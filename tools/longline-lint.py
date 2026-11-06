"""超长行检查：找出超过列宽阈值的行并报告位置，支持按显示宽度计算中文。

功能：
  - 逐行计算显示宽度：CJK 全角字符按 2 列（unicodedata.east_asian_width W/F），
    半角按 1 列，Tab 按可配置的制表位展开
  - 报告超过 --max-width 的行号、实际宽度、超出量与行内容截断预览
  - 退出码：发现超长行返回 1（便于 CI 门禁），无超长返回 0

示例命令：
  python longline-lint.py src/main.py --max-width 100
  python longline-lint.py README.md --max-width 80 --tab 4 --snippet 60
  python longline-lint.py notes.txt --count-cjk

参数：
  file                 输入文件
  --max-width N        列宽阈值（默认 80）
  --tab N              Tab 制表位宽度（默认 8）
  --snippet N          行内容预览的最大字符数（默认 80，0 关闭）
  --count-cjk          显式启用 CJK 全角按 2 列计数（默认已启用，仅作显式声明）
  --no-count-cjk       关闭 CJK 双宽，所有字符一律按 1 列计数（与 --count-cjk 互斥）
  --encoding ENC       输入编码（默认 utf-8，容错 replace）
"""
import argparse
import sys
import unicodedata


def display_width(s, tab=8, cjk=True):
    w = 0
    for ch in s:
        if ch == "\t":
            w += tab - (w % tab)
        elif cjk and unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        else:
            w += 1
    return w


def main(argv=None):
    ap = argparse.ArgumentParser(description="按显示宽度检查超长行并报告位置")
    ap.add_argument("file", help="输入文件")
    ap.add_argument("--max-width", type=int, default=80, help="列宽阈值（默认 80）")
    ap.add_argument("--tab", type=int, default=8, help="Tab 制表位宽度（默认 8）")
    ap.add_argument("--snippet", type=int, default=80, help="预览字符数（0 关闭）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--count-cjk", action="store_true",
                   help="显式启用 CJK 全角按 2 列计数（默认已启用，仅作显式声明）")
    g.add_argument("--no-count-cjk", action="store_true",
                   help="关闭 CJK 双宽，所有字符一律按 1 列计数")
    ap.add_argument("--encoding", default="utf-8", help="输入编码（默认 utf-8）")
    args = ap.parse_args(argv)
    cjk = not args.no_count_cjk

    offenders = []
    with open(args.file, encoding=args.encoding, errors="replace") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\r\n")
            w = display_width(line, args.tab, cjk)
            if w > args.max_width:
                offenders.append((lineno, w, w - args.max_width, line))

    print(f"file: {args.file}")
    print(f"max-width: {args.max_width}, tab: {args.tab}")
    if not offenders:
        print("OK: no lines exceed the width limit")
        return 0
    print(f"found {len(offenders)} long line(s):")
    for lineno, w, over, line in offenders:
        prev = line[:args.snippet] if args.snippet else ""
        print(f"  L{lineno}: width={w} (+{over})  {prev}")
    print(f"summary: {len(offenders)} line(s) over {args.max_width} columns")
    return 1


if __name__ == "__main__":
    sys.exit(main())
