#!/usr/bin/env python3
"""CP 名生成器 —— 从两个名字混拼截取, 生成同人 CP 名候选。

用途:
    输入两个名字(中英文皆可), 用「前后缀截取 / 交替混拼 / 重叠融合 /
    直球连写」等手法生成一批 CP 名候选, 并按好念程度打分排序。

用法:
    python ship-name.py NAME1 NAME2 [--count N] [--seed SEED]

示例命令:
    python ship-name.py Alice Bob
    python ship-name.py Brad Angelina --count 5 --seed 9
    python ship-name.py 蓝湛 魏婴 --count 5

仅依赖 Python 标准库; 成功时退出码为 0。
"""

from __future__ import annotations

import argparse
import random
import sys

VOWELS = set("aeiou")


def max_consonant_run(word: str) -> int:
    run = best = 0
    for ch in word:
        if ch.isalpha() and ch not in VOWELS:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def interleave(a: str, b: str) -> list:
    """两个名字逐字交替混拼, 各给一个先后顺序。"""
    tail = a[len(b):] if len(a) > len(b) else b[len(a):]
    out1 = "".join(x + y for x, y in zip(a, b)) + tail
    out2 = "".join(y + x for x, y in zip(a, b)) + tail
    return [out1, out2]


def overlap_merge(a: str, b: str):
    """若 a 的尾部与 b 的头部重合, 融合之(如 brad + angelina -> bradgelina)。"""
    for k in range(min(len(a), len(b)), 0, -1):
        if a[-k:] == b[:k]:
            return a + b[k:]
    return None


def candidates(a: str, b: str, rng: random.Random) -> list:
    """返回 [(候选名, 手法), ...]。"""
    cands = []

    def head_tail(x, y, tag):
        lx, ly = len(x), len(y)
        combos = [(i, j) for i in range(1, lx) for j in range(0, ly)]
        if lx > 8 or ly > 8:
            rng.shuffle(combos)
            combos = combos[:12]
        for i, j in combos:
            cand = x[:i] + y[j:]
            if cand:
                cands.append((cand, tag))

    head_tail(a, b, "A头B尾")
    head_tail(b, a, "B头A尾")
    for cand in interleave(a, b):
        cands.append((cand, "交替混拼"))
    for x, y in ((a, b), (b, a)):
        merged = overlap_merge(x, y)
        if merged:
            cands.append((merged, "重叠融合"))
    cands.append((a + b, "直球连写"))
    cands.append((b + a, "直球连写"))
    return cands


def score(cand: str, rng: random.Random) -> int:
    """好念程度打分: 长度合适、有元音、辅音不堆叠加分。"""
    s = rng.randint(0, 2)
    n = len(cand)
    if cand.isascii():
        if 4 <= n <= 8:
            s += 3
        elif n <= 10:
            s += 1
        else:
            s -= 2
        if any(ch in VOWELS for ch in cand):
            s += 2
        if max_consonant_run(cand) >= 3:
            s -= 3
    else:
        if 2 <= n <= 4:
            s += 3
        elif n <= 6:
            s += 1
        else:
            s -= 2
    return s


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(
        description="CP 名生成器: 两个名字混拼截取生成 CP 名候选")
    parser.add_argument("name1", help="第一个名字 (A)")
    parser.add_argument("name2", help="第二个名字 (B)")
    parser.add_argument("--count", type=int, default=6, help="候选数量 (默认 6)")
    parser.add_argument("--seed", type=int, default=None, help="随机种子, 便于复现")
    args = parser.parse_args(argv)

    if args.count < 1:
        parser.error("--count 至少为 1")
    a_raw, b_raw = args.name1.strip(), args.name2.strip()
    if not a_raw or not b_raw:
        parser.error("名字不能为空")

    rng = random.Random(args.seed)
    a = a_raw.lower() if a_raw.isascii() else a_raw
    b = b_raw.lower() if b_raw.isascii() else b_raw

    seen = {a_raw.lower(), b_raw.lower()}
    pool = []
    for cand, tag in candidates(a, b, rng):
        cand = cand.strip()
        if not cand or cand.lower() in seen:
            continue
        seen.add(cand.lower())
        pool.append((cand, tag, score(cand, rng)))
    pool.sort(key=lambda t: -t[2])

    print("CP 名候选: %s × %s" % (a_raw, b_raw))
    if not pool:
        print("(没有生成有效候选)")
        return 0
    for i, (cand, tag, sc) in enumerate(pool[:args.count], 1):
        mark = "★" if i == 1 else " "
        disp = cand.capitalize() if cand.isascii() else cand
        print(" %s %d. %-12s [%s · %d分]" % (mark, i, disp, tag, sc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
