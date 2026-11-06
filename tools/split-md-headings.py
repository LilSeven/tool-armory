#!/usr/bin/env python3
"""Markdown 按标题拆分 (split-md-headings)

把 Markdown 文档按一级/二级标题（# 和 ##）拆成多个 .md 文件，
标题文本经 slug 化处理作为文件名。

用法:
  python split-md-headings.py README.md -o outdir
  python split-md-headings.py doc.md -o outdir --min-level 2 --max-level 3
  python split-md-headings.py doc.md -o outdir --keep-title   # 分片内保留标题行
  python split-md-headings.py doc.md -o outdir --no-front     # 丢弃开头无标题内容

slug 规则：中文等非 ASCII 字符保留，空白转 -，去除文件名非法字符，
同名文件自动追加序号。代码块（``` 围栏）内的 # 不当作标题。
文件开头第一个标题之前的内容默认写入 00-intro.md。

示例命令:
  python split-md-headings.py manual.md -o ./chapters
"""

import argparse
import os
import re
import sys
import unicodedata

FRONT_RE = re.compile(r"\A---\s*\r?\n.*?\r?\n---\s*\r?\n", re.S)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def slugify(text, maxlen=50):
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f#`*_~\[\]()!.,;]', "", text)
    text = text.strip("-.") or "section"
    return text[:maxlen].rstrip("-")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把 Markdown 按一级/二级标题拆成多个 .md 文件，标题 slug 化为文件名")
    ap.add_argument("input", help="输入 Markdown 文件")
    ap.add_argument("-o", "--outdir", default=".",
                    help="输出目录（默认当前目录）")
    ap.add_argument("--min-level", type=int, default=1,
                    help="触发拆分的最小标题级别（默认 1）")
    ap.add_argument("--max-level", type=int, default=2,
                    help="触发拆分的最大标题级别（默认 2）")
    ap.add_argument("--keep-title", action="store_true",
                    help="输出分片中保留标题行本身（默认不保留）")
    ap.add_argument("--no-front", action="store_true",
                    help="丢弃文件开头第一个标题之前的内容（默认写入 00-intro.md）")
    args = ap.parse_args(argv)

    if args.min_level < 1 or args.max_level > 6 or args.min_level > args.max_level:
        print("错误: 标题级别范围无效", file=sys.stderr)
        return 2

    if not os.path.isfile(args.input):
        print("错误: 输入文件不存在: %s" % args.input, file=sys.stderr)
        return 2

    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    text = FRONT_RE.sub("", text, count=1)

    lines = text.splitlines(keepends=True)

    sections = []  # (title or None, [lines])
    cur_title, cur_lines, in_fence = None, [], False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        if not in_fence:
            m = HEADING_RE.match(line)
            if m and args.min_level <= len(m.group(1)) <= args.max_level:
                sections.append((cur_title, cur_lines))
                cur_title = m.group(2)
                cur_lines = [line] if args.keep_title else []
                continue
        cur_lines.append(line)
    sections.append((cur_title, cur_lines))

    os.makedirs(args.outdir, exist_ok=True)

    used = {}
    n_written = 0

    def write(fname, ls):
        with open(os.path.join(args.outdir, fname), "w",
                  encoding="utf-8", newline="") as f:
            f.writelines(ls)
        print("%s" % fname)

    for title, ls in sections:
        if title is None:
            if args.no_front or not any(s.strip() for s in ls):
                continue
            write("00-intro.md", ls)
            n_written += 1
            continue
        base = slugify(title)
        n = used.get(base, 0)
        used[base] = n + 1
        fname = base if n == 0 else "%s-%d" % (base, n + 1)
        fname += ".md"
        write(fname, ls)
        n_written += 1

    if n_written == 0:
        print("未找到任何标题，未产生输出。", file=sys.stderr)
        return 1
    print("共输出 %d 个文件到 %s" % (n_written, args.outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
