#!/usr/bin/env python3
"""文本差异统计：用 difflib 对比两个文件，输出增/删/改行数与变更行摘要。

用法:
    python diff-stat.py <旧文件> <新文件> [--out FILE]

示例:
    python diff-stat.py old.txt new.txt
    python diff-stat.py a.py b.py --out stat.txt
"""
import argparse
import difflib
import sys


def stat(a_lines, b_lines):
    added = removed = changed = 0
    changes = []  # (kind, 旧行号, 新行号, 内容描述)
    sm = difflib.SequenceMatcher(None, a_lines, b_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        a_frag = a_lines[i1:i2]
        b_frag = b_lines[j1:j2]
        if tag == "replace":
            if len(a_frag) == len(b_frag):
                # 逐行配对视为"改"
                changed += len(b_frag)
                for k in range(len(b_frag)):
                    changes.append(("M", i1 + k + 1, j1 + k + 1,
                                    a_frag[k], b_frag[k]))
            else:
                removed += len(a_frag)
                added += len(b_frag)
                for k, ln in enumerate(a_frag):
                    changes.append(("-", i1 + k + 1, None, ln, ""))
                for k, ln in enumerate(b_frag):
                    changes.append(("+", None, j1 + k + 1, "", ln))
        elif tag == "delete":
            removed += len(a_frag)
            for k, ln in enumerate(a_frag):
                changes.append(("-", i1 + k + 1, None, ln, ""))
        elif tag == "insert":
            added += len(b_frag)
            for k, ln in enumerate(b_frag):
                changes.append(("+", None, j1 + k + 1, "", ln))
    return added, removed, changed, changes


def main():
    ap = argparse.ArgumentParser(description="对比两个文件并统计增/删/改行数")
    ap.add_argument("old", help="旧文件")
    ap.add_argument("new", help="新文件")
    ap.add_argument("--out", help="结果写入文件（默认打印 stdout）")
    args = ap.parse_args()

    texts = []
    for p in (args.old, args.new):
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                texts.append(fh.read().splitlines())
        except OSError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2

    added, removed, changed, changes = stat(texts[0], texts[1])

    out = []
    out.append("差异统计: %s -> %s" % (args.old, args.new))
    out.append("  旧文件 %d 行, 新文件 %d 行" % (len(texts[0]), len(texts[1])))
    out.append("  新增: %d 行 (+)" % added)
    out.append("  删除: %d 行 (-)" % removed)
    out.append("  修改: %d 行 (M)" % changed)
    out.append("  变更总计: %d 行" % (added + removed + changed))
    out.append("=" * 60)
    if not changes:
        out.append("（两个文件完全相同）")
    else:
        for kind, ln_old, ln_new, a_text, b_text in changes:
            if kind == "M":
                out.append("M  旧L%d 新L%d" % (ln_old, ln_new))
                out.append("    - %s" % a_text)
                out.append("    + %s" % b_text)
            elif kind == "-":
                out.append("-  旧L%d %s" % (ln_old, a_text))
            else:
                out.append("+  新L%d %s" % (ln_new, b_text))

    text = "\n".join(out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("written %s (+%d -%d ~%d)" % (args.out, added, removed, changed))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
