#!/usr/bin/env python3
"""csv-redelim.py -- 在 CSV/TSV/竖线/分号等任意分隔符之间转换。

读取输入文件（或 stdin），用源分隔符解析，再用目标分隔符输出；
含目标分隔符、引号或换行的字段会自动加引号（RFC 4180 风格）。

用法:
    python csv-redelim.py INPUT -t "," [-s ";"] [-o OUT] [-e ENCODING]
    python csv-redelim.py INPUT --to tsv
    cat data.csv | python csv-redelim.py - --to "|"

参数:
    INPUT              输入文件路径；为 "-" 时读取 stdin
    -t, --to           目标分隔符（单字符，或逗号/tab/space 等别名）
    -s, --sep          源分隔符，默认自动探测（, \\t ; | 之一）
    -o, --output       输出文件路径，缺省写 stdout
    -e, --encoding     文件编码，默认 utf-8（可用 utf-8-sig 兼容 BOM）
    --no-quote         即使字段含特殊字符也不加引号（默认自动加引号）
    --quote-all        所有字段一律加引号

示例:
    python csv-redelim.py data.csv -t ";"          # CSV -> 分号分隔
    python csv-redelim.py report.tsv --to csv -o out.csv
"""
import argparse
import csv
import io
import sys

ALIASES = {
    "comma": ",", "csv": ",", ",": ",",
    "tab": "\t", "tsv": "\t", "\\t": "\t",
    "pipe": "|", "bar": "|", "|": "|",
    "semicolon": ";", ";": ";",
    "colon": ":", ":": ":",
    "space": " ", " ": " ",
}


def resolve_delim(text: str) -> str:
    """把别名或单字符解析为实际分隔符。"""
    key = text.lower() if len(text) != 1 else text
    if key in ALIASES:
        return ALIASES[key]
    if len(text) == 1 and text.isprintable() and text not in ('"', "'"):
        return text
    raise SystemExit(f"错误: 无法识别的分隔符 {text!r}（可用单字符或别名: "
                     f"comma/tab/pipe/semicolon/colon/space）")


def detect_delim(sample_lines):
    """在前几行中统计候选分隔符出现次数，选最少被引号包裹、出现最多者。"""
    cands = [",", "\t", ";", "|"]
    scores = {c: 0 for c in cands}
    in_quote = False
    for line in sample_lines:
        for ch in line:
            if ch == '"':
                in_quote = not in_quote
            elif ch in scores and not in_quote:
                scores[ch] += 1
        in_quote = False
    best = max(cands, key=lambda c: scores[c])
    if scores[best] == 0:
        raise SystemExit("错误: 无法自动探测源分隔符，请用 -s 指定")
    return best


def main():
    ap = argparse.ArgumentParser(
        description="在任意分隔符（CSV/TSV/竖线/分号等）之间转换，自动加引号")
    ap.add_argument("input", help="输入文件路径，或 '-' 表示 stdin")
    ap.add_argument("-t", "--to", dest="to", required=True, help="目标分隔符")
    ap.add_argument("-s", "--sep", help="源分隔符，缺省自动探测")
    ap.add_argument("-o", "--output", help="输出文件，缺省 stdout")
    ap.add_argument("-e", "--encoding", default="utf-8")
    ap.add_argument("--no-quote", action="store_true",
                    help="不自动加引号（字段仍按原样输出）")
    ap.add_argument("--quote-all", action="store_true",
                    help="所有字段一律加引号")
    args = ap.parse_args()

    out_delim = resolve_delim(args.to)

    # 读输入
    if args.input == "-":
        data = sys.stdin.buffer.read()
    else:
        try:
            with open(args.input, "rb") as f:
                data = f.read()
        except OSError as exc:
            raise SystemExit(f"错误: 无法读取 {args.input}: {exc}")

    text = data.decode(args.encoding)
    lines = text.splitlines()
    lines = [ln for ln in lines if ln != "" or True]  # 保留空行处理交给 csv
    lines = [ln for ln in lines if ln.strip() != ""]  # 跳过纯空行

    src_delim = resolve_delim(args.sep) if args.sep else detect_delim(lines[:50])

    rows = list(csv.reader(lines, delimiter=src_delim, quotechar='"'))

    # 输出
    if args.no_quote:
        for row in rows:
            for fld in row:
                if out_delim in fld or '"' in fld or "\n" in fld:
                    raise SystemExit(
                        f"错误: --no-quote 模式下字段 {fld!r} 含分隔符/引号/换行，"
                        f"无法安全输出，请去掉 --no-quote")
        out = "".join(out_delim.join(row) + "\n" for row in rows)
    else:
        quoting = csv.QUOTE_ALL if args.quote_all else csv.QUOTE_MINIMAL
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=out_delim, quoting=quoting,
                            lineterminator="\n")
        for row in rows:
            writer.writerow(row)
        out = buf.getvalue()

    if args.output:
        with open(args.output, "w", encoding=args.encoding, newline="") as f:
            f.write(out)
        print(f"已写入 {args.output}（{len(rows)} 行，源分隔符 {src_delim!r} "
              f"-> 目标 {out_delim!r}）", file=sys.stderr)
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
