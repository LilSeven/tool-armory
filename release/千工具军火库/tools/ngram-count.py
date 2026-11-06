#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N-gram 计数（ngram-count）：对文本生成字符级或词级 N-gram 并按频次排序输出。

输入：文件参数或 stdin。字符级 N-gram 按连续字符滑动取窗；词级先用简单规则
切词（英文按空白/标点，中文按单字成词）再组合成词 N-gram。

用法示例：
    python -I ngram-count.py --n 2 sample.txt
    python -I ngram-count.py --n 3 --mode word --top 10 sample.txt
    cat sample.txt | python -I ngram-count.py --n 2

选项：
    -f, --file PATH    输入文件（缺省读 stdin）
    -n, --ngram N      N-gram 的 N（默认 2）
    --mode {char,word} 字符级或词级（默认 char）
    --top N            只显示前 N 个（默认 20，0 为全部）
    --min N            过滤掉频次小于 N 的项
    --csv              以 CSV 格式输出
"""
import argparse
import re
import sys


def read_text(path: str | None) -> str:
    if path and path != "-":
        with open(path, "rb") as fh:
            data = fh.read()
    else:
        data = sys.stdin.buffer.read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def tokenize(text: str) -> list[str]:
    """简单分词：英文/数字串成一个词，中日韩每个字一个词。"""
    tokens: list[str] = []
    for word in re.findall(r"[A-Za-z0-9']+|[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]|[^\sA-Za-z0-9\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", text):
        tokens.append(word)
    return tokens


def main() -> int:
    ap = argparse.ArgumentParser(description="对文本生成 N-gram 并按频次排序输出")
    ap.add_argument("file", nargs="?", default="-", help="输入文件，缺省或 '-' 为 stdin")
    ap.add_argument("-n", "--ngram", type=int, default=2, metavar="N", help="N 值（默认 2）")
    ap.add_argument("--mode", choices=("char", "word"), default="char", help="字符级/词级")
    ap.add_argument("--top", type=int, default=20, metavar="N", help="显示前 N 个，0 为全部")
    ap.add_argument("--min", type=int, default=1, metavar="N", help="最小频次")
    ap.add_argument("--csv", action="store_true", help="输出 CSV")
    args = ap.parse_args()

    if args.ngram < 1:
        print("错误：--n 必须 >= 1", file=sys.stderr)
        return 2

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    text = read_text(args.file)
    units = list(text) if args.mode == "char" else tokenize(text)
    units = [u for u in units if not u.isspace()]
    if args.mode == "word":
        units = [u for u in units if u.isalnum() or "'" in u]

    counter: dict[str, int] = {}
    sep = "" if args.mode == "char" else " "
    for i in range(len(units) - args.ngram + 1):
        gram = sep.join(units[i:i + args.ngram])
        counter[gram] = counter.get(gram, 0) + 1

    total = sum(counter.values())
    items = [(g, c) for g, c in counter.items() if c >= args.min]
    items.sort(key=lambda kv: (-kv[1], kv[0]))
    shown = items if args.top == 0 else items[:args.top]

    if not shown:
        print(f"（无满足条件的 {args.ngram}-gram，单位总数={len(units)}）")
        return 0

    if args.csv:
        print("ngram,count")
        for g, c in shown:
            print(f'"{g}",{c}')
    else:
        print(f"[{args.ngram}-gram 计数] 模式={args.mode}  N-gram 总数={total}  "
              f"不同={len(counter)}  显示={len(shown)}")
        width = max(4, args.ngram)
        print(f"{'N-gram':<{width + 2}}{'频次':>8}{'占比':>10}")
        for g, c in shown:
            disp = g if g.isprintable() else repr(g)[1:-1]
            print(f"{disp:<{width + 2}}{c:>8}{c * 100.0 / total:>9.2f}%")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
