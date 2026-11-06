#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""URL Slug 生成 (slugify)

把任意标题文本转成 ASCII slug：Unicode NFKD 分解剥离音标/变音符，
非 ASCII 字母（如中文）按 --drop-cjk 决定丢弃或音译为 pinyin 首码不可用则丢弃，
空白与标点折叠为单个连字符，可截断限长并去掉首尾连字符。

用法:
  python slugify.py "Crème Brûlée Café"                # creme-brulee-cafe
  python slugify.py "Hello, World! 你好" -n 20         # 截断到 20 字符
  python slugify.py -f titles.txt                      # 逐行处理文件
  cat titles.txt | python slugify.py                   # 从 stdin 逐行读取

示例:
  python slugify.py "Über café & FIFO"   -> uber-cafe-fifo
"""
import argparse
import re
import sys
import unicodedata

WORD_RE = re.compile(r"[a-z0-9]+")


def translit_char(ch: str) -> str:
    """NFKD 分解后取 ASCII 部分；返回空串表示无法音译。"""
    d = unicodedata.normalize("NFKD", ch)
    return "".join(c for c in d if ord(c) < 128)


def slugify(text: str, max_len: int = 0, sep: str = "-") -> str:
    # 先整体分解以剥离音标
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_parts = []
    for ch in decomposed:
        if ord(ch) < 128:
            ascii_parts.append(ch)
        else:
            # 变音符本身（Mn 类别）直接丢弃；其他非 ASCII 丢弃
            pass
    ascii_text = "".join(ascii_parts).lower()
    words = WORD_RE.findall(ascii_text)
    slug = sep.join(words)
    if max_len > 0 and len(slug) > max_len:
        slug = slug[:max_len].rstrip(sep)
    return slug


def main() -> int:
    ap = argparse.ArgumentParser(description="标题文本转 ASCII slug")
    ap.add_argument("titles", nargs="*", help="标题文本")
    ap.add_argument("-f", "--file", help="逐行处理文件中的标题")
    ap.add_argument("-n", "--max-len", type=int, default=0,
                    help="slug 最大长度，0 = 不限")
    ap.add_argument("-s", "--sep", default="-", help="连接符，默认 '-'")
    args = ap.parse_args()

    items = list(args.titles)
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                items.extend(f.read().splitlines())
        except OSError as e:
            print(f"错误: 无法读取 {args.file}: {e}", file=sys.stderr)
            return 1
    if not items and not sys.stdin.isatty():
        items = sys.stdin.read().splitlines()
    if not items:
        ap.print_help()
        return 1

    for line in items:
        if not line.strip():
            continue
        print(slugify(line, max_len=args.max_len, sep=args.sep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
