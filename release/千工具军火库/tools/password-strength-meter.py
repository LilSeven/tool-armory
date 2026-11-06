#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""password-strength-meter -- 口令强度评估：熵值、字符空间、暴力穷举时间与可预测模式。

从 --password 或 stdin 读取口令（避免进入 shell 历史），输出：
  · 字符空间：按口令实际用到的类别（小写/大写/数字/符号/空格/非ASCII）
    估算攻击者的穷举池大小，给出 len*log2(pool) 基线熵；
  · 可预测模式扣减（启发式）：重复字符、字母/数字连续序列、键盘横排
    （qwerty 等）、内置常见口令词典命中（含 leet 归一，如 P@ssw0rd）、
    纯数字的年份/日期形态；
  · 折减后的有效熵与 4 档猜解速率下的平均穷举时间（平均搜到一半空间）。
全部本地计算，不联网，口令不落盘。评估为启发式，非保证。

示例:
  python password-strength-meter.py check --password 'P@ssw0rd!'
  echo 'mypassword' | python password-strength-meter.py check --stdin
  python password-strength-meter.py selftest
"""

import argparse
import math
import re
import string
import sys

# 内置常见口令词典（小写；待测口令先转小写并做 leet 归一再比对）
COMMON = set("""
123456 password 12345678 qwerty 111111 123456789 1234567890 abc123 123123
iloveyou admin welcome monkey dragon letmein login princess qwertyuiop
master hello freedom whatever starwars sunshine football baseball superman
batman pokemon shadow michael jennifer jordan harley ranger buster tigger
purple pepper maggie chelsea andrew charlie jessica thomas robert access
flower summer winter spring autumn secret hunter killer ninja matrix
computer internet samsung apple google amazon netflix facebook
test guest root changeme password1 passw0rd p@ssw0rd trustno1 qazwsx
asdfgh zxcvbnm 654321 696969 000000 121212 112233 123321 888888 159753
qwerty123 abc123456 1q2w3e4r 1qaz2wsx zaq12wsx 1234qwer 123qwe abcd1234
qweasd a123456 123456a 11111 121314 777777 555555 666666 131313 1234321
1234 12345 1234567 7654321 987654321 0123456789 147258369 102030
""".split())

KEYBOARD_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890"]

# leet 归一化：常见替换还原为字母（逐字符、等长映射）
LEET = str.maketrans({"4": "a", "@": "a", "8": "b", "3": "e", "1": "i", "!": "i",
                      "0": "o", "$": "s", "5": "s", "7": "t", "+": "t", "6": "g"})

PUNCT = set(string.punctuation)  # 32 个 ASCII 符号

RATES = [
    (10, "online, throttled (10/s)"),
    (10 ** 4, "online, unthrottled (10^4/s)"),
    (10 ** 10, "offline, GPU rig (10^10/s)"),
    (10 ** 12, "cracking farm (10^12/s)"),
]


def charset_pool(pw):
    """返回 (穷举池大小, 类别描述列表)。"""
    pool, classes = 0, []
    if re.search(r"[a-z]", pw):
        pool += 26
        classes.append("lower=26")
    if re.search(r"[A-Z]", pw):
        pool += 26
        classes.append("upper=26")
    if re.search(r"[0-9]", pw):
        pool += 10
        classes.append("digit=10")
    if any(c in PUNCT for c in pw):
        pool += 32
        classes.append("punct=32")
    if " " in pw:
        pool += 1
        classes.append("space=1")
    non_ascii = {c for c in pw if ord(c) > 126}
    if non_ascii:
        add = 500 * len(non_ascii)  # 对中文等非 ASCII 的粗略池估计
        pool += add
        classes.append(f"non-ascii x{len(non_ascii)}=+{add}")
    return pool, classes


def _sequence_runs(low):
    """字母/数字 ±1 连续段，长度>=3；返回 [(start, end, frag)]。"""
    found = []
    i, n = 0, len(low)
    while i < n - 2:
        d = ord(low[i + 1]) - ord(low[i])
        if d in (1, -1) and low[i].isalnum() and low[i].isascii():
            j = i + 1
            while j < n - 1 and ord(low[j + 1]) - ord(low[j]) == d:
                j += 1
            if j - i + 1 >= 3:
                found.append((i, j + 1, low[i:j + 1]))
                i = j
        i += 1
    return found


def _keyboard_runs(low):
    """键盘横排片段（含倒序），长度>=3，去除相互重叠。"""
    frags = []
    for row in KEYBOARD_ROWS:
        for r in (row, row[::-1]):
            n = len(r)
            for a in range(n):
                for b in range(n, a + 2, -1):  # 从最长开始试
                    frag = r[a:b]
                    if len(frag) >= 3 and frag in low:
                        frags.append(frag)
                        break
    out, taken = [], []
    for f in sorted(frags, key=len, reverse=True):
        s = low.find(f)
        if any(not (s + len(f) <= t or s >= t + len(g)) for t, g in taken):
            continue
        taken.append((s, f))
        out.append(f)
    return out


def evaluate(pw):
    """返回评估结果 dict：池、基线熵、模式扣减、有效熵、各速率穷举时间。"""
    pool, classes = charset_pool(pw)
    log_pool = math.log2(pool) if pool > 1 else 1.0
    base = len(pw) * log_pool
    low = pw.lower()
    norm = low.translate(LEET)

    findings = []  # (kind, detail, penalty_bits)

    # 1) 词典命中：整串或含 >=4 字符常见词（原文或 leet 归一后）
    if low in COMMON or norm in COMMON:
        findings.append(("dictionary", "whole password is a common password", float("inf")))
    else:
        hit = None
        for w in COMMON:
            if len(w) >= 4 and (w in low or w in norm):
                if hit is None or len(w) > len(hit):
                    hit = w
        if hit:
            findings.append(("dictionary", f"contains common word {hit!r}", 12.0))

    # 2) 重复字符段（同字符 x3+）：多出的每个字符几乎不增加熵
    for m in re.finditer(r"(.)\1{2,}", pw):
        r = len(m.group(0))
        findings.append(("repeat", f"repeated run {m.group(0)[:8]!r} (len={r})",
                         (r - 1) * log_pool))

    # 3) 连续序列段（abc/321）
    for _s, _e, frag in _sequence_runs(low):
        findings.append(("sequence", f"sequence {frag!r}",
                         (len(frag) - 2) * log_pool * 0.8))

    # 4) 键盘横排
    for frag in _keyboard_runs(low):
        findings.append(("keyboard", f"keyboard run {frag!r}",
                         (len(frag) - 2) * log_pool * 0.6))

    # 5) 纯数字形态：年份 / YYYYMMDD / 短数字（PIN、手机片段）
    if pw.isascii() and pw.isdigit():
        if re.fullmatch(r"(19|20)\d{2}", pw):
            findings.append(("year", "looks like a year", 14.0))
        elif re.fullmatch(r"(19|20)\d{2}[01]\d[0-3]\d", pw):
            findings.append(("date", "looks like YYYYMMDD date", 16.0))
        elif len(pw) <= 6:
            findings.append(("short-digits", "short digit-only (PIN/phone fragment)", 12.0))

    cap = 0.98 * base if base > 0 else 0.0  # 扣减上限，留一点不确定性
    penalty = min(sum(p for _k, _d, p in findings), cap)
    effective = max(base - penalty, 1.0)
    guesses = 2 ** (effective - 1)  # 平均找到一半空间
    times = [(name, human_time(guesses / rate)) for rate, name in RATES]
    return {
        "length": len(pw), "pool": pool, "classes": classes,
        "base": base, "findings": findings, "effective": effective,
        "times": times, "verdict": verdict(effective),
    }


def verdict(eff):
    if eff < 28:
        return "very weak"
    if eff < 36:
        return "weak"
    if eff < 60:
        return "fair"
    if eff < 80:
        return "strong"
    return "excellent"


def human_time(seconds):
    if seconds < 1:
        return "instant"
    if seconds < 60:
        return f"{seconds:.1f} s"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    if seconds < 48 * 3600:
        return f"{seconds / 3600:.1f} h"
    if seconds < 365.25 * 86400:
        return f"{seconds / 86400:.1f} days"
    years = seconds / (365.25 * 86400)
    if years < 1e6:
        return f"{years:,.1f} years"
    if years < 1e12:
        return f"{years:.3g} years"
    return f"{years:.3g} years (geological)"


def mask(pw):
    if len(pw) <= 4:
        return "*" * len(pw)
    return pw[0] + "*" * (len(pw) - 2) + pw[-1]


def print_report(pw, r):
    print("== password strength report ==")
    print(f"password   : {mask(pw)}")
    print(f"length     : {r['length']}")
    print(f"classes    : {', '.join(r['classes']) if r['classes'] else '-'}")
    print(f"pool       : {r['pool']}")
    print(f"baseline   : {r['base']:.1f} bits  ({r['length']} * log2({r['pool']}))")
    if r["findings"]:
        items = "; ".join(f"{k}: {d} (-{p:.1f} bits)" if p != float("inf")
                          else f"{k}: {d} (-> ~0)" for k, d, p in r["findings"])
        print(f"patterns   : {items}")
    else:
        print("patterns   : none detected")
    print(f"effective  : {r['effective']:.1f} bits")
    print(f"verdict    : {r['verdict']}")
    print("crack time (avg, half keyspace):")
    for name, t in r["times"]:
        print(f"  {name:<34}: {t}")
    print("note: heuristic estimate; unique random passphrases beat any pattern rule.")


def cmd_check(args):
    if args.password is not None:
        pw = args.password
    elif args.stdin:
        pw = sys.stdin.readline().rstrip("\r\n")
    else:
        raise ValueError("provide --password or --stdin")
    if not pw:
        raise ValueError("empty password")
    print_report(pw, evaluate(pw))
    return 0


def cmd_selftest(_args):
    weak = ["123456", "password", "P@ssw0rd!", "qwerty123", "aaaaaaaa", "abc12345", "19900815"]
    strong = ["rT9#mX2$vLq8Zw", "correct-horse-battery-staple-42!"]
    eff = {p: evaluate(p)["effective"] for p in weak + strong}

    # 1) 整串常见口令应被压到极低熵
    assert eff["123456"] < 10, eff["123456"]
    # 2) 各类模式都能被识别
    kinds = {k for p in weak for k, _d, _p in evaluate(p)["findings"]}
    for need in ("dictionary", "repeat", "sequence", "keyboard", "date"):
        assert need in kinds, f"pattern {need!r} not detected, got {kinds}"
    # 3) 强口令应无模式命中且有效熵高
    assert not evaluate("rT9#mX2$vLq8Zw")["findings"], "false positive on random password"
    assert eff["rT9#mX2$vLq8Zw"] >= 60, eff["rT9#mX2$vLq8Zw"]
    # 4) 熵排序：纯弱 < leet 常见词 < 随机强口令
    assert eff["123456"] < eff["P@ssw0rd!"] < eff["rT9#mX2$vLq8Zw"], eff

    print("selftest: pattern detection + entropy ordering checks passed")
    for p in weak + strong:
        print(f"  {p!r:>34} -> effective {eff[p]:6.1f} bits ({evaluate(p)['verdict']})")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="password-strength-meter",
                                 description="offline password strength estimation (stdlib only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="evaluate one password")
    c.add_argument("--password", help="password on argv (use --stdin to avoid shell history)")
    c.add_argument("--stdin", action="store_true", help="read password from first stdin line")
    c.set_defaults(func=cmd_check)

    t = sub.add_parser("selftest", help="run built-in self test")
    t.set_defaults(func=cmd_selftest)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
