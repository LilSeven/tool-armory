#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""小说章节拆分——按「第X章/卷」等标题正则把整本 TXT 拆成独立章节文件。

默认识别行首标题: 第X章/节/卷/回/部/集/篇（中文/阿拉伯/全角数字）、Chapter N、
Chap. N, 以及 序章/序言/楔子/引子/尾声/后记/终章/番外××。
标题行按出现顺序编号, 连同其后正文写入 <序号>_<标题>.txt（如 0001_第一章 初入江湖.txt）;
首个标题之前若还有内容, 写入 0000_前言.txt; 默认生成 index.txt 索引（序号/标题/文件名/起始行）。

用法:
    python chapter-splitter.py 全本.txt -d 拆分输出
    python chapter-splitter.py 全本.txt -d out --pattern "^\s*第[0-9一二三四五六七八九十百千]+章"
    python chapter-splitter.py 全本.txt -d out --loose
    python chapter-splitter.py 全本.txt -d out --no-index --name-template "{num:03d}_{title}"

说明: 默认要求标题行在章节号之后是空白/标点/行尾（避免把「第一章的内容…」这类正文误判）。
紧凑排版（如「第一章穿越火线」标题后直接跟正文）可用 --loose 放宽, 或用 --pattern
完全自定义（Python 正则, 逐行 match）。

退出码: 0=成功; 2=参数/文件错误; 3=未匹配到任何章节标题。
"""

import argparse
import re
import sys
from pathlib import Path

_TAIL = r"(?=\s|[。．.，,、；；;：:！!？?·~\-—（《“'\"〔【】）]|$)"

_ALT = (
    r"第\s*[0-9０-９零〇一二三四五六七八九十百千万两]+\s*[章节卷回部集篇]"
    r"|(?:chapter|chap)\s*\.?\s*\d+"
    r"|序章|序言|楔子|引子|尾声|后记|终章"
    r"|番外.{0,20}"
)
DEFAULT_RE = re.compile(r"^\s*(?:" + _ALT + r")" + _TAIL, re.IGNORECASE)
LOOSE_RE = re.compile(r"^\s*(?:" + _ALT + r")", re.IGNORECASE)

_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def _reconfig():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(msg, code=2):
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(code)


def read_text(path, encoding):
    raw = Path(path).read_bytes()
    if encoding != "auto":
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError) as exc:
            die(f"无法用 {encoding} 解码 {path}: {exc}")
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def save(path, body_lines, encoding):
    body = "\n".join(body_lines).rstrip("\n") + "\n"
    with open(path, "w", encoding=encoding, newline="") as fh:
        fh.write(body)


def sanitize_title(title, maxlen):
    t = _ILLEGAL.sub("_", title)
    t = re.sub(r"\s+", " ", t).strip()
    t = t[:maxlen].strip()
    return t or "无标题"


def main(argv=None):
    _reconfig()
    ap = argparse.ArgumentParser(
        prog="chapter-splitter",
        description="按「第X章/卷」等标题正则把整本 TXT 拆成独立章节文件并按序号命名",
    )
    ap.add_argument("input", help="输入 TXT 文件")
    ap.add_argument("-d", "--outdir", help="输出目录; 缺省为 <输入文件名>_chapters")
    ap.add_argument("-p", "--pattern", help="自定义标题正则（逐行 match）")
    ap.add_argument("--loose", action="store_true",
                    help="放宽校验: 章节号后不要求空白/标点（可能误切正文）")
    ap.add_argument("--name-template", default="{num:04d}_{title}",
                    help="文件名模板, 可用 {num} 与 {title}（默认 %s）" % "{num:04d}_{title}")
    ap.add_argument("--max-title-len", type=int, default=40, help="标题截断长度（默认 40）")
    ap.add_argument("--no-index", action="store_true", help="不生成 index.txt")
    ap.add_argument("--encoding", default="auto", help="输入编码, auto=尝试 utf-8/gb18030/big5")
    ap.add_argument("--out-encoding", default="utf-8", help="输出文件编码（默认 utf-8）")
    args = ap.parse_args(argv)

    if args.pattern:
        try:
            pattern = re.compile(args.pattern)
        except re.error as exc:
            die(f"--pattern 正则无效: {args.pattern!r} ({exc})")
    else:
        pattern = LOOSE_RE if args.loose else DEFAULT_RE

    try:
        text = read_text(args.input, args.encoding)
    except OSError as exc:
        die(f"读取输入失败: {exc}")

    lines = text.splitlines()
    hits = [i for i, ln in enumerate(lines) if pattern.match(ln)]
    if not hits:
        die("未匹配到任何章节标题（可用 --pattern 自定义, 或 --loose 放宽）", 3)

    inpath = Path(args.input)
    outdir = Path(args.outdir) if args.outdir else inpath.with_name(inpath.stem + "_chapters")
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        die(f"创建输出目录失败: {exc}")

    bounds = hits + [len(lines)]
    index_rows = []  # (num, heading, filename, start_line)
    pre_written = False

    pre_lines = lines[:hits[0]]
    if any(ln.strip() for ln in pre_lines):
        save(outdir / "0000_前言.txt", pre_lines, args.out_encoding)
        index_rows.append((0, "前言", "0000_前言.txt", 1))
        pre_written = True

    for k, start in enumerate(hits):
        num = k + 1
        heading = lines[start].strip()
        body = [heading] + lines[start + 1:bounds[k + 1]]
        title = sanitize_title(heading, args.max_title_len)
        try:
            fname = args.name_template.format(num=num, title=title) + ".txt"
        except (KeyError, IndexError, ValueError) as exc:
            die(f"--name-template 无效: {args.name_template!r} ({exc}); 只支持 "
                "{num} 与 {title}")
        save(outdir / fname, body, args.out_encoding)
        index_rows.append((num, heading, fname, start + 1))

    if not args.no_index:
        rows = ["序号\t标题\t文件名\t起始行"]
        rows += [f"{n:04d}\t{h}\t{f}\tL{l}" for n, h, f, l in index_rows]
        with open(outdir / "index.txt", "w", encoding=args.out_encoding, newline="") as fh:
            fh.write("\n".join(rows) + "\n")

    chapters = len(index_rows) - (1 if pre_written else 0)
    msg = f"[chapter-splitter] 拆出章节 {chapters} 章"
    msg += " + 前言 1 篇" if pre_written else ""
    msg += f" → {outdir}"
    msg += "; 索引: index.txt" if not args.no_index else "; 未生成索引"
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
