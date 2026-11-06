#!/usr/bin/env python3
"""近似重复检测（near-dupe）——用 difflib 序列相似度找出文本中内容高度相近的行对。

功能：
  - 对文件（或 stdin）中所有非空行两两计算 difflib.SequenceMatcher 相似度
  - 相似度 >= --threshold（默认 0.85）的行对按分数降序输出
  - --limit 限制最多输出多少对；--min-len 忽略过短行；--max-lines 超过时直接拒绝
    （两两比较为 O(n^2)，默认上限 2000 行，可用 --max-lines 调整）

用法示例：
  python near-dupe.py input.txt
  python near-dupe.py --threshold 0.9 --limit 20 input.txt
  cat input.txt | python near-dupe.py --threshold 0.8

输出格式（TSV）：相似度<TAB>行号A:文本A<TAB>行号B:文本B

退出码：0 成功；1 输入文件不存在等错误；2 参数错误；3 行数超出 --max-lines。
"""
import argparse
import difflib
import sys

def read_text(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        return f.read()

def main(argv=None):
    p = argparse.ArgumentParser(description="用序列相似度找出内容高度相近的行对并输出阈值过滤报告")
    p.add_argument("input", nargs="?", default="-", help="输入文件，缺省为 stdin（'-'）")
    p.add_argument("-o", "--output", default="-", help="报告输出文件，缺省为 stdout（'-'）")
    p.add_argument("--threshold", type=float, default=0.85, help="相似度阈值 0~1（默认 0.85）")
    p.add_argument("--limit", type=int, default=50, help="最多输出的行对数量（默认 50）")
    p.add_argument("--min-len", type=int, default=4, help="忽略长度小于该值的行（默认 4）")
    p.add_argument("--max-lines", type=int, default=2000, help="参与比较的最大行数（默认 2000）")
    args = p.parse_args(argv)

    if not (0.0 <= args.threshold <= 1.0):
        print("错误: --threshold 必须在 0~1 之间", file=sys.stderr)
        return 2
    if args.limit < 1 or args.min_len < 0 or args.max_lines < 2:
        print("错误: --limit >= 1, --min-len >= 0, --max-lines >= 2", file=sys.stderr)
        return 2
    try:
        text = read_text(args.input)
    except OSError as e:
        print(f"错误: 无法读取 {args.input}: {e}", file=sys.stderr)
        return 1

    lines = text.split("\n")
    # 收集参与比较的行：去行尾 \r（兼容 CRLF）、去首尾空白、跳过空行与过短行
    cand = []
    for idx, ln in enumerate(lines, 1):
        s = ln.strip()
        if len(s) < args.min_len:
            continue
        cand.append((idx, s))
    if len(cand) > args.max_lines:
        print(f"错误: 参与比较的行有 {len(cand)} 行，超过 --max-lines {args.max_lines}", file=sys.stderr)
        return 3

    pairs = []
    for i in range(len(cand)):
        idx_a, a = cand[i]
        for j in range(i + 1, len(cand)):
            idx_b, b = cand[j]
            ratio = difflib.SequenceMatcher(None, a, b).ratio()
            if ratio >= args.threshold:
                pairs.append((ratio, idx_a, a, idx_b, b))
    pairs.sort(key=lambda t: (-t[0], t[1], t[3]))
    pairs = pairs[: args.limit]

    report_lines = [f"{r:.4f}\t{ia}:{a}\t{ib}:{b}" for r, ia, a, ib, b in pairs]
    report = "\n".join(report_lines)
    if args.output == "-":
        if report:
            out = getattr(sys.stdout, "buffer", None)
            data = report.encode(sys.stdout.encoding or "utf-8", errors="replace")
            if out is not None:
                out.write(data + b"\n")
                out.flush()
            else:
                print(report)
        print(f"共 {len(cand)} 行参与比较，{len(pairs)} 对达到阈值 {args.threshold}", file=sys.stderr)
    else:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(report + ("\n" if report else ""))
        print(f"共 {len(cand)} 行参与比较，{len(pairs)} 对达到阈值 {args.threshold}，报告已写入 {args.output}",
              file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
