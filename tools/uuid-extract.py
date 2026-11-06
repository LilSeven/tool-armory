#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UUID 抽取器：用正则从文本/日志中抽取所有 UUID，去重并按版本归类。

匹配规则：
    默认匹配带连字符的标准 UUID（允许 {大括号} / [方括号] 与 urn:uuid: 前缀）；
    --bare 额外匹配 32 位无连字符 hex（要求前后不紧邻 hex 或连字符，避免误切）。
    版本取标准写法第 13 个 hex 位（版本号）：v1..v8，其余（0/9/a-f）记为 unknown。
    输出去重后的 UUID（统一为小写标准写法，按首次出现顺序），并按版本统计唯一数。

示例命令：
    python uuid-extract.py app.log
    python uuid-extract.py a.log b.log --bare
    type app.log | python uuid-extract.py -
    python uuid-extract.py app.log --json
    python uuid-extract.py --selftest

退出码：0 成功；2 输入或参数非法。
"""

import argparse
import json
import re
import sys

CANON_RE = re.compile(
    r"(?:urn:uuid:)?[{[]?\b([0-9a-fA-F]{8})-([0-9a-fA-F]{4})-([0-9a-fA-F]{4})"
    r"-([0-9a-fA-F]{4})-([0-9a-fA-F]{12})[}\]]?\b"
)
BARE_RE = re.compile(r"(?<![0-9a-fA-F-])([0-9a-fA-F]{32})(?![0-9a-fA-F-])")


def _canonical(h32: str) -> str:
    """32 位小写 hex -> 8-4-4-4-12 标准写法。"""
    return "%s-%s-%s-%s-%s" % (h32[0:8], h32[8:12], h32[12:16], h32[16:20], h32[20:32])


def version_of(h32: str) -> str:
    """按第 13 个 hex 位（版本号）归类：v1..v8，否则 unknown。"""
    v = h32[12]
    return "v" + v if v in "12345678" else "unknown"


def extract(text: str, bare: bool = False):
    """返回 (occurrences, [去重后 32 位小写 hex，按首次出现顺序])。"""
    seen, order, occurrences = set(), [], 0
    for pat in ([CANON_RE] + ([BARE_RE] if bare else [])):
        for m in pat.finditer(text):
            h = "".join(m.groups()).lower()
            occurrences += 1
            if h not in seen:
                seen.add(h)
                order.append(h)
    return occurrences, order


def _version_counts(hlist):
    counts = {}
    for h in hlist:
        v = version_of(h)
        counts[v] = counts.get(v, 0) + 1
    return counts


def render_text(occ, hlist):
    lines = ["occurrences: %d" % occ, "unique:      %d" % len(hlist)]
    counts = _version_counts(hlist)
    if counts:
        lines.append("by version (unique):")
        for name, cnt in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append("  %s: %d" % (name, cnt))
    if hlist:
        lines.append("unique uuids:")
        for h in hlist:
            lines.append("  %-8s%s" % (version_of(h), _canonical(h)))
    return "\n".join(lines)


def render_json(occ, hlist):
    payload = {
        "occurrences": occ,
        "unique": len(hlist),
        "versions": _version_counts(hlist),
        "uuids": [{"uuid": _canonical(h), "version": version_of(h)} for h in hlist],
    }
    return json.dumps(payload, indent=2)


def read_sources(paths):
    """无参数或 ['-'] 读 stdin，否则逐个读文件。"""
    texts = []
    if not paths or paths == ["-"]:
        texts.append(sys.stdin.read())
        return texts
    for p in paths:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            texts.append(f.read())
    return texts


def cmd_extract(args) -> int:
    try:
        texts = read_sources(args.files)
    except OSError as exc:
        print("error: cannot read input: %s" % exc, file=sys.stderr)
        return 2
    occ_total, hlist, seen = 0, [], set()
    for text in texts:
        occ, order = extract(text, bare=args.bare)
        occ_total += occ
        for h in order:
            if h not in seen:
                seen.add(h)
                hlist.append(h)
    print(render_json(occ_total, hlist) if args.json else render_text(occ_total, hlist))
    return 0


SAMPLE = "\n".join([
    "2026-11-02 10:00:00 INFO request id=3d813cbb-47fb-32ba-91df-831e1593ac29 user=alice",
    "2026-11-02 10:00:01 INFO job {06ba9ce6-8874-41d1-8fdf-4a1f0f5aa1e2} finished",
    "2026-11-02 10:00:02 WARN retry urn:uuid:550E8400-E29B-41D4-A716-446655440000",
    "2026-11-02 10:00:03 INFO request id=3d813cbb-47fb-32ba-91df-831e1593ac29 again",
    "2026-11-02 10:00:04 INFO trace 06ba9ce6-8874-41d1-8fdf-4a1f0f5aa1e2 done",
    "2026-11-02 10:00:05 INFO bare 3d813cbb47fb32ba91df831e1593ac29 (only with --bare)",
])


def cmd_selftest(_args) -> int:
    checks = []

    def check(name, cond):
        checks.append(bool(cond))
        print(("ok:   " if cond else "FAIL: ") + name)

    occ, hlist = extract(SAMPLE)
    check("default occurrences == 5", occ == 5)
    check("default unique == 3", len(hlist) == 3)
    check("versions are v3,v4,v4", sorted(version_of(h) for h in hlist) == ["v3", "v4", "v4"])
    canons = [_canonical(h) for h in hlist]
    check("uppercase/urn normalized to lowercase",
          "550e8400-e29b-41d4-a716-446655440000" in canons)
    check("duplicates deduped",
          canons.count("3d813cbb-47fb-32ba-91df-831e1593ac29") == 1)

    occ_b, hlist_b = extract(SAMPLE, bare=True)
    check("bare mode occurrences == 6", occ_b == 6)
    check("bare mode unique still 3 (bare hex is a dup)", len(hlist_b) == 3)
    payload = json.loads(render_json(occ_b, hlist_b))
    check("json render sane",
          payload["occurrences"] == 6 and payload["unique"] == 3
          and payload["versions"] == {"v3": 1, "v4": 2})

    occ_n, hlist_n = extract("no uuids here, just 12345 and abcdefgh")
    check("text without uuids finds nothing", occ_n == 0 and hlist_n == [])
    check("33 consecutive hex chars not matched", extract("f" * 33, bare=True) == (0, []))
    check("exact 32-hex matched only with --bare",
          extract("f" * 32) == (0, []) and extract("f" * 32, bare=True)[0] == 1)
    check("braced bare 32-hex matched",
          extract("{0123456789abcdef0123456789abcdef}", bare=True)[0] == 1)
    check("nil uuid version is unknown", version_of("0" * 32) == "unknown")

    total = len(checks)
    if all(checks):
        print("selftest ok (%d/%d checks)" % (total, total))
        return 0
    print("selftest FAILED (%d/%d checks failed)" % (checks.count(False), total))
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="uuid-extract.py",
        description="用正则从文本/日志中抽取所有 UUID，去重并按版本归类",
    )
    p.add_argument("files", nargs="*", help="输入文本文件（可多个）；省略或 '-' 表示 stdin")
    p.add_argument("--bare", action="store_true",
                   help="额外匹配 32 位无连字符 hex 的 UUID")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    p.add_argument("--selftest", action="store_true", help="运行内置自测后退出")
    p.set_defaults(func=cmd_extract)
    return p


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.selftest:
            return cmd_selftest(args)
        return args.func(args)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
