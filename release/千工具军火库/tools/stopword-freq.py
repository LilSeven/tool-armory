#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""停用词过滤词频（stopword-freq）：内置中英停用词表的词频统计。

支持通过 --stop 追加自定义停用词文件（每行一个词，# 开头为注释），
通过 --keep 指定保留词文件（其中的词即使命中停用词表也保留）。

用法示例：
    python -I stopword-freq.py sample.txt
    python -I stopword-freq.py --top 15 --stop mystop.txt sample.txt
    python -I stopword-freq.py --no-builtin --stop cn.txt sample.txt
    cat sample.txt | python -I stopword-freq.py

选项：
    -f, --file PATH    输入文件（缺省读 stdin）
    --stop PATH        附加停用词文件（每行一词，# 注释）
    --keep PATH        保留词文件（优先于停用词）
    --no-builtin       不使用内置停用词表
    --keep-punct       不过滤标点与空白 token
    --top N            只显示前 N 个（默认 30，0 为全部）
    --csv              以 CSV 格式输出

分词说明：英文按连续字母/数字切；连续中文段先按停用词/保留词表做
最长匹配（可切出"春天"这类多字词），无命中时回退为单字。
"""
import argparse
import re
import sys

BUILTIN_CN = (
    "的 了 和 是 就 都 而 及 与 着 或 一个 没有 我们 你们 他们 它 她 他 你 我 也要 有 在 "
    "不 也 很 到 说 要 去 你会 着 看 好 自己 这 那 之 与 及 其 或 者 但 等 更 已 为 以 于 从 "
    "被 把 让 向 往 按 照 本 该 各 每 某 些 什么 怎么 哪 这那 这么 那么 这些 那些 因此 所以 "
    "因为 如果 虽然 但是 然而 并且 而且 不过 然后 于是 关于 对于 由于 通过 根据 按照 作为 "
    "可以 能够 应该 需要 可能 会 想 觉得 知道 现在 时候 一直 已经 还是 还是 这个 那个"
).split()

BUILTIN_EN = """a about above after again against all am an and any are aren as at be
because been before being below between both but by can cannot could couldn did didn do does
doesn doing don down during each few for from further had hadn has hasn have haven having he
her here hers herself him himself his how i if in into is isn it its itself just ll me more
most mustn my myself no nor not now of off on once only or other ought our ours ourselves out
over own re s same shan she should shouldn so some such t than that the their theirs them
themselves then there these they this those through to too under until up ve very was wasn we
were weren what when where which while who whom why will with won would wouldn you your yours
yourself yourselves""".split()


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


def read_wordlist(path: str) -> set[str]:
    with open(path, "rb") as fh:
        data = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    words = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        words.update(line.split())
    return words


def tokenize(text: str, keep_punct: bool, cn_lexicon: set[str] | None = None) -> list[str]:
    """英文按词、中文按词典最长匹配（回退单字）、标点单独成 token。"""
    if keep_punct:
        return [t for t in re.split(r"\s+", text) if t]
    tokens: list[str] = []
    for m in re.finditer(
            r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*|[\u4e00-\u9fff]+|"
            r"[^\sA-Za-z0-9\u4e00-\u9fff]", text):
        seg = m.group(0)
        if len(seg) == 1 or not ("\u4e00" <= seg[0] <= "\u9fff"):
            tokens.append(seg)
            continue
        lex = cn_lexicon or set()
        i = 0
        while i < len(seg):
            for length in range(min(8, len(seg) - i), 1, -1):
                w = seg[i:i + length]
                if w in lex:
                    tokens.append(w)
                    i += length
                    break
            else:
                tokens.append(seg[i])
                i += 1
    return tokens


def main() -> int:
    ap = argparse.ArgumentParser(description="内置中英停用词表的词频统计")
    ap.add_argument("file", nargs="?", default="-", help="输入文件，缺省或 '-' 为 stdin")
    ap.add_argument("--stop", metavar="PATH", help="附加停用词文件")
    ap.add_argument("--keep", metavar="PATH", help="保留词文件（优先于停用词）")
    ap.add_argument("--no-builtin", action="store_true", help="不使用内置停用词表")
    ap.add_argument("--keep-punct", action="store_true", help="不过滤标点/空白 token")
    ap.add_argument("--top", type=int, default=30, metavar="N", help="显示前 N 个，0 为全部")
    ap.add_argument("--csv", action="store_true", help="输出 CSV")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    text = read_text(args.file)

    stopwords: set[str] = set()
    if not args.no_builtin:
        stopwords.update(BUILTIN_CN)
        stopwords.update(BUILTIN_EN)
    if args.stop:
        stopwords.update(read_wordlist(args.stop))
    keep: set[str] = set()
    if args.keep:
        keep = read_wordlist(args.keep)

    # 中文多字词词典：停用词 + 保留词中长度>=2 的纯中文词
    cn_lexicon = {w for w in (stopwords | keep)
                  if len(w) >= 2 and all("\u4e00" <= c <= "\u9fff" for c in w)}
    tokens = tokenize(text, args.keep_punct, cn_lexicon)

    counter: dict[str, int] = {}
    filtered = 0
    for tok in tokens:
        low = tok.lower()
        if not args.keep_punct and not tok.isalnum():
            filtered += 1
            continue
        if low in keep:
            pass
        elif low in stopwords:
            filtered += 1
            continue
        counter[tok] = counter.get(tok, 0) + 1

    total = sum(counter.values())
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = items if args.top == 0 else items[:args.top]

    if args.csv:
        print("word,count")
        for w, c in shown:
            print(f'"{w}",{c}')
        return 0

    print(f"[停用词过滤词频] token 总数={len(tokens)}  保留={total}  过滤={filtered}  "
          f"停用词表={'关闭' if args.no_builtin else f'{len(stopwords)} 个词'}")
    if not shown:
        print("（无保留词）")
        return 0
    width = max(6, max(len(w) for w, _ in shown))
    print(f"{'词':<{width}}{'频次':>8}{'占比':>10}")
    for w, c in shown:
        print(f"{w:<{width}}{c:>8}{c * 100.0 / total:>9.2f}%")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
