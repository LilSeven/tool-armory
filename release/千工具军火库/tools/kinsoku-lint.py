#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kinsoku-lint —— 避头尾禁则检查：找出禁则字符出现的位置。

用途：
    逐行检查两类禁则，报告文件名、行号、列号、字符及其 Unicode 名称：
      * 行头禁则：句读/收尾类标点不应出现在行首
        （。，、；：？！…」』）】》”’ 及半角 ,.:;!?)]}%）；
      * 行尾禁则：开括号/开引号/货币符不应悬在行尾
        （“‘「『（【《〈〔｛［ 及半角 ([{ 与 ￥＄¥$）。
    行首按“第一个非空白字符”判定，行尾按“最后一个非空白字符”判定。
    默认只报告、退出码恒为 0，可直接用在管道里；加 --strict 后发现禁则
    问题退出码为 1，便于在 CI 中使用。

示例命令：
    python kinsoku-lint.py book.txt                # 检查单个文件
    python kinsoku-lint.py a.txt b.txt             # 检查多个文件
    cat book.txt | python kinsoku-lint.py -        # 检查 stdin
    python kinsoku-lint.py book.txt --strict       # 有禁则问题时退出码 1
    python kinsoku-lint.py book.txt --no-ascii     # 只查全角，忽略半角标点
"""

import argparse
import sys
import unicodedata

HEAD_FORBIDDEN_FULL = set("。，、；：？！…‥⋯·～ー" "」』）】》〉〕｝" "”’")
HEAD_FORBIDDEN_ASCII = set(",.:;!?)]}%")
TAIL_FORBIDDEN_FULL = set("“‘「『（【《〈〔｛［" "￥＄¥$")
TAIL_FORBIDDEN_ASCII = set("([{")

KIND_LABEL = {"head": "行头禁则", "tail": "行尾禁则"}
KIND_HINT = {
    "head": "句读/收尾标点不应出现在行首",
    "tail": "开括号/开引号/货币符不应出现在行尾",
}


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")
        except Exception:
            pass


def _decode_auto(data):
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


def char_label(ch):
    code = "U+%04X" % ord(ch)
    name = unicodedata.name(ch, "")
    if name:
        return '"%s" (%s %s)' % (ch, code, name)
    return '"%s" (%s)' % (ch, code)


def lint_line(text, check_ascii=True):
    """检查单行，返回 [(kind, col, ch)]；col 为 1 基列号。"""
    problems = []
    body = text.strip()
    if not body:
        return problems
    head_set = HEAD_FORBIDDEN_FULL | (HEAD_FORBIDDEN_ASCII if check_ascii else set())
    tail_set = TAIL_FORBIDDEN_FULL | (TAIL_FORBIDDEN_ASCII if check_ascii else set())
    if body[0] in head_set:
        col = len(text) - len(text.lstrip()) + 1
        problems.append(("head", col, body[0]))
    if body[-1] in tail_set:
        col = len(text.rstrip())
        problems.append(("tail", col, body[-1]))
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="kinsoku-lint",
        description="避头尾禁则检查：报告行首句读、行尾开括号等禁则字符的位置。默认只报告，退出码恒为 0。",
    )
    parser.add_argument("inputs", nargs="*", default=[],
                        help="要检查的文本文件；缺省或 '-' 表示 stdin")
    parser.add_argument("--strict", action="store_true",
                        help="发现禁则问题时退出码为 1（默认恒为 0）")
    parser.add_argument("--no-ascii", action="store_true",
                        help="忽略半角标点，只检查全角禁则字符")
    parser.add_argument("--encoding",
                        help="指定输入编码；缺省自动识别 UTF-8/GB18030/Big5")
    args = parser.parse_args(argv)

    inputs = args.inputs or ["-"]
    check_ascii = not args.no_ascii
    head_n = tail_n = 0
    for src in inputs:
        try:
            text = read_text(src, args.encoding)
        except OSError as exc:
            print("kinsoku-lint: 无法读取 %s：%s" % (src, exc), file=sys.stderr)
            return 2
        label = "<stdin>" if src in ("-", None) else src
        for lineno, line in enumerate(text.splitlines(), 1):
            for kind, col, ch in lint_line(line, check_ascii):
                print("%s:%d:%d: %s %s —— %s"
                      % (label, lineno, col, KIND_LABEL[kind],
                         char_label(ch), KIND_HINT[kind]))
                if kind == "head":
                    head_n += 1
                else:
                    tail_n += 1
    total = head_n + tail_n
    if total:
        print("共发现 %d 处禁则问题（行头 %d 处、行尾 %d 处）。" % (total, head_n, tail_n))
        return 1 if args.strict else 0
    print("未发现避头尾禁则问题。")
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
