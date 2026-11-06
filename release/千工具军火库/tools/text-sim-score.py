#!/usr/bin/env python3
"""相似度评分：用 difflib SequenceMatcher 与字符 Jaccard 给两段文本打相似度分数，
并标出关键差异行。

用法:
    python text-sim-score.py <文件A> <文件B> [--out FILE]
    python text-sim-score.py --text "hello world" --text2 "hello word"

示例:
    python text-sim-score.py a.txt b.txt
    python text-sim-score.py --text "aaa bbb" --text2 "aaa ccc"
"""
import argparse
import difflib
import sys


def char_jaccard(a, b):
    sa = set(a)
    sb = set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def key_differences(a_lines, b_lines, ratio_threshold=0.6):
    """标出关键差异：只能在一侧找到的行，以及相似度低的替换对。"""
    result = []
    sm = difflib.SequenceMatcher(None, a_lines, b_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        a_frag = a_lines[i1:i2]
        b_frag = b_lines[j1:j2]
        if tag == "delete":
            for k, ln in enumerate(a_frag):
                result.append(("仅A有", i1 + k, None, ln, ""))
        elif tag == "insert":
            for k, ln in enumerate(b_frag):
                result.append(("仅B有", None, j1 + k, "", ln))
        else:  # replace
            n = max(len(a_frag), len(b_frag))
            for k in range(n):
                la = a_frag[k] if k < len(a_frag) else ""
                lb = b_frag[k] if k < len(b_frag) else ""
                r = difflib.SequenceMatcher(None, la, lb).ratio() if la and lb else 0.0
                if la and lb and r >= ratio_threshold:
                    result.append(("相似改写", i1 + k, j1 + k, la, lb))
                else:
                    kind = "替换" if la and lb else ("仅A有" if la else "仅B有")
                    result.append((kind, i1 + k if la else None,
                                   j1 + k if lb else None, la, lb))
    return result


def main():
    ap = argparse.ArgumentParser(description="计算两段文本的相似度并标出关键差异")
    ap.add_argument("file_a", nargs="?", help="文件 A（或与 --text 搭配）")
    ap.add_argument("file_b", nargs="?", help="文件 B")
    ap.add_argument("--text", help="直接传入文本 A")
    ap.add_argument("--text2", help="直接传入文本 B")
    ap.add_argument("--out", help="结果写入文件（默认打印 stdout）")
    args = ap.parse_args()

    if args.text is not None and args.text2 is not None:
        a_text, b_text = args.text, args.text2
        a_name, b_name = "<text A>", "<text B>"
    elif args.file_a and args.file_b:
        try:
            with open(args.file_a, "r", encoding="utf-8", errors="replace") as fh:
                a_text = fh.read()
            with open(args.file_b, "r", encoding="utf-8", errors="replace") as fh:
                b_text = fh.read()
        except OSError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        a_name, b_name = args.file_a, args.file_b
    else:
        print("error: 需要两个文件，或同时提供 --text 与 --text2", file=sys.stderr)
        return 2

    a_lines, b_lines = a_text.splitlines(), b_text.splitlines()
    seq_ratio = difflib.SequenceMatcher(None, a_text, b_text, autojunk=False).ratio()
    jaccard = char_jaccard(a_text, b_text)
    overall = (seq_ratio + jaccard) / 2.0

    out = []
    out.append("相似度评分: %s  vs  %s" % (a_name, b_name))
    out.append("  difflib 相似度   : %.4f (%.1f%%)" % (seq_ratio, seq_ratio * 100))
    out.append("  字符 Jaccard     : %.4f (%.1f%%)" % (jaccard, jaccard * 100))
    out.append("  综合评分(均值)   : %.4f (%.1f%%)" % (overall, overall * 100))
    out.append("  A %d 行 / B %d 行, A %d 字符 / B %d 字符"
               % (len(a_lines), len(b_lines), len(a_text), len(b_text)))
    out.append("=" * 60)
    diffs = key_differences(a_lines, b_lines)
    if not diffs:
        out.append("（内容完全一致，无关键差异）")
    else:
        out.append("关键差异 (%d 处):" % len(diffs))
        for kind, la, lb, ta, tb in diffs:
            loc = ""
            if la is not None:
                loc += "A:L%d " % (la + 1)
            if lb is not None:
                loc += "B:L%d" % (lb + 1)
            out.append("  [%s] %s" % (kind, loc.strip()))
            if ta:
                out.append("    A: %s" % ta)
            if tb:
                out.append("    B: %s" % tb)

    text = "\n".join(out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("written %s (score %.4f)" % (args.out, overall))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
