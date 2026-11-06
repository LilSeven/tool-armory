#!/usr/bin/env python3
"""词频统计（中英混排）：英文按单词统计，中文按双字组合（bigram）统计，输出 Top-N 表格。

用法:
    python word-freq.py -n 10 article.txt
    python word-freq.py a.txt b.txt -n 20 --min-count 2
    cat article.txt | python word-freq.py -n 15

规则:
    英文串（[A-Za-z']+）小写后按词计数；
    连续汉字串按重叠双字组合计数（如 "中文测试" -> 中文/文文/文测/测试），
    孤立单字按单字计数。
输出:
    排名  词  频次  占比 的对齐表格（中文按 2 倍宽度对齐）。
"""
import argparse
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

EN_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
CN_RUN = re.compile(r"[\u4e00-\u9fff]+")


def display_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - display_width(s))


def count_words(text: str) -> Counter:
    cnt = Counter()
    for m in EN_WORD.finditer(text):
        cnt[m.group(0).lower()] += 1
    # 把英文段替换为空格，避免中英文粘连影响中文切分
    bare = EN_WORD.sub(" ", text)
    for m in CN_RUN.finditer(bare):
        run = m.group(0)
        if len(run) == 1:
            cnt[run] += 1
        else:
            for i in range(len(run) - 1):
                cnt[run[i:i + 2]] += 1
    return cnt


def main() -> int:
    ap = argparse.ArgumentParser(
        description="中英混排词频统计：英文按词、中文按双字组合，输出 Top-N 表格。")
    ap.add_argument("files", nargs="*", metavar="FILE",
                    help="输入文件；缺省或 '-' 为 stdin")
    ap.add_argument("-n", "--top", type=int, default=20, help="显示前 N 项（默认 20）")
    ap.add_argument("--min-count", type=int, default=1, help="只显示频次 >= 该值的项（默认 1）")
    ap.add_argument("--encoding", default="utf-8", help="输入编码（默认 utf-8）")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding=args.encoding, errors="replace")
    except Exception:
        pass

    texts = []
    paths = args.files or ["-"]
    for p in paths:
        if p == "-":
            texts.append(sys.stdin.read())
        else:
            fp = Path(p)
            if not fp.is_file():
                ap.error(f"不是文件: {p}")
            texts.append(fp.read_text(encoding=args.encoding, errors="replace"))

    cnt = Counter()
    for t in texts:
        cnt.update(count_words(t))

    total = sum(cnt.values())
    items = [(w, c) for w, c in cnt.most_common()
             if c >= args.min_count][: max(0, args.top)]

    w1, w2, w3 = len("排名"), len("词"), len("频次")
    rows = []
    for i, (w, c) in enumerate(items, 1):
        rows.append((str(i), w, str(c), f"{c / total * 100:.2f}%" if total else "-"))
        w1 = max(w1, display_width(str(i)))
        w2 = max(w2, display_width(w))
        w3 = max(w3, display_width(str(c)))
    w4 = len("占比")
    header = (pad("排名", w1), pad("词", w2), pad("频次", w3), "占比")
    sep = "-+-".join("-" * w for w in (w1, w2, w3, w4))
    print(f"{header[0]} | {header[1]} | {header[2]} | {header[3]}")
    print(sep)
    for r in rows:
        print(f"{pad(r[0], w1)} | {pad(r[1], w2)} | {pad(r[2], w3)} | {r[3]}")
    print(f"{sep}")
    print(f"共 {total} 个计次单元，{len(cnt)} 个不同词条" + (f"，显示前 {len(rows)} 项" if rows else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
