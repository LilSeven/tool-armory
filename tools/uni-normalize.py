#!/usr/bin/env python3
"""uni-normalize.py — Unicode 规范化工具。

对文本执行 NFC/NFD/NFKC/NFKD 四种规范化形式之一，并把被改写的字符数
写到 stderr 报告；规范化后的文本写到 stdout（或 -o 指定的文件）。

示例命令：
  python uni-normalize.py NFKC -i input.txt -o output.txt
  echo "cafe\\u0301" | python uni-normalize.py NFC
  python uni-normalize.py NFC --text "ＡＢＣ１２３"

说明：
  * 报告含：原始/结果字符数、被改写的字符数（含删除/替换，不含纯插入）、
    以及最多 5 个被改写字符的示例（码点 + Unicode 名称）。
  * 只用标准库（unicodedata + difflib）。
"""

import argparse
import difflib
import sys
import unicodedata

FORMS = ("NFC", "NFD", "NFKC", "NFKD")


def count_changed(src: str, dst: str) -> int:
    """统计 src 中被规范化改写（删除/替换）的字符个数，按源串计。"""
    if src == dst:
        return 0
    sm = difflib.SequenceMatcher(None, src, dst, autojunk=False)
    n = 0
    for op, a1, a2, _b1, _b2 in sm.get_opcodes():
        if op in ("delete", "replace"):
            n += a2 - a1
    return n


def changed_examples(src: str, dst: str, limit: int = 5):
    """返回最多 limit 个 (原字符, 新字符或'') 示例。"""
    out = []
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(
            None, src, dst, autojunk=False).get_opcodes():
        if op == "delete":
            pairs = [(ch, "") for ch in src[a1:a2]]
        elif op == "replace":
            pairs = list(zip(src[a1:a2], dst[b1:b2]))
            pairs += [(ch, "") for ch in src[a1 + len(pairs):a2]]
        else:
            continue
        out.extend(pairs)
        if len(out) >= limit:
            break
    return out[:limit]


def describe(ch: str) -> str:
    if not ch:
        return "<删除>"
    try:
        return "U+%04X %s" % (ord(ch), unicodedata.name(ch))
    except ValueError:
        return "U+%04X <无名>" % ord(ch)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Unicode NFC/NFD/NFKC/NFKD 规范化，并报告被改写的字符数。")
    ap.add_argument("form", help="规范化形式", choices=FORMS, type=str.upper)
    ap.add_argument("-i", "--input", help="输入文件（缺省读 stdin）")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout）")
    ap.add_argument("--text", help="直接指定待处理文本（优先于 -i/stdin）")
    ap.add_argument("--encoding", default="utf-8",
                    help="输入/输出编码（缺省 utf-8）")
    args = ap.parse_args()

    try:
        sys.stdin.reconfigure(encoding=args.encoding, errors="replace", newline="")
    except Exception:
        pass

    if args.text is not None:
        data = args.text
    elif args.input:
        with open(args.input, "r", encoding=args.encoding, errors="replace") as f:
            data = f.read()
    else:
        data = sys.stdin.read()

    norm = unicodedata.normalize(args.form, data)
    changed = count_changed(data, norm)

    if args.output:
        with open(args.output, "w", encoding=args.encoding, newline="") as f:
            f.write(norm)
    else:
        sys.stdout.write(norm)

    sys.stderr.write(
        "[uni-normalize] form=%s  %d 字符 -> %d 字符  被改写: %d\n"
        % (args.form, len(data), len(norm), changed))
    for src_ch, dst_ch in changed_examples(data, norm):
        sys.stderr.write("  %s -> %s\n" % (describe(src_ch), describe(dst_ch or "")))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
