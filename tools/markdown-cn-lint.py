#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文 Markdown 排版检查 — 按《中文文案排版指北》检查 Markdown，输出违规清单。

检查项（规则 id）：
  cn-en-space   中西文之间缺空格（汉字与拉丁字母/数字直接相连）
  punct-half    中文语境使用半角标点（,.;:?! 紧邻汉字，如「测试,test」）
  punct-full    英文/数字语境使用全角标点（，。；：？！前后 8 字内无汉字，启发式）
  punct-repeat  全角标点连续重复（如「。。」「！！！」）
  fw-alnum      使用全角字母/数字（Ａ ｂ ０ ９）
  zero-width    存在零宽字符（U+200B/200C/200D/FEFF/2060/00AD）
  code-lang     围栏代码块缺少语言标注（``` 后没有语言）

检查时自动跳过：围栏代码块内部、行内代码、URL、Markdown 链接目标与 HTML 标签。

示例命令：
  python markdown-cn-lint.py README.md
  python markdown-cn-lint.py a.md b.md --max 20
  python markdown-cn-lint.py README.md --strict   # 有违规时退出码 1，便于 CI

退出码：0 无违规（或未加 --strict）；1 有违规且加了 --strict；2 读取失败。
"""

import argparse
import re
import sys

# ---------- 字符类 ----------
CJK = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"           # 汉字
CJK_PUNCT = "，。、；：？！…—·“”‘’「」『』（）《》〈〉【】～"
HALF2FULL = {",": "，", ".": "。", ";": "；", ":": "：", "?": "？", "!": "！"}
FULL_PUNCT = "，。；：？！"
REPEAT_PUNCT = "，。；：？！、"
FW_ALNUM = "\uff10-\uff19\uff21-\uff3a\uff41-\uff5a"
ZW_CHARS = {
    "\u200b": "零宽空格 U+200B",
    "\u200c": "零宽不连字 U+200C",
    "\u200d": "零宽连接符 U+200D",
    "\ufeff": "零宽不换行空格 U+FEFF",
    "\u2060": "字词连接符 U+2060",
    "\u00ad": "软连字符 U+00AD",
}

RE_CJK = re.compile("[" + CJK + "]")
RE_CJKISH = re.compile("[" + CJK + CJK_PUNCT + "]")       # 汉字或全角标点
RE_ZW = re.compile("[" + "".join(ZW_CHARS) + "]")
RE_BOUNDARY = re.compile(
    "(?<=[%(c)s])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[%(c)s])" % {"c": CJK})
RE_HALF_PUNCT = re.compile("[,.;:?!]")
RE_FULL_PUNCT = re.compile("[" + FULL_PUNCT + "]")
RE_REPEAT = re.compile("([" + REPEAT_PUNCT + "])\\1+")
RE_FW_ALNUM = re.compile("[" + FW_ALNUM + "]")

# 行内需要原样保护的内容
RE_PROTECT = re.compile(
    r"https?://[^\s)\]}>'\"，。；！？]+"    # URL
    r"|`+[^`\n]*`+"                        # 行内代码
    r"|\]\([^)\n]*\)"                      # Markdown 链接目标
    r"|<[^>\n\s]*>"                        # HTML 标签 / <autolink>
)
RE_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")

READ_ORDER = ("utf-8", "gb18030", "big5", "latin-1")


def split_free(line):
    """把一行切成 [(起始偏移, 文本, 是否受保护)] 段，保持原始列号。"""
    parts = []
    pos = 0
    for m in RE_PROTECT.finditer(line):
        if m.start() > pos:
            parts.append((pos, line[pos:m.start()], False))
        parts.append((m.start(), m.group(0), True))
        pos = m.end()
    if pos < len(line):
        parts.append((pos, line[pos:], False))
    return parts


def iter_fenced(lines):
    """逐行产出 (下标, 行, 是否在代码块内, 标记)。

    标记仅在围栏行上有值：("open", 语言信息串) 或 ("close", "")。
    """
    fence_char = None
    fence_len = 0
    for i, line in enumerate(lines):
        m = RE_FENCE.match(line)
        if fence_char is None:
            if m:
                fence_char, fence_len = m.group(1)[0], len(m.group(1))
                yield i, line, True, ("open", m.group(2).strip())
            else:
                yield i, line, False, None
        else:
            if (m and m.group(1)[0] == fence_char
                    and len(m.group(1)) >= fence_len
                    and not m.group(2).strip()):
                fence_char = None
                yield i, line, True, ("close", "")
            else:
                yield i, line, True, None


def check_line(ln, line, findings):
    """对一行执行各项检查（列号从 1 开始）。"""
    for m in RE_ZW.finditer(line):
        findings.append((ln, m.start() + 1, "zero-width",
                         "零宽字符：%s（建议删除）" % ZW_CHARS[m.group(0)]))
    for start, seg, protected in split_free(line):
        if protected:
            continue
        # 中西文之间缺空格
        for m in RE_BOUNDARY.finditer(seg):
            findings.append((ln, start + m.start() + 1, "cn-en-space",
                             "中西文之间建议加一个半角空格"))
        # 中文语境的半角标点
        for m in RE_HALF_PUNCT.finditer(seg):
            j = m.start()
            prev = seg[j - 1] if j > 0 else ""
            nxt = seg[j + 1] if j + 1 < len(seg) else ""
            if RE_CJKISH.match(prev) or RE_CJKISH.match(nxt):
                findings.append((ln, start + j + 1, "punct-half",
                                 "中文语境应使用全角标点：%s → %s"
                                 % (m.group(0), HALF2FULL[m.group(0)])))
        # 英文/数字语境的全角标点（启发式：前后 8 字内无汉字）
        for m in RE_FULL_PUNCT.finditer(seg):
            j = m.start()
            ctx = seg[max(0, j - 8):j] + seg[j + 1:j + 9]
            if not RE_CJK.search(ctx):
                findings.append((ln, start + j + 1, "punct-full",
                                 "英文/数字语境疑似应使用半角标点：%s" % m.group(0)))
        # 全角标点重复
        for m in RE_REPEAT.finditer(seg):
            findings.append((ln, start + m.start() + 1, "punct-repeat",
                             "全角标点重复：“%s”" % m.group(0)))
        # 全角字母/数字
        for m in RE_FW_ALNUM.finditer(seg):
            ch = m.group(0)
            findings.append((ln, start + m.start() + 1, "fw-alnum",
                             "全角字母/数字：%s → %s" % (ch, chr(ord(ch) - 0xFEE0))))


def lint_text(text):
    """返回违规列表 [(行号, 列号, 规则, 说明)]，按位置排序。"""
    findings = []
    lines = text.splitlines()
    for i, line, is_code, tag in iter_fenced(lines):
        ln = i + 1
        if tag and tag[0] == "open" and not tag[1]:
            findings.append((ln, 1, "code-lang",
                             "围栏代码块缺少语言标注（``` 后未指定语言）"))
        if is_code:
            continue
        check_line(ln, line, findings)
    findings.sort(key=lambda f: (f[0], f[1]))
    return findings


def decode_best(raw):
    """按常见编码依次尝试解码，返回 (文本, 编码名)；全部失败抛最后一个异常。"""
    last = None
    for enc in READ_ORDER:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError as exc:
            last = exc
    raise last


def _setup_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="中文 Markdown 排版检查（中文文案排版指北），输出违规清单")
    ap.add_argument("files", nargs="+", help="待检查的 Markdown / 文本文件")
    ap.add_argument("--strict", action="store_true",
                    help="发现违规时退出码置 1（CI 用）")
    ap.add_argument("--max", type=int, default=100, metavar="N",
                    help="每个文件最多显示 N 条（0 = 不限，默认 100）")
    args = ap.parse_args(argv)
    _setup_utf8_stdio()

    total = 0
    hard_errors = 0
    for name in args.files:
        try:
            with open(name, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            print("%s: 错误：无法读取（%s）" % (name, exc), file=sys.stderr)
            hard_errors += 1
            continue
        try:
            text, enc = decode_best(raw)
        except UnicodeDecodeError as exc:
            print("%s: 错误：无法解码（%s）" % (name, exc), file=sys.stderr)
            hard_errors += 1
            continue
        findings = lint_text(text)
        total += len(findings)
        print("==> %s（%s，%d 行，%d 处违规）"
              % (name, enc, len(text.splitlines()), len(findings)))
        shown = findings if args.max <= 0 else findings[:args.max]
        for ln, col, rule, msg in shown:
            print("  %s:%d:%d  [%s]  %s" % (name, ln, col, rule, msg))
        hidden = len(findings) - len(shown)
        if hidden > 0:
            print("  …（另有 %d 条未显示，可用 --max 0 查看）" % hidden)

    print("共 %d 处违规。" % total)
    if args.strict and total:
        return 1
    return 2 if hard_errors else 0


if __name__ == "__main__":
    sys.exit(main())
