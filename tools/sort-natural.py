#!/usr/bin/env python3
"""自然排序 (sort-natural): 按数字感知方式对文本行排序，file2 排在 file10 之前。

支持按列取键（默认整行）、忽略大小写、唯一化、逆序。数字段按数值比较，
非数字段按字符串比较，因此 a2 < a10，v1.10 > v1.9。

用法:
  python -I sort-natural.py [-k COL] [-d SEP] [-i] [-r] [-u] [FILE ...]

选项:
  -k, --key COL   按第 COL 列（1 起）作为排序键；缺省用整行
  -d, --delim SEP 列分隔符（字面量，支持写 \\t）；缺省按连续空白切分
  -i, --fold      忽略大小写
  -r, --reverse   逆序
  -u, --unique    排序后去重（相邻键相同的行只保留第一个）
  FILE ...        输入文件；缺省或为 - 时读 stdin

示例:
  printf 'file10\\nfile2\\nfile1\\n' | python -I sort-natural.py
  python -I sort-natural.py -k 2 -i scores.txt
  python -I sort-natural.py -d ',' -k 3 -r data.csv
"""

import argparse
import re
import sys

# Windows 控制台/管道下强制 UTF-8，避免 Git Bash 管道输入输出乱码
for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def natural_key(text: str, fold: bool):
    """把字符串拆成数字/非数字段，返回可比较的 key。"""
    parts = re.split(r"(\d+)", text)
    key = []
    for p in parts:
        if p == "":
            continue
        if p.isdigit():
            key.append((0, int(p), ""))
        else:
            key.append((1, 0, p.lower() if fold else p))
    # 末尾拼原文作稳定 tiebreak（区分 file02 与 file2）
    return (key, text.lower() if fold else text)


def main() -> int:
    ap = argparse.ArgumentParser(description="自然排序：数字感知的行排序")
    ap.add_argument("-k", "--key", type=int, default=0,
                    help="按第几列排序（1 起），0=整行（默认 0）")
    ap.add_argument("-d", "--delim", default=None,
                    help="列分隔符，\\t 代表制表符；缺省按空白切分")
    ap.add_argument("-i", "--fold", action="store_true", help="忽略大小写")
    ap.add_argument("-r", "--reverse", action="store_true", help="逆序输出")
    ap.add_argument("-u", "--unique", action="store_true",
                    help="去重（排序键相同的行只留一行）")
    ap.add_argument("files", nargs="*", help="输入文件，缺省读 stdin")
    args = ap.parse_args()

    if args.delim is not None:
        delim = args.delim.replace("\\t", "\t")
        split_fn = lambda s: s.split(delim)  # noqa: E731
    else:
        split_fn = str.split

    def key_for(line: str):
        if args.key > 0:
            cols = split_fn(line)
            field = cols[args.key - 1] if len(cols) >= args.key else ""
        else:
            field = line
        return natural_key(field, args.fold)

    lines = []
    files = args.files or ["-"]
    for path in files:
        stream = sys.stdin if path == "-" else open(
            path, "r", encoding="utf-8", errors="replace")
        try:
            for raw in stream:
                lines.append(raw.rstrip("\r\n"))
        finally:
            if stream is not sys.stdin:
                stream.close()

    lines.sort(key=key_for, reverse=args.reverse)

    if args.unique:
        out, seen = [], set()
        for ln in lines:
            k = repr(key_for(ln))
            if k not in seen:
                seen.add(k)
                out.append(ln)
        lines = out

    for ln in lines:
        print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
