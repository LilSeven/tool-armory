#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志格式猜测(log-format-detect):采样日志行,归纳字段布局与正则模板。

读取日志文件的采样行,把每行按 token 类型(时间戳/IP/整数/浮点数/引号串/
HTTP 方法/状态码/日志级别/单词...)归类,统计出现最多的字段布局,并为每种
布局生成一条可直接 re.compile 的正则模板(带命名分组),辅助后续编写解析器。

用法:
    python log-format-detect.py <logfile> [--samples N] [--top N] [--all]
    cat app.log | python log-format-detect.py -

示例:
    python -I log-format-detect.py access.log --samples 200 --top 3
    tail -n 100 app.log | python -I log-format-detect.py -

说明:
  - 生成的模板假定字段之间以单个空格分隔;
  - 引号 "..." 与方括号 [...] 包裹的内容视为一个整体字段;
  - 行首形如 "YYYY-MM-DD HH:MM:SS,fff" 或 "Mon DD HH:MM:SS" 的时间戳会先
    合并为一个 token 再归纳。

仅使用 Python 标准库。
"""

import argparse
import re
import sys
from collections import Counter

# 时间戳模式(无锚点, 用 fullmatch 判定; pattern 会被嵌入生成的模板中)
TS_PATTERNS = [
    re.compile(r"\d{4}-\d{1,2}-\d{1,2}[T ]\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"),
    re.compile(r"\d{4}/\d{1,2}/\d{1,2}[T ]\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?"),
    re.compile(r"\d{1,2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}(?: [+-]\d{4})?"),
    re.compile(r"[A-Za-z]{3} +\d{1,2} \d{2}:\d{2}:\d{2}"),
    re.compile(r"\d{13}(?:\.\d+)?"),  # epoch 毫秒
]
EPOCH_S_RE = re.compile(r"\d{10}(?:\.\d+)?")  # epoch 秒(仅行首位置视为时间戳)

TOKEN_RE = re.compile(r'"[^"]*"|\[[^\]]*\]|\S+')
ISO_SPACE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?")
SLASH_SPACE_RE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2} \d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?")
SYSLOG_SPACE_RE = re.compile(r"^[A-Za-z]{3} {1,2}\d{1,2} \d{2}:\d{2}:\d{2}")

IP_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")
STATUS_RE = re.compile(r"[1-5]\d{2}")
INT_RE = re.compile(r"\d+")
FLOAT_RE = re.compile(r"\d+\.\d+")
VER_RE = re.compile(r"HTTP/[\d.]+", re.IGNORECASE)
METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE", "CONNECT"}
LEVELS = {"DEBUG", "INFO", "NOTICE", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL", "TRACE"}

# 类别 -> (人类可读标签, 分组基名, 默认正则片段)
CLASS_INFO = {
    "TS":     ("TIMESTAMP", "ts",     None),
    "IP":     ("IP",        "ip",     r"\d{1,3}(?:\.\d{1,3}){3}"),
    "METHOD": ("METHOD",    "method", r"[A-Z]+"),
    "LEVEL":  ("LEVEL",     "level",  r"[A-Z]+"),
    "VER":    ("HTTP_VER",  "ver",    r"HTTP/[\d.]+"),
    "PATH":   ("PATH",      "path",   r"\S+"),
    "STATUS": ("STATUS",    "status", r"[1-5]\d{2}"),
    "FLOAT":  ("FLOAT",     "num",    r"\d+\.\d+"),
    "INT":    ("INT",       "num",    r"\d+"),
    "DASH":   ("DASH",      "dash",   r"-"),
    "QSTR":   ("QUOTED",    "str",    r'"[^"]*"'),
    "BRACK":  ("BRACKETED", "brack",  r"\[[^\]]*\]"),
    "WORD":   ("WORD",      "word",   r"\S+"),
}


def tokenize(line):
    """先合并跨空格的时间戳前缀, 再按 引号/方括号/非空白 切 token。"""
    toks = []
    rest = line
    for lead in (ISO_SPACE_RE, SLASH_SPACE_RE, SYSLOG_SPACE_RE):
        m = lead.match(rest)
        if m:
            toks.append(m.group(0))
            rest = rest[m.end():]
            break
    toks.extend(TOKEN_RE.findall(rest))
    return toks


def classify(token, idx):
    """返回 (类别, 用于模板的正则片段)。"""
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        inner = token[1:-1]
        for pat in TS_PATTERNS:
            if pat.fullmatch(inner):
                return "TS", pat.pattern
        return "QSTR", CLASS_INFO["QSTR"][2]
    if len(token) >= 2 and token[0] == "[" and token[-1] == "]":
        inner = token[1:-1]
        for pat in TS_PATTERNS:
            if pat.fullmatch(inner):
                return "TS", pat.pattern
        return "BRACK", CLASS_INFO["BRACK"][2]
    for pat in TS_PATTERNS:
        if pat.fullmatch(token):
            return "TS", pat.pattern
    if idx == 0 and EPOCH_S_RE.fullmatch(token):
        return "TS", EPOCH_S_RE.pattern
    if IP_RE.fullmatch(token):
        return "IP", CLASS_INFO["IP"][2]
    if token.isalpha() and token.upper() in METHODS:
        return "METHOD", CLASS_INFO["METHOD"][2]
    if token.isalpha() and token.upper() in LEVELS:
        return "LEVEL", CLASS_INFO["LEVEL"][2]
    if VER_RE.fullmatch(token):
        return "VER", CLASS_INFO["VER"][2]
    if token.startswith("/"):
        return "PATH", CLASS_INFO["PATH"][2]
    if STATUS_RE.fullmatch(token):
        return "STATUS", CLASS_INFO["STATUS"][2]
    if FLOAT_RE.fullmatch(token):
        return "FLOAT", CLASS_INFO["FLOAT"][2]
    if INT_RE.fullmatch(token):
        return "INT", CLASS_INFO["INT"][2]
    if token == "-":
        return "DASH", CLASS_INFO["DASH"][2]
    return "WORD", CLASS_INFO["WORD"][2]


def build_template(line):
    """把一行日志归纳为 (类别序列, 正则模板字符串)。"""
    toks = tokenize(line)
    classes, pieces = [], []
    used = Counter()
    for i, tok in enumerate(toks):
        cls, rex = classify(tok, i)
        classes.append(cls)
        if cls == "DASH":
            pieces.append(rex)
            continue
        base = CLASS_INFO[cls][1]
        used[base] += 1
        name = base if used[base] == 1 else "%s_%d" % (base, used[base])
        pieces.append("(?P<%s>%s)" % (name, rex))
    return classes, "^" + " ".join(pieces) + "$"


def template_safe(line):
    """build_template 的兜底版: 生成的正则编译失败时退化为全 WORD。"""
    classes, regex = build_template(line)
    try:
        re.compile(regex)
    except re.error:
        toks = tokenize(line)
        classes = ["WORD"] * len(toks)
        regex = "^" + " ".join([r"\S+"] * len(toks)) + "$"
    return classes, regex


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog="log-format-detect",
        description="采样日志行, 归纳字段布局与正则模板")
    ap.add_argument("file", help="日志文件路径; '-' 表示 stdin")
    ap.add_argument("--samples", type=int, default=100, metavar="N",
                    help="采样行数(默认 100)")
    ap.add_argument("--top", type=int, default=5, metavar="N",
                    help="最多展示的模板数(默认 5)")
    ap.add_argument("--all", action="store_true", help="展示全部模板")
    args = ap.parse_args(argv)

    if args.file == "-":
        try:
            sys.stdin.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
        fh, src = sys.stdin, "<stdin>"
    else:
        try:
            fh = open(args.file, "r", encoding="utf-8", errors="replace")
        except OSError as exc:
            print("错误: 无法打开 %s: %s" % (args.file, exc), file=sys.stderr)
            return 2
        src = args.file

    samples = []
    try:
        for line in fh:
            line = line.rstrip("\r\n")
            if line.strip():
                samples.append(line)
                if len(samples) >= max(1, args.samples):
                    break
    finally:
        if fh is not sys.stdin:
            fh.close()

    if not samples:
        print("错误: 未采样到任何非空日志行", file=sys.stderr)
        return 1

    counter = Counter()
    meta = {}
    for line in samples:
        classes, regex = template_safe(line)
        counter[regex] += 1
        meta.setdefault(regex, (classes, line))

    out = sys.stdout
    out.write("采样行数: %d (来源: %s)\n" % (len(samples), src))
    out.write("归纳出 %d 种字段模板:\n\n" % len(counter))
    shown = counter.most_common() if args.all else counter.most_common(max(1, args.top))
    for rank, (regex, cnt) in enumerate(shown, 1):
        classes, example = meta[regex]
        labels = " ".join(CLASS_INFO[c][0] for c in classes)
        out.write("[模板 %d] 命中 %d/%d 行 (%.1f%%)\n"
                  % (rank, cnt, len(samples), 100.0 * cnt / len(samples)))
        out.write("  字段布局: %s\n" % (labels or "(空)"))
        out.write("  正则模板: %s\n" % regex)
        out.write("  示例行  : %s\n\n" % example[:200])
    hidden = len(counter) - len(shown)
    if hidden > 0:
        out.write("(还有 %d 种模板未展示, 可加 --all 查看)\n" % hidden)
    return 0


if __name__ == "__main__":
    sys.exit(main())
