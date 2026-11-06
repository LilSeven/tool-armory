#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paragraph-reflow —— 硬换行段落合并：合并被复制粘贴切断的中文段落。

用途：
    从网页 / PDF / 聊天窗口复制出来的中文文本常被硬换行切成碎行。本工具把
    “断行处没有句末标点”的相邻行拼接回完整段落：行尾无标点、或是句中标点
    （，、：等）时与下一行拼接；行尾为句末标点（。！？… 及后引号、后括号）
    时保留换行，作为独立段落。空行、标题（第X章 / Markdown # / 一、 / 1. /
    （一）/ - 列表等）、引用与缩进行视为结构性内容，原样保留、不参与合并。

示例命令：
    python paragraph-reflow.py broken.txt                   # 结果输出到屏幕
    python paragraph-reflow.py broken.txt -o clean.txt      # 结果写入文件
    cat broken.txt | python paragraph-reflow.py             # 从 stdin 读取
    python paragraph-reflow.py broken.txt --join-all        # 忽略标点，仅按空行/结构行分段
    python paragraph-reflow.py broken.txt --ignore-indent   # 缩进行也参与合并并去掉缩进

说明：输出统一为 UTF-8 编码、LF 换行；输入编码自动识别（UTF-8 / GB18030 / Big5）。
"""

import argparse
import re
import sys

# 句末标点：行尾出现即认为段落可以在此结束
SENTENCE_END_CHARS = set("。！？!?…‥⋯" "」』）】》〉〕｝" "”’\"'")

# 结构性行：不参与合并
STRUCT_RES = [
    re.compile(r"^#{1,6}\s"),                                      # Markdown 标题
    re.compile(r"^>\s"),                                           # Markdown 引用
    re.compile(r"^[-*+•·▪◦–]\s+"),                                 # 无序列表
    re.compile(r"^\d{1,4}[、.．)）]\s*"),                           # 有序列表：12. / 3、
    re.compile(r"^[（(]\s*[0-9一二三四五六七八九十]{1,6}\s*[)）]"),  # （一） / (3)
    re.compile(r"^[一二三四五六七八九十百千零〇]{1,8}[、.．]"),      # 一、
    re.compile(r"^第[0-9一二三四五六七八九十百千万零〇两]{1,8}[章节回卷部篇集幕场]"),  # 第X章
]
FULL_LINE_TITLES_RE = re.compile(r"^(序章|序言|楔子|引子|前言|后记|尾声|番外|附录)$")


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")
        except Exception:
            pass


def _decode_auto(data):
    """按 BOM 与常见中文编码顺序尝试解码，失败时用替换字符兜底。"""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return data.decode("utf-32")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_text(path, encoding=None):
    if path in ("-", None):
        data = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as fh:
            data = fh.read()
    if encoding:
        return data.decode(encoding, errors="replace")
    return _decode_auto(data)


def write_text(text, out_path):
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def ends_sentence(line):
    s = line.rstrip()
    return bool(s) and s[-1] in SENTENCE_END_CHARS


def is_structural(line):
    if line[:1].isspace():
        return True
    if FULL_LINE_TITLES_RE.match(line.strip()):
        return True
    return any(rx.match(line) for rx in STRUCT_RES)


def smart_join(left, right):
    """拼接两行；两侧都是半角字母数字时补一个空格，避免英文粘连。"""
    if (left and right and left[-1].isascii() and left[-1].isalnum()
            and right[0].isascii() and right[0].isalnum()):
        return left + " " + right
    return left + right


def reflow(lines, join_all=False, ignore_indent=False):
    out = []
    buf = None
    for raw in lines:
        line = raw.rstrip()
        if ignore_indent:
            line = line.lstrip()
        if not line:
            if buf is not None:
                out.append(buf)
                buf = None
            out.append("")
            continue
        if is_structural(line):
            if buf is not None:
                out.append(buf)
                buf = None
            out.append(line)
            continue
        buf = line if buf is None else smart_join(buf, line)
        if not join_all and ends_sentence(buf):
            out.append(buf)
            buf = None
    if buf is not None:
        out.append(buf)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="paragraph-reflow",
        description="合并被复制粘贴切断的中文段落：断行处无句末标点即拼接，保持标题列表结构。",
    )
    parser.add_argument("input", nargs="?", default="-",
                        help="输入文本文件；缺省或 '-' 表示 stdin")
    parser.add_argument("-o", "--output",
                        help="输出文件（UTF-8/LF）；缺省输出到 stdout")
    parser.add_argument("--encoding",
                        help="指定输入编码；缺省自动识别 UTF-8/GB18030/Big5")
    parser.add_argument("--join-all", action="store_true",
                        help="忽略句末标点，仅按空行与结构行分段")
    parser.add_argument("--ignore-indent", action="store_true",
                        help="忽略行首缩进：缩进行参与合并并去除缩进")
    args = parser.parse_args(argv)

    try:
        text = read_text(args.input, args.encoding)
    except OSError as exc:
        print("paragraph-reflow: 无法读取输入：%s" % exc, file=sys.stderr)
        return 2

    result = reflow(text.splitlines(),
                    join_all=args.join_all,
                    ignore_indent=args.ignore_indent)
    out_text = "\n".join(result)
    if out_text:
        out_text += "\n"
    try:
        write_text(out_text, args.output)
    except OSError as exc:
        print("paragraph-reflow: 无法写出结果：%s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
