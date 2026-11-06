#!/usr/bin/env python3
"""行集合运算：对两个文件做行级交/并/差/对称差，无需预排序（用集合/计数实现）。

重复行默认去重；--keep-dup 时按多重集（multiset）语义运算。
输出按行在 A（差集/交集取 A；并集先 A 后 B 新增）中首次出现的顺序排列。

用法:
    python lineset-ops.py a.txt b.txt -m intersect
    python lineset-ops.py a.txt b.txt -m union,diff -o out_.txt
    python lineset-ops.py a.txt b.txt -m symdiff --keep-dup
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

MODES = ("intersect", "union", "diff", "symdiff")


def read_lines(path: str, encoding: str):
    if path == "-":
        return [ln.rstrip("\r\n") for ln in sys.stdin]
    p = Path(path)
    if not p.is_file():
        ap = argparse.ArgumentParser()
        ap.error(f"不是文件: {path}")
    with open(p, "r", encoding=encoding, errors="replace") as fh:
        return [ln.rstrip("\r\n") for ln in fh]


def op_multiset(mode: str, ca: Counter, cb: Counter):
    if mode == "intersect":
        return ca & cb
    if mode == "union":
        return ca | cb
    if mode == "diff":
        return ca - cb
    if mode == "symdiff":
        return (ca - cb) + (cb - ca)
    raise ValueError(mode)


def op_set(mode: str, sa, sb):
    if mode == "intersect":
        return sa & sb
    if mode == "union":
        return sa | sb
    if mode == "diff":
        return sa - sb
    if mode == "symdiff":
        return sa ^ sb
    raise ValueError(mode)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="对两个文件做行级交/并/差运算，类似 comm 但无需预排序。")
    ap.add_argument("file1", help="文件 A（'-' 表示 stdin）")
    ap.add_argument("file2", help="文件 B（'-' 表示 stdin）")
    ap.add_argument("-m", "--mode", default="intersect",
                    help="intersect/union/diff/symdiff，逗号分隔可一次做多个（默认 intersect）")
    ap.add_argument("--keep-dup", action="store_true",
                    help="按多重集语义保留重复次数（默认去重）")
    ap.add_argument("-o", "--output", default="-", help="输出文件，缺省 stdout")
    ap.add_argument("--encoding", default="utf-8", help="输入编码（默认 utf-8）")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding=args.encoding, errors="replace")
    except Exception:
        pass

    modes = [m.strip() for m in args.mode.split(",") if m.strip()]
    for m in modes:
        if m not in MODES:
            ap.error(f"未知运算: {m}，可选 {','.join(MODES)}")

    la = read_lines(args.file1, args.encoding)
    lb = read_lines(args.file2, args.encoding)
    order_a, order_b = [], []
    for ln in la:
        if ln not in order_a:
            order_a.append(ln)
    for ln in lb:
        if ln not in order_b:
            order_b.append(ln)

    out = sys.stdout if args.output == "-" else open(
        args.output, "w", encoding="utf-8", newline="")
    try:
        for mode in modes:
            if len(modes) > 1:
                out.write(f"### {mode} ###\n")
            if args.keep_dup:
                result = op_multiset(mode, Counter(la), Counter(lb))
                # 顺序：A 中首次出现，其后 B 中新增；每行首次遇到时按剩余次数输出
                for ln in order_a + order_b:
                    remaining = result.pop(ln, 0)
                    for _ in range(remaining):
                        out.write(ln + "\n")
            else:
                result = op_set(mode, set(la), set(lb))
                for ln in order_a + order_b:
                    if ln in result:
                        out.write(ln + "\n")
                        result.discard(ln)
    finally:
        if out is not sys.stdout:
            out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
