#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志时间时区修复（log-tz-fixer）：为日志文件中缺时区的时间戳补上指定时区并转换为 UTC。

对形如 2025-03-14 08:30:00(.毫秒) / 2025/03/14 8:30 且未带时区标记的时间戳，
按 --tz 指定的源时区解释，替换为 UTC ISO8601；已带 Z 或 ±HH:MM 后缀的时间戳原样保留。

用法:
  python log-tz-fixer.py app.log --tz +8
  python log-tz-fixer.py app.log --tz Asia/Shanghai --out fixed.log
  cat app.log | python log-tz-fixer.py - --tz +05:30
示例:
  echo "2025-03-14 08:30:00 INFO ready" | python log-tz-fixer.py - --tz +8
  # -> 2025-03-14T00:30:00+00:00 INFO ready
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone

# 不带时区的本地时间戳（后面紧跟 Z 或 ±HH:MM 的不匹配）
TS_RE = re.compile(
    r"\b(?P<ts>\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2}(?:[.,]\d{1,6})?)?)"
    r"(?![\d:Zz]|[+\-]\d{2}:?\d{2})"
)


def make_tz(spec: str):
    """把 +8 / -05:30 / UTC / Asia/Shanghai 之类的时区描述解析为 tzinfo。"""
    spec = spec.strip()
    if spec.upper() in ("UTC", "Z", "+00:00", "+0"):
        return timezone.utc
    m = re.fullmatch(r"(?:UTC|GMT)?([+-])(\d{1,2})(?::?(\d{2}))?", spec,
                     re.IGNORECASE)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        hh, mm = int(m.group(2)), int(m.group(3) or 0)
        if hh > 23 or mm > 59:
            raise ValueError(f"时区偏移超出范围: {spec!r}")
        return timezone(sign * timedelta(hours=hh, minutes=mm))
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(spec)
    except Exception as exc:
        raise ValueError(
            f"无法识别时区 {spec!r}（可写 +8、-05:30；IANA 名称如 Asia/Shanghai "
            f"在 Windows 上需安装 tzdata 包）") from exc


def fix_line(line: str, tz) -> tuple[str, int]:
    """替换一行中所有缺时区的时间戳，返回 (新行, 替换个数)。"""
    count = 0

    def repl(m):
        nonlocal count
        raw = m.group("ts")
        txt = raw.replace("/", "-").replace("T", " ").replace(",", ".")
        frac = ""
        if "." in txt:
            txt, _, frac = txt.partition(".")
            frac = "." + frac
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(txt.strip(), fmt)
                break
            except ValueError:
                continue
        if dt is None:
            return raw
        count += 1
        out = dt.replace(tzinfo=tz).astimezone(timezone.utc)
        return out.strftime("%Y-%m-%dT%H:%M:%S") + frac + "+00:00"

    return TS_RE.sub(repl, line), count


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="日志时间时区修复：为日志中缺时区的时间戳补上指定时区并转换为 UTC。")
    ap.add_argument("file", help="日志文件路径；- 表示读 stdin")
    ap.add_argument("--tz", default="+8",
                    help="源时区：+8 / -05:30 / Asia/Shanghai（默认 +8）")
    ap.add_argument("--out", help="输出文件（默认写到 stdout）")
    args = ap.parse_args(argv)

    try:
        tz = make_tz(args.tz)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    if args.file == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print(f"错误：无法读取文件 {args.file!r}: {exc}", file=sys.stderr)
            return 2

    total = 0
    fixed_lines = []
    for line in text.splitlines():
        new, n = fix_line(line, tz)
        total += n
        fixed_lines.append(new)
    result = "\n".join(fixed_lines) + ("\n" if text.endswith("\n") or fixed_lines else "")

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(result)
        except OSError as exc:
            print(f"错误：无法写入文件 {args.out!r}: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(result)
    if total:
        print(f"# 已转换 {total} 个时间戳（源时区 {args.tz} -> UTC）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
