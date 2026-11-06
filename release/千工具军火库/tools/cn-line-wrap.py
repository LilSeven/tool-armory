#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cn-line-wrap —— 中文列宽折行：按显示宽度把长段落折行。

用途：
    以“显示宽度”为准折行：汉字/全角字符按 2 列、半角按 1 列计算，
    中英混排不会折错位。折行同时做基础避头尾：
      * 句读（。，、等）放不下时“悬挂”在本行行末，最多超出 2 列（--no-hang 关闭）；
      * 行尾不留开括号/开引号（「（“ 等连同其后的句读一起移到下一行）；
      * 英文单词、版本号（v2.10.3）等整词不拆开（仅超长 URL 才逐字符硬切）。
    输入每个非空行为一个段落；空行原样保留为段落间隔。
    输出统一为 UTF-8 编码、LF 换行；输入编码自动识别。

示例命令：
    python cn-line-wrap.py long.txt -w 40                 # 每行最多 40 显示列
    python cn-line-wrap.py long.txt -w 40 -o wrapped.txt  # 写入文件
    python cn-line-wrap.py long.txt -w 40 --show-width    # 行首标注实际宽度（调试）
    python cn-line-wrap.py long.txt -w 40 --no-hang       # 禁止悬挂，严格不超宽
    python cn-line-wrap.py long.txt -w 40 --ambiguous 2   # 东亚模糊宽度字符按 2 列计
    cat long.txt | python cn-line-wrap.py -w 40           # 从 stdin 读取
"""

import argparse
import re
import sys
import unicodedata

# 行头禁则（句读/收尾标点不折到行首）
HEAD_FORBIDDEN = set("。，、；：？！…‥⋯·～ー" "」』）】》〉〕｝" "”’" ",.:;!?)]}%")
# 行尾禁则（开括号/开引号/货币符不留在行尾）
TAIL_FORBIDDEN = set("“‘「『（【《〈〔｛［" "([{" "￥＄¥$")

# 半角单词：字母数字串，内部可含 . ' - _ / @ 等连接符（如 v2.10.3、example.com）
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’._@/-][A-Za-z0-9]+)*")


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


def write_text(text, out_path):
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def char_width(ch, ambiguous=1):
    """单字符显示宽度：全角 2、组合字符 0、东亚模糊可配置、其余 1。"""
    if unicodedata.combining(ch):
        return 0
    ea = unicodedata.east_asian_width(ch)
    if ea in ("W", "F"):
        return 2
    if ea == "A":
        return ambiguous
    return 1


def str_width(s, ambiguous=1):
    return sum(char_width(c, ambiguous) for c in s)


def tokenize(text):
    """切成 token：半角单词整块、连续空白整块、其余单字符。"""
    tokens = []
    i, n = 0, len(text)
    while i < n:
        m = WORD_RE.match(text, i)
        if m:
            tokens.append(m.group())
            i = m.end()
            continue
        ch = text[i]
        if ch.isspace():
            j = i
            while j < n and text[j].isspace():
                j += 1
            tokens.append(text[i:j])
            i = j
            continue
        tokens.append(ch)
        i += 1
    return tokens


def wrap_line(line, width, ambiguous=1, hang=True):
    """把一行文本按显示宽度折成多行。"""
    tokens = tokenize(line.expandtabs(4))
    lines = []
    cur = ""
    cur_w = 0

    def flush():
        """结束当前行；行尾若挂着“开括号+句读”组合则整体移到下一行。"""
        nonlocal cur, cur_w
        k = len(cur)
        while k > 0 and cur[k - 1] in HEAD_FORBIDDEN:   # 行尾连续句读
            k -= 1
        m = k
        while m > 0 and cur[m - 1] in TAIL_FORBIDDEN:   # 紧贴的开括号/开引号
            m -= 1
        moved = ""
        if m < k:                                       # 行尾确有开括号，组合下移
            moved = cur[m:]
            cur = cur[:m]
            cur_w = str_width(cur, ambiguous)
        if cur:
            lines.append(cur.rstrip())
        cur = moved
        cur_w = str_width(moved, ambiguous)

    for tok in tokens:
        tw = str_width(tok, ambiguous)
        if tok.isspace():
            if cur_w + tw <= width:                     # 行尾空白自然丢弃
                cur += tok
                cur_w += tw
            continue
        if cur_w + tw <= width:
            cur += tok
            cur_w += tw
            continue
        if (hang and len(tok) == 1 and tok in HEAD_FORBIDDEN
                and cur_w + tw <= width + 2
                and not (cur and cur[-1] in TAIL_FORBIDDEN)):
            # 标点悬挂：挂在行末，最多超出 2 列
            cur += tok
            cur_w += tw
            continue
        if tw > width:
            # 超长 token（长单词/URL）：逐字符硬切，不做禁则处理
            flush()
            for ch in tok:
                cw = char_width(ch, ambiguous)
                if cur and cur_w + cw > width:
                    lines.append(cur.rstrip())
                    cur = ""
                    cur_w = 0
                cur += ch
                cur_w += cw
            continue
        flush()
        cur += tok
        cur_w = str_width(cur, ambiguous)
    if cur.strip():
        lines.append(cur.rstrip())
    return [ln for ln in lines if ln != ""]


def wrap_text(text, width, ambiguous=1, hang=True):
    out = []
    for line in text.splitlines():
        if not line.strip():
            out.append("")
            continue
        out.extend(wrap_line(line, width, ambiguous, hang))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="cn-line-wrap",
        description="按显示宽度折行：汉字/全角按 2 列、半角按 1 列，中英混排不错位，并做基础避头尾。",
    )
    parser.add_argument("input", nargs="?", default="-",
                        help="输入文本；缺省或 '-' 表示 stdin")
    parser.add_argument("-w", "--width", type=int, default=72,
                        help="每行最大显示宽度（列），默认 72")
    parser.add_argument("-o", "--output",
                        help="输出文件（UTF-8/LF）；缺省输出到 stdout")
    parser.add_argument("--encoding",
                        help="指定输入编码；缺省自动识别 UTF-8/GB18030/Big5")
    parser.add_argument("--ambiguous", type=int, choices=(1, 2), default=1,
                        help="东亚模糊宽度字符按几列计，默认 1")
    parser.add_argument("--no-hang", action="store_true",
                        help="禁止标点悬挂，严格不超过指定宽度")
    parser.add_argument("--show-width", action="store_true",
                        help="在每行行首标注实际显示宽度（调试用）")
    args = parser.parse_args(argv)

    if args.width < 4:
        print("cn-line-wrap: 宽度过小（至少 4 列）", file=sys.stderr)
        return 2
    try:
        text = read_text(args.input, args.encoding)
    except OSError as exc:
        print("cn-line-wrap: 无法读取输入：%s" % exc, file=sys.stderr)
        return 2

    lines = wrap_text(text, args.width, args.ambiguous, hang=not args.no_hang)
    if args.show_width:
        lines = ["[%3d] %s" % (str_width(ln, args.ambiguous), ln) for ln in lines]
    out_text = "\n".join(lines)
    if out_text:
        out_text += "\n"
    try:
        write_text(out_text, args.output)
    except OSError as exc:
        print("cn-line-wrap: 无法写出结果：%s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
