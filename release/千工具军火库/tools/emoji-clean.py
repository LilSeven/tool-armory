#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Emoji 统计与清理（emoji-clean）

统计文本中的 emoji 与符号修饰符（肤色修饰符、变体选择符 VS15/16、ZWJ、
键帽、区域指示符国旗等），或将其整体删除，适配严肃公文排版场景。
识别按字符区间 + 序列状态机实现：👨‍👩‍👧、👍🏽、🇨🇳、#️⃣ 各计为 1 个 emoji。
纯 ASCII（©®™ 等正文常用符号）默认保留。

用法：
    python -I emoji-clean.py <输入文件> [--detail] [--stats]
    python -I emoji-clean.py <输入文件> --remove [-o 输出文件]
    python -I emoji-clean.py --text "你好😀🇨🇳" --detail
    python -I emoji-clean.py --self-test

选项：
    --remove            删除 emoji 后输出文本（缺省只统计）
    -o, --output FILE   删除结果写入文件（缺省打印到标准输出）
    --text TEXT         直接处理命令行文本
    --detail            统计模式下列出每种 emoji 及出现次数
    --encoding ENC      输入文件编码（默认 utf-8）
    --self-test         运行内置自测并退出

示例：
    python -I emoji-clean.py 公文.txt --detail
    python -I emoji-clean.py 公文.txt --remove -o 公文.clean.txt
"""

import argparse
import sys
from collections import Counter

# emoji 基字符区间（ pictographic 与相关符号块）
EMOJI_RANGES = (
    (0x1F000, 0x1F0FF),  # 麻将/多米诺/纸牌
    (0x1F100, 0x1F1FF),  # 带圈字母补充 + 区域指示符（国旗）
    (0x1F200, 0x1F2FF),  # 带圈表意文字补充
    (0x1F300, 0x1F5FF),  # 杂项符号和图形（含肤色修饰符 1F3FB–1F3FF）
    (0x1F600, 0x1F64F),  # 表情符号
    (0x1F650, 0x1F67F),  # 装饰性丁贝符
    (0x1F680, 0x1F6FF),  # 交通和地图
    (0x1F900, 0x1F9FF),  # 补充符号和图形
    (0x1FA70, 0x1FAFF),  # 符号和图形扩展 A
    (0x2600, 0x26FF),    # 杂项符号 ☀☁☎⚠…
    (0x2700, 0x27BF),    # 丁贝符 ✂✅❤…
    (0x2B00, 0x2BFF),    # ⭐⬛⭕⬆…
    (0x3030, 0x3030),    # 〰
    (0x303D, 0x303D),    # 〽
    (0x3297, 0x3297),    # ㊗
    (0x3299, 0x3299),    # ㊙
)
# 只作修饰、不单独成 emoji 基字符
MODIFIERS = {0xFE0F, 0xFE0E, 0x200D, 0x20E3}
SKIN_MIN, SKIN_MAX = 0x1F3FB, 0x1F3FF


def _in_ranges(o):
    return any(lo <= o <= hi for lo, hi in EMOJI_RANGES)


def _is_emoji_base(o):
    return o not in MODIFIERS and _in_ranges(o)


def _is_ri(ch):
    return 0x1F1E6 <= ord(ch) <= 0x1F1FF


def find_emoji_tokens(text):
    """扫描文本，返回 emoji 序列的 (start, end) 列表。"""
    tokens = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        o = ord(ch)
        # 区域指示符成对 → 国旗
        if _is_ri(ch) and i + 1 < n and _is_ri(text[i + 1]):
            tokens.append((i, i + 2))
            i += 2
            continue
        # 键帽：#、*、数字 + (VS16)? + U+20E3
        if ch in "#*0123456789":
            j = i + 1
            if j < n and ord(text[j]) == 0xFE0F:
                j += 1
            if j < n and ord(text[j]) == 0x20E3:
                tokens.append((i, j + 1))
                i = j + 1
                continue
        if _is_emoji_base(o):
            j = i + 1
            while j < n:
                oj = ord(text[j])
                if oj in (0xFE0F, 0xFE0E, 0x20E3) or SKIN_MIN <= oj <= SKIN_MAX:
                    j += 1
                elif oj == 0x200D:  # ZWJ：须后接 emoji 基字符（允许中间修饰符）
                    k = j + 1
                    while k < n and (ord(text[k]) in (0xFE0F, 0xFE0E)
                                     or SKIN_MIN <= ord(text[k]) <= SKIN_MAX):
                        k += 1
                    if k < n and _is_emoji_base(ord(text[k])):
                        j = k + 1
                    else:
                        break
                else:
                    break
            tokens.append((i, j))
            i = j
        elif o in MODIFIERS or SKIN_MIN <= o <= SKIN_MAX:
            # 孤立的修饰符也按需清除
            tokens.append((i, i + 1))
            i += 1
        else:
            i += 1
    return tokens


def token_label(tok):
    return " ".join("U+{:04X}".format(ord(c)) for c in tok)


def read_text(path, encoding):
    with open(path, "r", encoding=encoding, newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def remove_emoji(text):
    tokens = find_emoji_tokens(text)
    if not tokens:
        return text, 0
    out = []
    prev = 0
    for start, end in tokens:
        out.append(text[prev:start])
        prev = end
    out.append(text[prev:])
    return "".join(out), len(tokens)


def print_stats(text, detail=False):
    tokens = find_emoji_tokens(text)
    texts = [text[s:e] for s, e in tokens]
    print("字符总数: {}".format(len(text)))
    print("emoji 序列: {} 个（去重 {} 种）".format(len(tokens), len(set(texts))))
    if texts:
        print("文本占比: {:.1f}%".format(
            100.0 * sum(e - s for s, e in tokens) / max(1, len(text))))
    if detail and texts:
        for tok, n in Counter(texts).most_common():
            print("  {!r}  {}  x{}".format(tok, token_label(tok), n))


def self_test():
    text = ("会议通知：请联系张三 \U0001F4DE\U0001F4AA\U0001F3FC"
            "\U0001F1E8\U0001F1F3\u2705\u2764\uFE0F 并回复 #1\uFE0F\u20E3")
    # 📞 💪🏽 🇨🇳 ✅ ❤️ #1⃣ = 6 个序列
    tokens = find_emoji_tokens(text)
    assert len(tokens) == 6, [(text[s:e], token_label(text[s:e])) for s, e in tokens]
    assert text[tokens[0][0]:tokens[0][1]] == "\U0001F4DE"
    assert text[tokens[1][0]:tokens[1][1]] == "\U0001F4AA\U0001F3FC"
    assert text[tokens[2][0]:tokens[2][1]] == "\U0001F1E8\U0001F1F3"
    assert text[tokens[5][0]:tokens[5][1]] == "1\uFE0F\u20E3"
    cleaned, removed = remove_emoji(text)
    assert removed == 6
    assert cleaned == "会议通知：请联系张三  并回复 #", repr(cleaned)
    # 无 emoji 文本
    plain, removed2 = remove_emoji("公文正文，无任何符号修饰。(c)2024")
    assert removed2 == 0 and plain == "公文正文，无任何符号修饰。(c)2024"
    # ZWJ 家庭序列计为 1 个
    family = "\U0001F468\u200D\U0001F469\u200D\U0001F467"
    assert len(find_emoji_tokens("a" + family + "b")) == 1
    print("emoji-clean 自测通过：6 类序列识别与清理正确，纯文本不受影响")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="统计或删除文本中的 emoji 与符号修饰符")
    parser.add_argument("input", nargs="?", help="输入文件（或配合 --text 使用）")
    parser.add_argument("--remove", action="store_true", help="删除 emoji 后输出")
    parser.add_argument("-o", "--output", help="输出文件（缺省打印到标准输出）")
    parser.add_argument("--text", help="直接处理命令行文本")
    parser.add_argument("--detail", action="store_true", help="列出每种 emoji 及次数")
    parser.add_argument("--encoding", default="utf-8", help="输入文件编码（默认 utf-8）")
    parser.add_argument("--self-test", action="store_true", help="运行内置自测后退出")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

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

    if args.remove:
        cleaned, removed = remove_emoji(text)
        note = "删除 emoji 序列: {} 个".format(removed)
        if args.output:
            try:
                write_text(args.output, cleaned)
            except OSError as e:
                print("写入失败: {}".format(e), file=sys.stderr)
                return 1
            print(note)
            print("已写入: {}".format(args.output))
        else:
            print(note, file=sys.stderr)
            sys.stdout.write(cleaned)
            if not cleaned.endswith("\n"):
                sys.stdout.write("\n")
    else:
        print_stats(text, detail=args.detail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
