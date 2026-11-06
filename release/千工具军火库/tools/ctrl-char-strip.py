#!/usr/bin/env python3
"""控制字符清除(ctrl-char-strip)

删除 C0(0x00-0x1F)与 C1(0x7F,0x80-0x9F)控制字符;默认保留
\\n \\r \\t,可用 --visualize 把它们替换为 ^X 形式(如 ^@ ^A)而非删除。

用法:
  python ctrl-char-strip.py <输入文件> [-o 输出文件] [--visualize] [--all]
  cat in.txt | python ctrl-char-strip.py --visualize

选项:
  --visualize   控制字符显示为 ^X(删除模式则直接移除)
  --all         连同 \\n \\r \\t 也处理(默认保留)

示例:
  python ctrl-char-strip.py messy.log --visualize
  python ctrl-char-strip.py messy.log --all -o clean.txt
"""
import argparse
import sys

# Windows 控制台/管道默认 GBK,强制 UTF-8
for _s in (sys.stdout, sys.stderr, sys.stdin):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", newline="")

KEEP = {'\n', '\r', '\t'}
CARET = {0: '^@', 1: '^A', 2: '^B', 3: '^C', 4: '^D', 5: '^E', 6: '^F',
         7: '^G', 8: '^H', 9: '^I', 10: '^J', 11: '^K', 12: '^L',
         13: '^M', 14: '^N', 15: '^O', 16: '^P', 17: '^Q', 18: '^R',
         19: '^S', 20: '^T', 21: '^U', 22: '^V', 23: '^W', 24: '^X',
         25: '^Y', 26: '^Z', 27: '^[', 28: '^\\', 29: '^]', 30: '^^',
         31: '^_', 127: '^?'}
# C1 0x80-0x9F 用 ^C- 前缀表示不足,采用 ^<HEX> 形式


def is_ctrl(ch):
    cp = ord(ch)
    return cp < 32 or cp == 127 or 0x80 <= cp <= 0x9F


def process(text, visualize=False, strip_all=False):
    out = []
    n_removed = 0
    for ch in text:
        if not is_ctrl(ch) or (not strip_all and ch in KEEP):
            out.append(ch)
            continue
        n_removed += 1
        if visualize:
            cp = ord(ch)
            if cp in CARET:
                out.append(CARET[cp])
            else:
                out.append('^%02X' % cp)
    return ''.join(out), n_removed


def main(argv=None):
    ap = argparse.ArgumentParser(description="C0/C1 控制字符清除/可视化")
    ap.add_argument("input", nargs="?", help="输入文件,缺省读 stdin")
    ap.add_argument("-o", "--output", help="输出文件,缺省 stdout")
    ap.add_argument("--visualize", action="store_true",
                    help="控制字符替换为 ^X 形式")
    ap.add_argument("--all", action="store_true",
                    help="连同换行/回车/制表符一并处理")
    args = ap.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result, n = process(text, args.visualize, args.all)
    print("处理控制字符: %d 个" % n, file=sys.stderr)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
