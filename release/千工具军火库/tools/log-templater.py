"""日志模式聚合：把日志中数字/ID/时间归一为模板行，按模板聚合计数找出高频模式。

功能：
  - 将每行日志中的 IPv4、十六进制 ID（0x…/长 hex）、时间戳（ISO/常见格式）、
    数字、UUID、加引号的字符串替换为占位符 <NUM> <ID> <TIME> <UUID> <STR>
  - 以归一化后的模板为 key 聚合计数，输出 Top N 高频模板
  - 每个模板附带一条原始示例行与行号（1-based）

示例命令：
  python log-templater.py app.log
  python log-templater.py app.log --top 20 --mask-str
  python log-templater.py app.log -o patterns.md

参数：
  file                 输入日志文件
  --top N              输出前 N 个高频模板（默认 15）
  --mask-str           同时把引号内字符串归一为 <STR>（默认关闭）
  --encoding ENC       输入编码（默认 utf-8，容错 replace）
"""
import argparse
import re
import sys
from collections import Counter

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b")
HEX_RE = re.compile(r"\b0[xX][0-9a-fA-F]+\b|\b[0-9a-fA-F]{12,}\b")
TIME_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
    r"|\d{2}:\d{2}:\d{2}(?:[.,]\d+)?"
    r"|\d{4}/\d{2}/\d{2}[- ]?\d{0,2}:?\d{0,2}:?\d{0,2}"
    r"|\d{10,13}\b"            # unix 时间戳（秒/毫秒）
)
STR_RE = re.compile(r'"[^"]*"|\'[^\']*\'')
NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


def templaterize(line, mask_str=True):
    s = line
    s = UUID_RE.sub("<UUID>", s)
    s = TIME_RE.sub("<TIME>", s)
    s = IP_RE.sub("<IP>", s)
    s = HEX_RE.sub("<ID>", s)
    if mask_str:
        s = STR_RE.sub("<STR>", s)
    s = NUM_RE.sub("<NUM>", s)
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description="日志模板归一与高频模式聚合")
    ap.add_argument("file", help="输入日志文件")
    ap.add_argument("--top", type=int, default=15, help="输出前 N 个模板（默认 15）")
    ap.add_argument("--mask-str", action="store_true", help="同时归一引号内字符串")
    ap.add_argument("--encoding", default="utf-8", help="输入编码（默认 utf-8）")
    ap.add_argument("-o", "--output", help="输出文件（默认 stdout）")
    args = ap.parse_args(argv)

    counts = Counter()
    examples = {}
    total = 0
    with open(args.file, encoding=args.encoding, errors="replace") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            total += 1
            tpl = templaterize(line, args.mask_str)
            counts[tpl] += 1
            if tpl not in examples:
                examples[tpl] = (lineno, line)

    lines = ["# 日志模式聚合报告", "", f"- 文件：`{args.file}`",
             f"- 有效行数：{total}", f"- 模板数：{len(counts)}", "",
             f"## 高频模板 Top {args.top}", ""]
    for tpl, c in counts.most_common(args.top):
        lineno, ex = examples[tpl]
        pct = (c / total * 100) if total else 0.0
        lines.append(f"## [{c:>5} 行 | {pct:5.1f}%] {tpl}")
        lines.append(f"    示例 L{lineno}: {ex[:200]}")
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
