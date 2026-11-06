#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown 目录（TOC）生成：扫描标题层级，生成带锚点链接的目录，可插入指定位置。

锚点采用 GitHub 风格 slug（小写、去标点、空格转连字符、保留 CJK），同名标题自动加 -1/-2。

用法:
  python md-toc.py doc.md                          # 打印目录到 stdout
  python md-toc.py doc.md --max-level 3            # 只取 h1-h3
  python md-toc.py doc.md --insert-after "<!-- TOC -->"   # 插到标记行之后
  python md-toc.py doc.md --insert-after "^# 标题$" # 标记支持正则
  python md-toc.py doc.md -o toc.md                # 目录写入文件
  python md-toc.py doc.md --indent "  " --marker "{n}. [{t}](#{a})"

参数:
  --max-level N        最多收录到第 N 级标题（默认 6）
  --min-level N        从第 N 级开始收录（默认 1）
  --indent STR         每级缩进字符串（默认两空格）
  --marker STR         行模板，可用 {n}序号 {t}标题 {a}锚点 {l}级别（默认 "- [{t}](#{a})"）
  --insert-after REGEX 在首个匹配该正则的行之后插入（写入原文件）
  --in-place           配合 --insert-after，直接改写原文件（默认加 .toc.bak 备份）
  --no-backup          不生成备份文件
"""

import argparse
import re
import sys

FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def github_slug(text, used):
    s = text.strip().lower()
    s = re.sub(r"[\s]+", "-", s)               # 空白转连字符
    s = re.sub(r"[^\w\- \u4e00-\u9fff\u3400-\u4dbf]", "", s, flags=re.UNICODE)
    s = s.replace(" ", "-")
    if not s:
        s = "section"
    base, n = s, s
    k = 0
    while n in used:
        k += 1
        n = "%s-%d" % (base, k)
    used.add(n)
    return n


def extract_headings(lines):
    headings = []
    in_fence = False
    fence = ""
    for ln, line in enumerate(lines, 1):
        m = FENCE_RE.match(line)
        if m:
            if not in_fence:
                in_fence, fence = True, m.group(1)
            elif m.group(1) == fence:
                in_fence = False
            continue
        if in_fence:
            continue
        hm = HEADING_RE.match(line)
        if hm:
            headings.append((len(hm.group(1)), hm.group(2).strip(), ln))
    return headings


def build_toc(headings, args):
    used = set()
    lines = []
    for i, (level, text, _ln) in enumerate(headings, 1):
        if level < args.min_level or level > args.max_level:
            continue
        slug = github_slug(text, used)
        lines.append(args.indent * (level - args.min_level) +
                     args.marker.format(n=i, t=text, a=slug, l=level))
    return lines


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="Markdown 目录生成")
    ap.add_argument("mdfile")
    ap.add_argument("--min-level", type=int, default=1)
    ap.add_argument("--max-level", type=int, default=6)
    ap.add_argument("--indent", default="  ")
    ap.add_argument("--marker", default="- [{t}](#{a})")
    ap.add_argument("-o", "--out", help="目录输出文件（默认 stdout）")
    ap.add_argument("--insert-after", metavar="REGEX",
                    help="把目录插入文档中首个匹配行之后")
    ap.add_argument("--in-place", action="store_true",
                    help="直接改写 mdfile（需 --insert-after）")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    with open(args.mdfile, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    headings = extract_headings(lines)
    toc = build_toc(headings, args)
    if not toc:
        print("未发现标题", file=sys.stderr)
        sys.exit(0)

    if args.insert_after:
        rx = re.compile(args.insert_after)
        pos = next((i for i, l in enumerate(lines) if rx.search(l)), None)
        if pos is None:
            sys.exit("错误: 未找到匹配 %r 的行" % args.insert_after)
        new_lines = lines[: pos + 1] + ["<!-- TOC 开始 -->"] + toc + ["<!-- TOC 结束 -->", ""] + lines[pos + 1:]
        if args.in_place:
            if not args.no_backup:
                import shutil
                shutil.copy2(args.mdfile, args.mdfile + ".toc.bak")
            with open(args.mdfile, "w", encoding="utf-8", newline="") as f:
                f.write("\n".join(new_lines) + "\n")
            print("已插入 %d 条目录到 %s（标记后第 %d 行）" % (len(toc), args.mdfile, pos + 2),
                  file=sys.stderr)
        else:
            sys.stdout.write("\n".join(new_lines) + "\n")
    else:
        text = "\n".join(toc)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            print("已写入 %s（%d 条）" % (args.out, len(toc)), file=sys.stderr)
        else:
            print(text)


if __name__ == "__main__":
    main()
