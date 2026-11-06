#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实体提取器 (extract-entities)。

用途:
    从文本(文件或 stdin)中批量提取 URL、邮箱、IPv4 地址、中国大陆手机号、
    十六进制色值等实体，按类型去重并导出为 JSON / CSV / TXT / table。

示例命令:
    python -I extract-entities.py page.html
    python -I extract-entities.py notes.txt --types url,email,phone
    cat raw.txt | python -I extract-entities.py -o out.json --format json
    python -I extract-entities.py --self-test
"""
import argparse
import csv
import io
import json
import re
import sys
from collections import OrderedDict

# ---------- 正则 ----------
RE_URL = re.compile(r"""https?://[A-Za-z0-9\-._~%]+(?::\d{2,5})?(?:/[^\s<>"'\)\]`,;]*)?(?:\?[^\s<>"'\)\]`,;]*)?(?:#[^\s<>"'\)\]`,;]*)?""", re.I)
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
RE_IPV4 = re.compile(
    r"(?<![\w.])(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    r"\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    r"\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    r"\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?!\.?\d)")
RE_PHONE = re.compile(r"(?<![\d\-])1[3-9]\d{9}(?!\d)")
RE_HEXCOLOR = re.compile(r"(?<![0-9A-Fa-f])#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})(?![0-9A-Fa-f])")

TYPES = OrderedDict([
    ("url", ("URL", RE_URL)),
    ("email", ("邮箱", RE_EMAIL)),
    ("ipv4", ("IPv4", RE_IPV4)),
    ("phone", ("手机号", RE_PHONE)),
    ("color", ("十六进制色值", RE_HEXCOLOR)),
])
TRAIL_PUNCT = ".,;:!?）】》\"'"


def _clean_url(u: str) -> str:
    while u and u[-1] in TRAIL_PUNCT:
        u = u[:-1]
    return u


def extract(text: str, types) -> "OrderedDict[str, list]":
    """返回 {type: [去重后的实体, ...]}，保持首次出现顺序。"""
    out = OrderedDict()
    for key in types:
        label, rx = TYPES[key]
        seen, items = set(), []
        for m in rx.finditer(text):
            val = m.group(0)
            if key == "url":
                val = _clean_url(val)
            if val not in seen:
                seen.add(val)
                items.append(val)
        out[key] = items
    return out


def render_table(result) -> str:
    lines = []
    for key, items in result.items():
        lines.append(f"## {key} ({TYPES[key][0]}) x{len(items)}")
        lines.extend(f"  {v}" for v in items)
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="批量提取文本实体并去重导出")
    ap.add_argument("input", nargs="?", help="输入文件；缺省或为 - 时读 stdin")
    ap.add_argument("-o", "--output", help="输出文件（缺省 stdout）")
    ap.add_argument("--format", choices=["json", "csv", "txt", "table"],
                    default=None, help="输出格式；缺省按 -o 扩展名推断，否则 table")
    ap.add_argument("--types", default="url,email,ipv4,phone,color",
                    help="逗号分隔的实体类型: " + ",".join(TYPES))
    ap.add_argument("--self-test", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)

    if args.self_test:
        sample = ("Visit https://example.com/a?b=1 and http://foo.bar/baz. "
                  "Mail bob@example.com / alice@test.cn. "
                  "IPs 192.168.1.1 256.0.0.1 10.0.0.2. "
                  "Phones 13812345678, 12345. Colors #FFAA00 #abc #GGGGGG.")
        r = extract(sample, ["url", "email", "ipv4", "phone", "color"])
        assert r["url"] == ["https://example.com/a?b=1", "http://foo.bar/baz"], r["url"]
        assert r["email"] == ["bob@example.com", "alice@test.cn"], r["email"]
        assert r["ipv4"] == ["192.168.1.1", "10.0.0.2"], r["ipv4"]  # 256 段被排除
        assert r["phone"] == ["13812345678"], r["phone"]
        assert r["color"] == ["#FFAA00", "#abc"], r["color"]       # #GGGGGG 排除
        # 去重检查 + 版本号样式的串不被误当 IP
        r2 = extract("a@b.com a@b.com 1.2.3.4 1.2.3.4 ver 1.2.3.4.5", ["email", "ipv4"])
        assert r2["email"] == ["a@b.com"] and r2["ipv4"] == ["1.2.3.4"], r2["ipv4"]
        print("self-test OK")
        return 0

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    for t in types:
        if t not in TYPES:
            ap.error(f"未知类型: {t}（可选: {','.join(TYPES)}）")

    if args.input and args.input != "-":
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        text = sys.stdin.read()

    result = extract(text, types)

    fmt = args.format
    if fmt is None:
        if args.output and args.output.lower().endswith(".json"):
            fmt = "json"
        elif args.output and args.output.lower().endswith(".csv"):
            fmt = "csv"
        else:
            fmt = "table"

    out = io.StringIO()
    if fmt == "json":
        out.write(json.dumps({k: v for k, v in result.items()},
                             ensure_ascii=False, indent=2))
    elif fmt == "csv":
        w = csv.writer(out)
        w.writerow(["type", "value"])
        for k, items in result.items():
            w.writerows([k, v] for v in items)
    elif fmt == "txt":
        for items in result.values():
            out.write("\n".join(items) + ("\n" if items else ""))
    else:
        out.write(render_table(result))

    text_out = out.getvalue()
    if args.output:
        with open(args.output, "w", encoding="utf-8-sig" if fmt == "csv" else "utf-8") as f:
            f.write(text_out)
        total = sum(len(v) for v in result.values())
        print(f"[extract-entities] 导出 {total} 个实体 -> {args.output} ({fmt})", file=sys.stderr)
    else:
        sys.stdout.write(text_out if text_out.endswith("\n") or not text_out else text_out + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
