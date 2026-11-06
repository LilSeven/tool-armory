"""日志级别统计：统计日志中 INFO/WARN/ERROR 等级别分布与时间跨度，按级别抽样示例行。

功能：
  - 识别常见级别词（TRACE/DEBUG/INFO/NOTICE/WARN/WARNING/ERROR/FATAL/CRITICAL）
  - 输出各级别条数与占比，识别不出的行计入 OTHER
  - 从行首/行内提取时间戳计算时间跨度（min..max）
  - 每个级别抽样 --samples 条示例（首条 + 均匀抽样）

示例命令：
  python log-level-stat.py app.log
  python log-level-stat.py app.log --samples 3 --pattern "\\[(\\w+)\\]"
  python log-level-stat.py app.log -o stat.md

参数：
  file                 输入日志文件
  --samples N          每级别抽样示例行数（默认 3）
  --pattern REGEX      自定义级别提取正则（需含 1 个捕获组；默认匹配常见级别词）
  --encoding ENC       输入编码（默认 utf-8，容错 replace）
"""
import argparse
import re
import sys
from collections import Counter
from datetime import datetime

DEFAULT_PATTERN = r"\b(TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|ERR|FATAL|CRITICAL)\b"
LEVEL_NORM = {"WARNING": "WARN", "ERR": "ERROR"}
TIME_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
    r"|(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"
)
TIME_FMTS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"]


def parse_time(line):
    m = TIME_RE.search(line)
    if not m:
        return None
    s = m.group(1) or m.group(2)
    s = s.split(",")[0].split(".")[0].rstrip("Z")
    s = re.sub(r"[+-]\d{2}:?\d{2}$", "", s).replace("T", " ")
    for fmt in TIME_FMTS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="日志级别分布与时间跨度统计，按级别抽样")
    ap.add_argument("file", help="输入日志文件")
    ap.add_argument("--samples", type=int, default=3, help="每级别抽样示例行数（默认 3）")
    ap.add_argument("--pattern", default=DEFAULT_PATTERN, help="级别提取正则（1 个捕获组）")
    ap.add_argument("--encoding", default="utf-8", help="输入编码（默认 utf-8）")
    ap.add_argument("-o", "--output", help="输出文件（默认 stdout）")
    args = ap.parse_args(argv)

    lv_re = re.compile(args.pattern, re.IGNORECASE)
    counter = Counter()
    samples = {}
    tmin = tmax = None
    total = 0

    with open(args.file, encoding=args.encoding, errors="replace") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            total += 1
            m = lv_re.search(line)
            level = m.group(1).upper() if m else "OTHER"
            level = LEVEL_NORM.get(level, level)
            counter[level] += 1
            samples.setdefault(level, []).append(line)
            t = parse_time(line)
            if t:
                tmin = t if tmin is None else min(tmin, t)
                tmax = t if tmax is None else max(tmax, t)

    lines = ["# 日志级别统计报告", "", f"- 文件：`{args.file}`", f"- 有效行数：{total}"]
    if tmin and tmax:
        span = tmax - tmin
        h, rem = divmod(int(span.total_seconds()), 3600)
        mn = rem // 60
        lines += [f"- 时间跨度：{tmin} ~ {tmax}（共 {h}h{mn}m）"]
    else:
        lines.append("- 时间跨度：未识别到时间戳")
    lines += ["", "## 级别分布", "", "| 级别 | 条数 | 占比 |", "|---|---|---|"]
    for lv, c in counter.most_common():
        lines.append(f"| {lv} | {c} | {(c / total * 100 if total else 0):.1f}% |")

    lines += ["", "## 按级别抽样示例"]
    for lv in counter:
        pool = samples[lv]
        if args.samples >= len(pool):
            picked = pool[:args.samples]
        else:
            step = len(pool) / args.samples
            picked = [pool[int(i * step)] for i in range(args.samples)]
        lines += [f"### {lv}（{counter[lv]} 条，抽样 {len(picked)} 条）"]
        for p in picked[:args.samples]:
            lines.append(f"    {p[:200]}")
        lines.append("")
    report = "\n".join(lines).rstrip() + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"report written: {args.output}")
    else:
        sys.stdout.write(report)


if __name__ == "__main__":
    main()
