#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容字符标准化（compat-char-normalize）

把文本中的 CJK 兼容表意文字（U+F900–U+FAFF）与全角兼容形式（全角 ASCII
U+FF01–U+FF5E、全角空格 U+3000、全角货币/符号 U+FFE0–U+FFE6、白括号
U+FF5F/FF60）映射回 Unicode 标准字形，便于统一检索、排序与比对。

映射依据本机 unicodedata 的字符分解记录（实测 460 个兼容字可映射）。
U+FA0E/FA0F/FA11/FA13/FA14/FA1F/FA21/FA23/FA24/FA27/FA28/FA29 这 12 个
字符是 Unicode 标准化例外：编码数据中不存在分解记录，NFKC 也保留它们，
故本工具同样保留不动。--nfkc 改用完整 NFKC 兼容分解（ﬁ→fi、㎡→m2 等）。

用法：
    python -I compat-char-normalize.py <输入文件> [-o 输出文件] [选项]
    python -I compat-char-normalize.py --text "從前ＡＢＣ１２３" --stats
    python -I compat-char-normalize.py --list        # 打印内置映射表
    python -I compat-char-normalize.py --self-test   # 运行内置自测

选项：
    -o, --output FILE          结果写入文件（缺省打印到标准输出）
    --text TEXT                直接处理命令行文本
    --nfkc                     使用完整 NFKC 兼容分解
    --keep-ideographic-space   保留全角空格 U+3000 不转换
    --stats                    统计被替换的字符
    --encoding ENC             输入文件编码（默认 utf-8）
    --list                     列出映射表后退出
    --self-test                运行内置自测并退出

示例：
    python -I compat-char-normalize.py doc.txt -o doc.norm.txt --stats
    python -I compat-char-normalize.py --text "從前更ＡＢＣ１２３（中文）　結束"
    python -I compat-char-normalize.py --text "﨎￠￥" --nfkc
"""

import argparse
import sys
import unicodedata
from collections import Counter

COMPAT_START, COMPAT_END = 0xF900, 0xFAFF   # CJK 兼容表意文字（含补充区）
FW_START, FW_END = 0xFF01, 0xFF5E           # 全角 ASCII
FW_OFFSET = 0xFEE0


def build_compat_map():
    """U+F900–U+FAFF → 标准字形（依据 unicodedata 分解记录）。"""
    table = {}
    for cp in range(COMPAT_START, COMPAT_END + 1):
        dec = unicodedata.decomposition(chr(cp))
        if not dec:
            continue
        parts = dec.split()
        if parts and parts[0].startswith("<"):
            parts = parts[1:]
        if not parts:
            continue
        try:
            target = "".join(chr(int(p, 16)) for p in parts)
        except ValueError:
            continue
        if target and target != chr(cp):
            table[cp] = target
    return table


def build_fullwidth_map(keep_ideographic_space=False):
    """全角兼容形式 → 半角/标准形式。"""
    table = {}
    for cp in range(FW_START, FW_END + 1):
        table[cp] = chr(cp - FW_OFFSET)
    for cp in (0xFF5F, 0xFF60):
        table[cp] = unicodedata.normalize("NFKC", chr(cp))
    for cp in range(0xFFE0, 0xFFE7):
        table[cp] = unicodedata.normalize("NFKC", chr(cp))
    if not keep_ideographic_space:
        table[0x3000] = " "
    return table


def build_table(keep_ideographic_space=False):
    table = build_fullwidth_map(keep_ideographic_space)
    table.update(build_compat_map())
    return table


def transform(text, table=None, nfkc=False):
    if nfkc:
        return unicodedata.normalize("NFKC", text)
    return text.translate(str.maketrans(table))


def read_text(path, encoding):
    with open(path, "r", encoding=encoding, newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def format_cp(cp):
    return "U+{:04X}".format(cp)


def show_list(table):
    for cp in sorted(table):
        target = table[cp]
        tgt = " ".join(format_cp(ord(c)) for c in target)
        print("{} {!r} -> {} {!r}".format(format_cp(cp), chr(cp), tgt, target))


def show_stats(text, table):
    hits = Counter(ch for ch in text if ord(ch) in table)
    total = sum(hits.values())
    print("字符总数: {}".format(len(text)))
    print("被映射字符: {} 个（{} 种）".format(total, len(hits)))
    for ch, n in hits.most_common(10):
        tgt = table[ord(ch)]
        tgt = " ".join(format_cp(ord(c)) for c in tgt)
        print("  {} {!r} x{} -> {}".format(format_cp(ord(ch)), ch, n, tgt))


def self_test():
    table = build_table()
    # 映射表关键条目（均经本机 unicodedata 实测）
    assert table.get(0xF900) == chr(0x8C48), table.get(0xF900)   # 豈
    assert table.get(0xFA19) == chr(0x795E), table.get(0xFA19)   # 神
    assert table.get(0xFF21) == "A"
    assert table.get(0x3000) == " "
    assert table.get(0xFFE0) == "¢"
    assert 0xFA0E not in table  # 标准化例外：无分解数据，保留
    cases = [
        ("ＡＢＣ１２３", "ABC123"),
        ("（中文）？！，", "(中文)?!,"),
        ("　全角空格", " 全角空格"),
        ("\uf900", chr(0x8C48)),
        ("\ufa19", chr(0x795E)),
        ("\ufa0e", "\ufa0e"),
        ("\uffe0\uffe5", "¢¥"),
    ]
    for src, want in cases:
        got = transform(src, table)
        assert got == want, (src, got, want)
    # NFKC 模式抽查
    assert unicodedata.normalize("NFKC", "ﬁ") == "fi"
    assert unicodedata.normalize("NFKC", "㎡") == "m2"
    print("compat-char-normalize 自测通过：映射表 {} 项，全角/兼容字/NFKC 例外行为正确".format(len(table)))
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        description="把 U+F900 兼容表意文字与全角兼容形式映射回标准字形")
    parser.add_argument("input", nargs="?", help="输入文件（或配合 --text 使用）")
    parser.add_argument("-o", "--output", help="输出文件（缺省打印到标准输出）")
    parser.add_argument("--text", help="直接处理命令行文本")
    parser.add_argument("--nfkc", action="store_true", help="使用完整 NFKC 兼容分解")
    parser.add_argument("--keep-ideographic-space", action="store_true",
                        help="保留全角空格 U+3000 不转换")
    parser.add_argument("--stats", action="store_true", help="统计被替换的字符")
    parser.add_argument("--encoding", default="utf-8", help="输入文件编码（默认 utf-8）")
    parser.add_argument("--list", action="store_true", help="列出映射表后退出")
    parser.add_argument("--self-test", action="store_true", help="运行内置自测后退出")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    table = None if args.nfkc else build_table(not args.keep_ideographic_space)
    if args.list:
        show_list(table or build_fullwidth_map(not args.keep_ideographic_space))
        return 0

    if args.text is not None:
        text = args.text
    elif args.input:
        try:
            text = read_text(args.input, args.encoding)
        except (OSError, UnicodeError) as e:
            print("读取失败: {}".format(e), file=sys.stderr)
            return 1
    else:
        parser.error("请提供输入文件，或使用 --text 传入文本")
        return 2

    result = transform(text, table, nfkc=args.nfkc)
    if args.stats:
        show_stats(text, table or {})
    if args.output:
        try:
            write_text(args.output, result)
        except OSError as e:
            print("写入失败: {}".format(e), file=sys.stderr)
            return 1
        print("已写入: {}".format(args.output))
    else:
        sys.stdout.write(result)
        if not result.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
