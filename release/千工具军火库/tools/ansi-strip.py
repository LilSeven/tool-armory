#!/usr/bin/env python3
"""ansi-strip.py — ANSI 转义序列清除工具。

从终端日志中剥离 ANSI 颜色码与光标控制序列（CSI/OSC/DCS/双字符转义、
字符集切换等），还原干净文本；--list 可先列出命中的序列。

覆盖：
  CSI  ESC[ ... 终止符        颜色/光标控制，如 ESC[31m、ESC[2J、ESC[1;1H
  OSC  ESC] ... BEL 或 ST     窗口标题、超链接等
  DCS/SOS/PM/APC  ESC P/^/_ ... ST
  双字符转义 ESC 7 / ESC M / ESC c 等
  字符集切换 ESC ( B、ESC ) 0 等

示例命令：
  python ansi-strip.py -i colored.log -o clean.log
  cat colored.log | python ansi-strip.py --list
  python ansi-strip.py --text $'\x1b[31mError\x1b[0m: disk full'
"""

import argparse
import re
import sys

# 各类转义序列（按优先级排列；OSC/DCS 需在双字符转义之前匹配）
PATTERNS = [
    ("OSC", re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")),
    ("DCS/SOS/PM/APC", re.compile(r"\x1b[P^_][^\x1b]*\x1b\\")),
    ("CSI", re.compile(r"\x1b\[[0-9:;<=>?]*[ -/]*[@-~]")),
    ("charset", re.compile(r"\x1b[()][0-9A-B0-2]")),
    # ECMA-48 双字符转义：ESC + 终止字节 0x30..0x7E（含 ESC 7 / ESC M / ESC c）
    ("ESC-2char", re.compile(r"\x1b[0-~]")),
]
COMBINED = re.compile("|".join("(?:%s)" % p.pattern for _n, p in PATTERNS))


def kind_of(seq: str) -> str:
    for name, pat in PATTERNS:
        if pat.fullmatch(seq):
            return name
    return "unknown"


def strip_ansi(text: str) -> str:
    return COMBINED.sub("", text)


def list_hits(text: str, limit: int = 30) -> int:
    count = 0
    for m in COMBINED.finditer(text):
        sys.stderr.write("[ansi-strip] 位置 %d  %-14s %r\n"
                         % (m.start() + 1, kind_of(m.group(0)), m.group(0)))
        count += 1
        if count >= limit:
            sys.stderr.write("[ansi-strip] ...（仅列出前 %d 处）\n" % limit)
            break
    return count


def main() -> int:
    ap = argparse.ArgumentParser(
        description="剥离终端日志中的 ANSI 颜色与光标控制序列。")
    ap.add_argument("-i", "--input", help="输入文件（缺省读 stdin）")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout）")
    ap.add_argument("--text", help="直接指定待处理文本")
    ap.add_argument("--list", action="store_true",
                    help="在 stderr 列出命中的转义序列")
    ap.add_argument("--squeeze", action="store_true",
                    help="额外把 3 个以上连续空行压缩为 1 个空行")
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

    total = len(COMBINED.findall(data))
    if args.list:
        list_hits(data)

    clean = strip_ansi(data)
    if args.squeeze:
        clean = re.sub(r"\n{3,}", "\n\n", clean)

    sys.stderr.write("[ansi-strip] 共剥离 %d 个转义序列，%d -> %d 字符。\n"
                     % (total, len(data), len(clean)))

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
