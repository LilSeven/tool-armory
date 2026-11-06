#!/usr/bin/env python3
"""统一差异生成：用 difflib 生成 unified diff 格式补丁文本，可控制上下文行数。

用法:
    python diff-patch.py <旧文件> <新文件> [-u 3] [--label A:B] [--out FILE]

示例:
    python diff-patch.py old.txt new.txt -u 3
    python diff-patch.py a.py b.py -u 1 --out fix.patch
"""
import argparse
import difflib
import sys


def main():
    ap = argparse.ArgumentParser(description="生成 unified diff 补丁文本")
    ap.add_argument("old", help="旧文件")
    ap.add_argument("new", help="新文件")
    ap.add_argument("-u", "--context", type=int, default=3, help="上下文行数，默认 3")
    ap.add_argument("--label", default="", help="自定义标签，格式 A:B（默认用文件名）")
    ap.add_argument("--out", help="补丁写入文件（默认打印 stdout）")
    args = ap.parse_args()

    texts = []
    for p in (args.old, args.new):
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                texts.append(fh.read().splitlines())
        except OSError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2

    if args.label:
        parts = args.label.split(":", 1)
        if len(parts) == 2:
            a_label, b_label = parts
        else:
            a_label = b_label = args.label
    else:
        a_label, b_label = args.old, args.new

    diff = difflib.unified_diff(
        texts[0], texts[1],
        fromfile=a_label, tofile=b_label,
        n=max(0, args.context), lineterm="",
    )
    lines = list(diff)

    text = "\n".join(lines)
    if not lines:
        text = "（两个文件相同，无差异）"
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
        print("written %s (%d diff lines)" % (args.out, len(lines)))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
