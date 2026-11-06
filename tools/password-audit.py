#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""password-audit -- 口令清单自审：找重复口令、弱口令、与内置常见口令表重合项。

输入：本地口令清单文本文件，每行一条。两种行格式：
  <password>             纯口令
  <site>:<password>      站点:口令（按首个冒号切分；--sep 可改为其它分隔符）
未指定 --sep 时自动识别：行内含 TAB 按 TAB 切，否则含冒号按首个冒号切；
若口令本身含冒号，请用 --sep 指定一个不出现在口令中的分隔符。

审计项：跨条目重复口令 / 过短（--min-length，默认 8）/ 纯数字 /
字符多样性低 / 连续序列与重复字符 / 键盘横排 / 命中内置常见口令表（约 150 条）。
默认掩码显示口令，--show 明文；--json 输出机器可读结果。
退出码仅表示运行成败（0=成功），不代表是否发现问题。
所有数据仅本地处理，不联网；建议审计完即删导出文件。

示例:
  python password-audit.py audit passwords.txt
  python password-audit.py audit passwords.txt --sep : --min-length 10 --show
  python password-audit.py audit passwords.txt --json
  python password-audit.py selftest
"""

import argparse
import json
import re
import string
import sys
from collections import Counter

# 内置常见口令表（小写；比对时把条目口令转小写）
COMMON = set("""
123456 password 123456789 12345678 12345 qwerty 1234567 111111 1234567890
123123 abc123 1234 password1 iloveyou 000000 qwerty123 zaq12wsx dragon
sunshine princess letmein 654321 monkey 1qaz2wsx 123321 qwe123 money
eagle 123qwe whatever 1q2w3e4r qazwsx 123abc password123 qweasd zxcvbnm
asdfgh iloveu superman batman trustno1 tigger purple pepper maggie chelsea
andrew charlie jessica michael jennifer thomas robert jordan harley ranger
buster hunter killer george welcome master hello freedom starwars shadow
computer internet samsung apple google amazon netflix facebook twitter
youtube instagram linkedin steam minecraft baseball football soccer hockey
696969 121212 112233 121314 777777 555555 888888 666666 232323 102030
1234qwer qwertyuiop asdfghjkl 1q2w3e aa123456 abcd1234 test123 temp123
guest admin changeme admin123 root toor passw0rd p@ssw0rd welcome1 letmein1
0123456789 123123123 147258369 987654321 7654321 11111 11111111 12121212
banana cheese cookie chocolate coffee beer wine money cash gold silver
ashley amanda nicole hannah jasmine daniel matthew anthony dennis brandon
summer2023 summer2024 winter2024 spring2024 autumn2024 hunter2
""".split())

KEYBOARD_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890"]
PUNCT = set(string.punctuation)


def parse_entries(text, sep=None):
    """按行解析清单 -> [{line, label, password}]。"""
    entries = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        label, password = None, line
        if sep is not None:
            if sep in line:
                label, password = line.split(sep, 1)
        elif "\t" in line:
            label, password = line.split("\t", 1)
        elif ":" in line:
            label, password = line.split(":", 1)
        entries.append({"line": lineno, "label": label.strip() if label else None,
                        "password": password.strip()})
    return entries


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
                for b in range(n, a + 2, -1):
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


def check_password(pw, min_length):
    """返回该口令的问题标签列表（无问题则为空）。"""
    reasons = []
    if pw.lower() in COMMON:
        reasons.append("common-list")
    if len(pw) < min_length:
        reasons.append(f"short(<{min_length})")
    if pw.isascii() and pw.isdigit():
        reasons.append("digits-only")
    if len(pw) >= 4 and len(set(pw)) <= 3:
        reasons.append("low-diversity")
    if re.search(r"(.)\1{2,}", pw):
        reasons.append("repeat-run")
    for _s, _e, frag in _sequence_runs(pw.lower()):
        if len(frag) >= 4:
            reasons.append("sequence:" + frag)
            break
    for frag in _keyboard_runs(pw.lower()):
        if len(frag) >= 4:
            reasons.append("keyboard:" + frag)
            break
    return reasons


def audit(entries, min_length=8):
    """返回报告 dict：重复组与逐条问题。"""
    counts = Counter(e["password"] for e in entries)
    dup = {pw for pw, c in counts.items() if c > 1}
    report = {
        "entries": len(entries),
        "unique": len(counts),
        "duplicate_groups": [
            {"password": pw, "count": counts[pw],
             "lines": [e["line"] for e in entries if e["password"] == pw]}
            for pw in sorted(dup, key=lambda p: (-counts[p], p))
        ],
        "findings": [],
    }
    for e in entries:
        reasons = check_password(e["password"], min_length)
        if e["password"] in dup:
            reasons.append("duplicate")
        if reasons:
            report["findings"].append({"line": e["line"], "label": e["label"],
                                       "password": e["password"], "reasons": reasons})
    report["issue_entries"] = len(report["findings"])
    return report


def mask(pw):
    if len(pw) <= 4:
        return "*" * len(pw)
    return pw[:2] + "*" * (len(pw) - 3) + pw[-1]


def print_report(report, show=False, min_length=8):
    def pwx(pw):
        return pw if show else mask(pw)

    print("== password-audit report ==")
    print(f"entries: {report['entries']}   unique passwords: {report['unique']}"
          f"   min length: {min_length}")
    if report["duplicate_groups"]:
        print(f"duplicate password groups ({len(report['duplicate_groups'])}):")
        for g in report["duplicate_groups"]:
            print(f"  x{g['count']} at lines {','.join(map(str, g['lines']))}"
                  f" : {pwx(g['password'])}")
    else:
        print("duplicate password groups: none")
    if report["findings"]:
        print(f"findings ({report['issue_entries']} entries flagged):")
        for f in report["findings"]:
            label = f["label"] if f["label"] else "-"
            print(f"  line {f['line']:<4} [{label:<16}] {', '.join(f['reasons'])}"
                  f"   pw={pwx(f['password'])}")
    else:
        print("findings: none")
    reasons = Counter(r for f in report["findings"] for r in f["reasons"])
    if reasons:
        top = ", ".join(f"{k}({v})" for k, v in reasons.most_common())
        print(f"summary: {report['issue_entries']}/{report['entries']} entries flagged;"
          f" reasons: {top}")
    else:
        print(f"summary: 0/{report['entries']} entries flagged")


def load_text(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def cmd_audit(args):
    try:
        text = load_text(args.file)
    except OSError as exc:
        print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
        return 2
    entries = parse_entries(text, args.sep)
    report = audit(entries, args.min_length)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report, show=args.show, min_length=args.min_length)
    return 0


def cmd_selftest(_args):
    sample = (
        "github.com:Ky9#mT2vLq8!z\n"
        "gitlab.com:Ky9#mT2vLq8!z\n"      # 与上一条重复
        "email:123456\n"                   # 常见表 + 纯数字
        "old-mail:abc123\n"                # 常见表
        "router:admin\n"                   # 常见表 + 过短
        "feed:aaaaaaaa\n"                  # 重复字符 + 低多样性
        "notes:1234abcd\n"                 # 连续序列
        "bank:Tx8!vR2#pLm9@Qz\n"           # 健康
        "plainline-no-label\n"             # 无标签格式，健康
    )
    entries = parse_entries(sample)
    assert len(entries) == 9, len(entries)
    assert entries[0]["label"] == "github.com" and entries[0]["password"] == "Ky9#mT2vLq8!z"
    assert entries[8]["label"] is None and entries[8]["password"] == "plainline-no-label"

    report = audit(entries, 8)
    flagged = {f["line"] for f in report["findings"]}
    # 第 1、2 行同口令 => 双双带 duplicate；3-7 各有弱口令问题；8、9 健康
    assert flagged == {1, 2, 3, 4, 5, 6, 7}, flagged
    assert len(report["duplicate_groups"]) == 1
    assert report["duplicate_groups"][0]["count"] == 2
    assert report["duplicate_groups"][0]["lines"] == [1, 2]
    by_line = {f["line"]: f["reasons"] for f in report["findings"]}
    assert by_line[1] == ["duplicate"] and "duplicate" in by_line[2]
    assert "common-list" in by_line[3] and "digits-only" in by_line[3]
    assert "common-list" in by_line[4] and "common-list" in by_line[5]
    assert "short(<8)" in by_line[5]
    assert "repeat-run" in by_line[6] and "low-diversity" in by_line[6]
    assert any(r.startswith("sequence:") for r in by_line[7])
    assert 8 not in flagged and 9 not in flagged, "strong/label-less lines should not be flagged"

    # --sep 逗号格式
    e2 = parse_entries("shop,Ab7#kk22QQ\n", ",")
    assert e2[0]["label"] == "shop" and e2[0]["password"] == "Ab7#kk22QQ"

    # 掩码不泄露完整口令
    assert mask("Ky9#mT2vLq8!z") != "Ky9#mT2vLq8!z" and "*" in mask("Ky9#mT2vLq8!z")

    print("selftest: parsing / duplicates / weak & common detection / masking passed")
    print("report preview for the built-in sample:")
    print_report(report, show=False, min_length=8)
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="password-audit",
                                 description="audit a local password list (stdlib only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="audit a password list file ('-' for stdin)")
    a.add_argument("file", help="password list path, or '-' for stdin")
    a.add_argument("--sep", help="force a separator between label and password (default: auto TAB/colon)")
    a.add_argument("--min-length", type=int, default=8, help="minimum acceptable length (default 8)")
    a.add_argument("--show", action="store_true", help="show passwords unmasked in the report")
    a.add_argument("--json", action="store_true", help="output machine-readable JSON")
    a.set_defaults(func=cmd_audit)

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
