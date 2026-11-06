#!/usr/bin/env python3
"""startup-namer.py — 创业公司起名: 生成 Zylora 式创业风名字并按音节流畅度打分(单文件, 仅标准库)。

用途:
    以"声母+元音(+尾音)"音节模板拼出 Zylora、Velyra、Kramora 一类创业风名字,
    并按启发式"音节流畅度"打分(0-100)。gen 生成并按分数降序输出;
    score 可给任意英文名打分。--seed 可复现结果。

流畅度规则(启发式, 视 y 为元音):
    + 元辅交替率(相邻两字母一辅一元占比): 每 1% 计 0.6 分, 满分 60
    + 音节数 2-3 个: +20; 1 或 4 个: +10; 其他: +0
    + 以元音收尾: +12; 以辅音收尾: +6
    + 长度 4-9 字母: +8; 3 或 10-11 字母: +4; 其他: +0
    - 每处 3 连辅音: -18; 每处难读的 2 连辅音: -6
    总分截取到 [0, 100]。评定: >=85 出众, >=70 顺口, >=50 尚可, <50 拗口。

示例:
    python startup-namer.py gen                    # 随机 1 个名字并打分
    python startup-namer.py gen 8                  # 生成 8 个, 按分数降序
    python startup-namer.py gen 5 --seed 1         # 固定种子复现
    python startup-namer.py gen 5 --min-score 85   # 只保留 85 分以上
    python startup-namer.py score Zylora           # 给任意名字打分
    python startup-namer.py score Xstrlqw          # 拗口名字, 分数很低
"""

from __future__ import annotations

import argparse
import random
import re
import sys

ONSETS = ["Z", "V", "N", "L", "S", "K", "M", "T", "R", "B", "P", "D", "G",
          "H", "Y", "W", "F", "J", "X", "C", "Qu"]
CLUSTERS = ["Zl", "Fl", "Kr", "Tr", "Sl", "Br", "Dr", "Kl", "Vr", "Gr", "Pr"]
NUCLEI = ["a", "e", "i", "o", "u", "y"]
# 非末音节的尾音(多数为开音节, 读起来更顺)
CODAS_IN = ["l", "n", "r", "m", "s", "x"]
CODAS_END = ["n", "x"]

VOWELS = set("aeiouy")
# 可读的 2 连辅音: 第二位为流音/滑音, 或属于常见辅音串
ALLOWED_PAIRS = {
    "st", "sp", "sk", "sn", "sm", "sc", "sw",
    "nd", "nt", "mp", "nk", "ng",
    "rd", "rn", "rt", "rk", "rm", "rl", "rs",
    "ld", "lm", "ln", "ls", "lt",
    "ns", "ms", "ts", "ds", "ks",
    "pt", "ct", "ft", "xt", "zt", "kt",
    "tr", "dr", "br", "cr", "fr", "gr", "pr", "bl", "cl", "fl", "gl", "pl",
    "kl", "kr", "vr", "zl", "zr", "xl", "th", "ph", "ch", "sh", "wh", "qu",
}

VERDICTS = ((85, "出众"), (70, "顺口"), (50, "尚可"), (0, "拗口"))


def pair_ok(pair):
    """两字母辅音串是否顺口。"""
    if len(pair) == 1:
        return True
    return pair[1] in "lrw" or pair in ALLOWED_PAIRS


def _nuc_pool(onset):
    """y 不作集群声母、Y/W 声母或省略声母后的元音(避免 Zly/Yy/Zyy 一类怪串)。"""
    if onset in ("Y", "W") or len(onset) == 2 or onset == "":
        return ("a", "e", "i", "o", "u")
    return tuple(NUCLEI)


def make_name(rng):
    """按音节模板拼名, 出 Zylora/Velyra/Kramora 一类形状:
    首音节必有声母(约一半为重音头集群声母, 可带尾音, 如 Zyl-);
    中间音节在前音节带尾音时可省声母(如 Zyl-o-ra), 否则必有声母;
    末音节多为开音节, 元音偏向 a/o, 偶以 n/x 收尾。整体保持元辅交替。"""
    n_syl = rng.choice((2, 3, 3, 3))
    sylls = []
    prev_open = True
    prev_onset = None
    for i in range(n_syl):
        last = (i == n_syl - 1)
        # 声母
        if i == 0:
            onset = rng.choice(CLUSTERS) if rng.random() < 0.45 else rng.choice(ONSETS)
        elif prev_open:
            onset = rng.choice(CLUSTERS) if rng.random() < 0.08 else rng.choice(ONSETS)
        else:
            onset = ""
            if rng.random() < 0.5:
                for _ in range(8):
                    cand = rng.choice(ONSETS)
                    if pair_ok(sylls[-1][2] + cand.lower()):
                        onset = cand
                        break
        if onset and onset == prev_onset:
            for _ in range(8):
                cand = rng.choice(ONSETS)
                if cand != prev_onset and (prev_open or
                                           pair_ok(sylls[-1][2] + cand.lower())):
                    onset = cand
                    break
        # 元音
        if last:
            nuc = rng.choice(("a", "a", "a", "o", "o", "i"))
        else:
            nuc = rng.choice(_nuc_pool(onset))
        # 尾音
        if last:
            coda = rng.choice(CODAS_END) if rng.random() < 0.08 else ""
        else:
            coda = rng.choice(CODAS_IN) if rng.random() < 0.35 else ""
        sylls.append([onset, nuc, coda])
        prev_open = (coda == "")
        prev_onset = onset
    s = "".join(o + n + c for o, n, c in sylls)
    return s[0].upper() + s[1:].lower()


def fluency(name):
    """返回 (总分 0-100, 音节数, 元辅交替率 0-1)。"""
    s = name.lower()
    n = len(s)
    syllables = len(re.findall(r"[aeiouy]+", s))
    classes = ["V" if ch in VOWELS else "C" for ch in s]
    trans = sum(1 for a, b in zip(classes, classes[1:]) if a != b)
    rate = trans / (n - 1) if n > 1 else 0.0
    score = 0.6 * rate * 100
    score += 20 if syllables in (2, 3) else (10 if syllables in (1, 4) else 0)
    score += 12 if s[-1] in VOWELS else 6
    score += 8 if 4 <= n <= 9 else (4 if n in (3, 10, 11) else 0)
    for run in re.findall(r"[^aeiouy]{2,}", s):
        if len(run) >= 3:
            score -= 18
        elif not pair_ok(run):
            score -= 6
    return max(0, min(100, int(round(score)))), syllables, rate


def verdict(score):
    for threshold, label in VERDICTS:
        if score >= threshold:
            return label
    return VERDICTS[-1][1]


def cmd_gen(args):
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    picked, seen = [], set()
    attempts = 0
    while len(picked) < args.count and attempts < args.count * 60 + 120:
        attempts += 1
        name = make_name(rng)
        if name in seen:
            continue
        seen.add(name)
        sc, syl, rate = fluency(name)
        picked.append((name, sc, syl, rate))
    picked.sort(key=lambda t: (-t[1], t[0]))
    kept = [t for t in picked if t[1] >= args.min_score]
    if not kept:
        raise ValueError("没有名字达到 --min-score %d(可降低阈值或重试)"
                         % args.min_score)
    for i, (name, sc, syl, rate) in enumerate(kept, 1):
        print("%d. %-12s %3d/100 (%d 音节, 交替率 %d%%, %s)"
              % (i, name, sc, syl, int(round(rate * 100)), verdict(sc)))
    return 0


def cmd_score(args):
    if not re.fullmatch(r"[A-Za-z]{2,20}", args.name):
        raise ValueError("名字需为 2-20 个英文字母, 如 Zylora")
    sc, syl, rate = fluency(args.name)
    print("%s: %d/100 (%d 音节, 交替率 %d%%, %s)"
          % (args.name, sc, syl, int(round(rate * 100)), verdict(sc)))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="startup-namer",
        description="生成 Zylora 式创业风名字并按音节流畅度打分。")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="命令")

    sp = sub.add_parser("gen", help="生成名字并打分(按分数降序)")
    sp.add_argument("count", nargs="?", type=int, default=1, help="生成个数(默认 1)")
    sp.add_argument("--min-score", type=int, default=0, metavar="N",
                    help="只保留不低于 N 分的名字")
    sp.add_argument("--seed", type=int, default=None,
                    help="随机种子, 提供则结果可复现")
    sp.set_defaults(func=cmd_gen)

    sp = sub.add_parser("score", help="给任意英文名打分")
    sp.add_argument("name", help="待评分名字, 如 Zylora")
    sp.set_defaults(func=cmd_score)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print("startup-namer: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
