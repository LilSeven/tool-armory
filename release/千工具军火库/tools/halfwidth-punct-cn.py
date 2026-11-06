#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""半角标点转全角 (halfwidth-punct-cn)。

把中文语境中的半角标点 , . ! ? : ; 转为对应全角 , 。 ！ ？ ： ；,
自动跳过数字小数点/千分位 (1.5, 1,000) 与英文单词内部 (e.g., sure:ok)。
纯标准库实现。

判定规则 (对每个目标字符, 邻居字符忽略两侧空格后判断):
  - 前后均为数字           -> 跳过 (小数点、千分位)
  - 前后均为 ASCII 字母    -> 跳过 (英文单词/缩写内部)
  - 前后一边是字母一边是数字 -> 跳过
  - 其余: 只要有一侧是 CJK (汉字/CJK标点/全角字符) -> 转全角

用法:
    python halfwidth-punct-cn.py [文件...] [-i]

示例命令:
    python halfwidth-punct-cn.py note.txt
    echo "你好,世界.版本是1.5" | python halfwidth-punct-cn.py -
    python halfwidth-punct-cn.py -i note.txt

退出码: 0 = 成功; 2 = 读文件失败。
"""

import argparse
import sys

_MAP = {",": "，", ".": "。", "!": "！", "?": "？", ":": "：", ";": "；"}


def _is_cjk(ch):
    o = ord(ch)
    return (0x3000 <= o <= 0x303F or   # CJK 标点
            0x4E00 <= o <= 0x9FFF or   # CJK 统一表意文字
            0xF900 <= o <= 0xFAFF or   # 兼容表意文字
            0xFF00 <= o <= 0xFFEF)     # 全角形式


def _is_ascii_letter(ch):
    return ch.isascii() and ch.isalpha()


def _is_ascii_digit(ch):
    return ch.isascii() and ch.isdigit()


def _neighbors(s, i):
    """取 s[i] 两侧忽略空格后的最近字符, 越界返回 ''。"""
    j = i - 1
    while j >= 0 and s[j] == " ":
        j -= 1
    k = i + 1
    while k < len(s) and s[k] == " ":
        k += 1
    return (s[j] if j >= 0 else ""), (s[k] if k < len(s) else "")


def convert_line(s):
    out = list(s)
    for i, ch in enumerate(s):
        if ch not in _MAP:
            continue
        prev, nxt = _neighbors(s, i)
        if not prev or not nxt:
            continue  # 行首/行尾, 上下文不足, 不动
        if _is_ascii_digit(prev) and _is_ascii_digit(nxt):
            continue  # 1.5 / 1,000
        if (_is_ascii_letter(prev) and _is_ascii_letter(nxt)):
            continue  # e.g. / sure:ok
        if (_is_ascii_letter(prev) and _is_ascii_digit(nxt)) or \
           (_is_ascii_digit(prev) and _is_ascii_letter(nxt)):
            continue
        if _is_cjk(prev) or _is_cjk(nxt):
            out[i] = _MAP[ch]
    return "".join(out)


def convert_text(text):
    return "\n".join(convert_line(ln) for ln in text.split("\n"))


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="中文语境半角标点转全角")
    ap.add_argument("paths", nargs="*", default=[],
                    help="输入文件; 省略或 '-' 表示 stdin")
    ap.add_argument("-i", "--in-place", action="store_true",
                    help="就地改写文件")
    args = ap.parse_args(argv)

    paths = args.paths or ["-"]
    if args.in_place and paths == ["-"]:
        print("错误: -i 需要指定文件", file=sys.stderr)
        return 2

    rc = 0
    for p in paths:
        try:
            if p == "-":
                data = sys.stdin.buffer.read()
            else:
                with open(p, "rb") as fh:
                    data = fh.read()
        except OSError as exc:
            print(f"错误: 无法读取 {p}: {exc}", file=sys.stderr)
            rc = 2
            continue
        out = convert_text(data.decode("utf-8", errors="replace"))
        if args.in_place:
            try:
                with open(p, "wb") as fh:
                    fh.write(out.encode("utf-8"))
            except OSError as exc:
                print(f"错误: 无法写入 {p}: {exc}", file=sys.stderr)
                rc = 2
        else:
            sys.stdout.write(out + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
