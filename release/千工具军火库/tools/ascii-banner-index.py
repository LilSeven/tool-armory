#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ascii-banner-index —— 分隔线目录生成。

扫描文本文件中 ==========、----------、********** 等手工分隔标记行
（banner），识别其对应的小节标题与所在行号，生成一份带行号的文件目录
（TOC）。可打印到终端、另存为独立文件，或幂等回写到原文件头部
（<!-- toc --> ... <!-- /toc --> 标记块内，重复执行只更新块内容）。

识别四种写法（默认全部启用）：
  1) 下划线式：标题行在上一行，分隔线在下一行
       第一章 概述
       =========
  2) 内嵌式：标题夹在同字符分隔线中间
       ===== 第一章 概述 =====
  3) 行尾式：标题与分隔线在同一行
       第一章 概述 =====
  4) 纯分隔线：配合 --above，取上方最近非空行作为标题
默认自动跳过 ``` / ~~~ 代码块与自身 <!-- toc --> 标记块内的分隔样式，
避免误报，并保证 --write 幂等。

示例命令:
  python ascii-banner-index.py notes.md                 # 打印目录到终端
  python ascii-banner-index.py notes.md -o toc.txt      # 目录另存为文件
  python ascii-banner-index.py notes.md --write         # 回写目录到文件头部（幂等）
  python ascii-banner-index.py notes.md --min-len 3 --levels "=-~"

退出码: 0=成功生成目录; 1=未发现任何分隔标记; 2=参数或 IO 错误。
仅用 Python 标准库。
"""

import argparse
import locale
import re
import sys
from pathlib import Path

TOC_BEGIN = "<!-- toc -->"
TOC_END = "<!-- /toc -->"
FENCE_RE = re.compile(r"^\s*(```|~~~)")
DEFAULT_LEVELS = "=-~*#_+."


def classify(line, min_len, levels):
    """把一行分类为 ("pure"|"inline"|"trailing", 分隔字符, 标题) 或 None。"""
    s = line.strip()
    if len(s) < min_len:
        return None
    esc = re.escape(levels)
    run = max(min_len - 1, 0)
    # 1) 纯分隔线：整行由同一分隔字符组成
    if len(set(s)) == 1 and s[0] in levels:
        return ("pure", s[0], None)
    # 2) 内嵌式：===== 标题 =====
    m = re.match(rf"^([{esc}])\1{{{run},}}\s+(.*?)\s+\1{{{run},}}$", s)
    if m and m.group(2) and (set(m.group(2)) - set(levels)):
        return ("inline", m.group(1), m.group(2))
    # 3) 行尾式：标题 =====
    m = re.match(rf"^(.*?\S)\s+([{esc}])\2{{{run},}}$", s)
    if m and (set(m.group(1)) - set(levels)):
        return ("trailing", m.group(2), m.group(1))
    return None


def scan(lines, min_len, levels, above, skip_fences=True, skip_toc_block=True):
    """扫描行列表，返回 [(行号, 分隔字符, 标题), ...]。"""
    entries = []
    in_fence = False
    in_toc = False
    prev_nonblank = None   # (行号, 文本)
    prev_is_banner = False
    for idx, raw in enumerate(lines, 1):
        if skip_toc_block and raw.strip() == TOC_BEGIN:
            in_toc = True
            prev_is_banner = False
            continue
        if skip_toc_block and raw.strip() == TOC_END:
            in_toc = False
            prev_is_banner = False
            continue
        if skip_toc_block and in_toc:
            continue
        if skip_fences and FENCE_RE.match(raw):
            in_fence = not in_fence
            prev_is_banner = False
            continue
        if skip_fences and in_fence:
            continue
        kind = classify(raw, min_len, levels)
        if kind is None:
            t = raw.strip()
            if t:
                prev_nonblank = (idx, t)
                prev_is_banner = False
            continue
        style, ch, title = kind
        if style == "pure":
            has_title = prev_nonblank is not None and not prev_is_banner
            if has_title or above:
                entries.append((idx, ch, prev_nonblank[1] if has_title else "(未命名)"))
        else:
            entries.append((idx, ch, title))
        prev_is_banner = True
    return entries


def render_toc(title, entries, levels):
    lines = ["目录: %s" % title, "-" * 32]
    for lineno, ch, name in entries:
        lvl = levels.index(ch) + 1 if ch in levels else 1
        lines.append("%6d  %s%s" % (lineno, "  " * (lvl - 1), name))
    return lines


def read_text_smart(path, for_write=False):
    """依次尝试 utf-8 / 本地编码读取，返回 (文本, 实际编码)。"""
    for enc in ("utf-8", "utf-8-sig"):
        try:
            return path.read_text(encoding=enc), enc
        except UnicodeDecodeError:
            continue
    loc = locale.getpreferredencoding(False) or "utf-8"
    try:
        return path.read_text(encoding=loc), loc
    except UnicodeDecodeError:
        if for_write:
            raise
        return path.read_text(encoding=loc, errors="replace"), loc


def write_toc(path, toc_lines, enc):
    """把 TOC 写入原文件：已存在标记块则替换，否则插入文件头部（幂等）。"""
    text = path.read_text(encoding=enc)
    nl = "\r\n" if "\r\n" in text else "\n"
    block = nl.join([TOC_BEGIN] + list(toc_lines) + [TOC_END])
    b = text.find(TOC_BEGIN)
    e = text.find(TOC_END)
    if 0 <= b < e:
        new_text = text[:b] + block + text[e + len(TOC_END):]
    else:
        new_text = block + nl + nl + text
    with open(path, "w", encoding=enc, newline="") as f:
        f.write(new_text)


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog="ascii-banner-index",
        description="扫描 ========= / ------- 等手工分隔标记，生成文件内目录（TOC）。",
    )
    ap.add_argument("file", help="要生成目录的文本文件")
    ap.add_argument("-o", "--output", help="把目录另存为该文件（默认仅打印）")
    ap.add_argument("--write", action="store_true",
                    help="把目录回写到原文件头部 %s ... %s 标记块（幂等）" % (TOC_BEGIN, TOC_END))
    ap.add_argument("--min-len", type=int, default=4, help="分隔线最短长度（默认 4）")
    ap.add_argument("--levels", default=DEFAULT_LEVELS,
                    help="层级分隔字符，按顺序层级递增（默认 '%s'）" % DEFAULT_LEVELS)
    ap.add_argument("--above", action="store_true", help="纯分隔线取上方最近非空行作标题")
    ap.add_argument("--no-fence-skip", action="store_true", help="不跳过 ``` / ~~~ 代码块")
    args = ap.parse_args(argv)

    if args.min_len < 1:
        print("错误: --min-len 必须 >= 1", file=sys.stderr)
        return 2
    if not args.levels:
        print("错误: --levels 不能为空", file=sys.stderr)
        return 2

    path = Path(args.file)
    if not path.is_file():
        print("错误: 找不到文件: %s" % path, file=sys.stderr)
        return 2
    try:
        text, enc = read_text_smart(path, for_write=args.write)
    except UnicodeDecodeError as exc:
        print("错误: 无法无损解码 %s（--write 需要无损解码，可用 --encoding 类工具预处理）: %s"
              % (path, exc), file=sys.stderr)
        return 2

    entries = scan(text.splitlines(), args.min_len, args.levels,
                   args.above, not args.no_fence_skip)
    if not entries:
        print("未发现任何分隔标记（min-len=%d, levels=%r）" % (args.min_len, args.levels),
              file=sys.stderr)
        return 1

    toc_lines = render_toc(str(path), entries, args.levels)
    if args.write:
        try:
            write_toc(path, toc_lines, enc)
        except OSError as exc:
            print("错误: 回写失败: %s" % exc, file=sys.stderr)
            return 2
        print("已回写目录到 %s（标记块 %s ... %s）" % (path, TOC_BEGIN, TOC_END))
    if args.output:
        Path(args.output).write_text("\n".join(toc_lines) + "\n", encoding="utf-8")
        print("目录已另存为 %s" % args.output)
    print("\n".join(toc_lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
