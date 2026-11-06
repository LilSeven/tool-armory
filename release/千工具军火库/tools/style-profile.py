#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""排版风格预设套用 — 提供「出版/网络文章/GitHub/字幕」等预设，一键按预设
参数组合应用各清洗规则。

每套预设是一组参数组合（BOM、零宽字符、换行符、中西文空格、标点全半角、
全角字母数字、弯引号、行尾空白）。默认 dry-run，只输出将生效的改动统计；
加 --write 才写回文件。Markdown（.md/.markdown/.mdown）默认自动跳过围栏
代码块、行内代码、URL 与链接目标，可用 --md / --no-md 强制开关。

预设一览：
  publish   出版：全角标点＋弯引号＋中西文空格＋全角字母数字转半角，LF
  web       网络文章：全角标点＋中西文空格＋全角字母数字转半角，LF
  github    GitHub：中西文空格＋行尾空白清理，LF；不改标点（对代码友好）
  subtitle  字幕：全角标点＋中西文空格＋行尾空白清理，CRLF（播放器兼容）

示例命令：
  python style-profile.py --list
  python style-profile.py article.md --profile github             # 预览改动
  python style-profile.py article.md --profile github --write
  python style-profile.py sub.srt --profile subtitle --write
  python style-profile.py a.txt --profile publish --eol crlf --write
  cat in.txt | python style-profile.py --profile web > out.txt

退出码：0 成功；2 参数/读取/写入错误。
"""

import argparse
import re
import sys
from collections import defaultdict

CJK = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
CJK_PUNCT = "，。、；：？！…—·“”‘’「」『』（）《》〈〉【】～"
HALF2FULL = {",": "，", ".": "。", ";": "；", ":": "：", "?": "？", "!": "！"}
ZW_RE = re.compile("[\u200b\u200c\u200d\ufeff\u2060\u00ad]")
RE_CJKISH = re.compile("[" + CJK + CJK_PUNCT + "]")
RE_BOUNDARY = re.compile(
    "(?<=[%(c)s])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[%(c)s])" % {"c": CJK})
RE_NUM_DATE = re.compile(r"(?<=[0-9]) (?=[年月日天时分秒周])")
RE_FW_ALNUM = re.compile("[\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]")
RE_DQ = re.compile("\"([^\"\n]*[" + CJK + "][^\"\n]*)\"")
RE_SQ = re.compile("'([^'\n]*[" + CJK + "][^'\n]*)'")

RE_PROTECT = re.compile(
    r"https?://[^\s)\]}>'\"，。；！？]+"
    r"|`+[^`\n]*`+"
    r"|\]\([^)\n]*\)"
    r"|<[^>\n\s]*>"
)
RE_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")

PROFILES = {
    "publish": {
        "label": "出版（全角标点＋弯引号＋中西文空格）",
        "eol": "lf", "space_cn_en": True, "half_to_full": True,
        "fw_alnum_to_half": True, "curly_quotes": True,
        "trim_trailing": False, "md": True,
    },
    "web": {
        "label": "网络文章（全角标点＋中西文空格）",
        "eol": "lf", "space_cn_en": True, "half_to_full": True,
        "fw_alnum_to_half": True, "curly_quotes": False,
        "trim_trailing": False, "md": True,
    },
    "github": {
        "label": "GitHub（中西文空格＋行尾清理，不改标点）",
        "eol": "lf", "space_cn_en": True, "half_to_full": False,
        "fw_alnum_to_half": False, "curly_quotes": False,
        "trim_trailing": True, "md": True,
    },
    "subtitle": {
        "label": "字幕（全角标点＋CRLF＋行尾清理）",
        "eol": "crlf", "space_cn_en": True, "half_to_full": True,
        "fw_alnum_to_half": True, "curly_quotes": False,
        "trim_trailing": True, "md": False,
    },
}


def split_free(line):
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


def transform_free(seg, prof, stats):
    """对一行内的可自由文本段按预设做变换。"""
    if prof.get("curly_quotes"):
        seg, n = RE_DQ.subn("“\\1”", seg)
        seg, n2 = RE_SQ.subn("‘\\1’", seg)
        stats["curly-quotes"] += n + n2
    if prof.get("half_to_full"):
        chars = []
        for i, ch in enumerate(seg):
            if ch in HALF2FULL:
                prev = seg[i - 1] if i > 0 else ""
                nxt = seg[i + 1] if i + 1 < len(seg) else ""
                # 同一符号连写（如 ... 或 !!）不转换，避免变成「。..」
                if ((RE_CJKISH.match(prev) or RE_CJKISH.match(nxt))
                        and prev != ch and nxt != ch):
                    ch = HALF2FULL[ch]
                    stats["punct-half→full"] += 1
            chars.append(ch)
        seg = "".join(chars)
    if prof.get("fw_alnum_to_half"):
        def _half(m):
            stats["fw-alnum→half"] += 1
            return chr(ord(m.group(0)) - 0xFEE0)
        seg = RE_FW_ALNUM.sub(_half, seg)
    if prof.get("space_cn_en"):
        seg, n = RE_BOUNDARY.subn(" ", seg)
        # 数字与「年月日…」之间不空格（2023 年 → 2023年）
        seg, n2 = RE_NUM_DATE.subn("", seg)
        stats["space-cn-en"] += n - n2
    return seg


def transform_line(line, prof, stats):
    new = ZW_RE.sub("", line)
    if new != line:
        stats["strip-zw"] += len(line) - len(new)
        line = new
    pieces = []
    for _start, seg, protected in split_free(line):
        pieces.append(seg if protected else transform_free(seg, prof, stats))
    new = "".join(pieces)
    if prof.get("trim_trailing"):
        stripped = new.rstrip()
        if stripped != new:
            stats["trim-trailing"] += 1
            new = stripped
    return new


def count_eols(text):
    crlf = text.count("\r\n")
    return crlf, text.count("\n") - crlf, text.count("\r") - crlf


def transform_text(text, prof, md_aware, stats):
    """全文按预设变换（内部先归一为 LF，最后再转目标风格）。"""
    eol_changes_target = prof["eol"]
    crlf, lf, cr = count_eols(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    fence = None
    out = []
    for line in lines:
        if md_aware:
            m = RE_FENCE.match(line)
            if fence is None:
                if m:
                    fence = (m.group(1)[0], len(m.group(1)))
                    out.append(line)
                    continue
            else:
                out.append(line)
                if (m and m.group(1)[0] == fence[0]
                        and len(m.group(1)) >= fence[1]
                        and not m.group(2).strip()):
                    fence = None
                continue
        out.append(transform_line(line, prof, stats))
    joined = "\n".join(out)
    nl = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}[prof["eol"]]
    if nl != "\n":
        joined = joined.replace("\n", nl)
    changes = {"lf": crlf + cr, "crlf": lf + cr, "cr": lf + crlf}[eol_changes_target]
    if changes:
        stats["eol"] = "→ %s（统一 %d 处换行）" % (prof["eol"].upper(), changes)
    return joined


def _setup_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def read_text(raw):
    """优先 UTF-8（去 BOM），失败退 gb18030；返回 (文本, 是否有 BOM, 编码)。"""
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:] if had_bom else raw
    try:
        return body.decode("utf-8"), had_bom, "utf-8"
    except UnicodeDecodeError:
        return body.decode("gb18030"), had_bom, "gb18030"


def report_and_save(name, text, had_bom, prof, args, md_aware):
    stats = defaultdict(int)
    new_text = transform_text(text, prof, md_aware, stats)
    if had_bom:
        stats["strip-bom"] = 1
    action = "已写入" if args.write else "dry-run（加 --write 生效）"
    print("%s: 预设 %s%s" % (name, args.profile, "（%s）" % action))
    order = ["strip-bom", "strip-zw", "curly-quotes", "punct-half→full",
             "fw-alnum→half", "space-cn-en", "trim-trailing", "eol"]
    keys = [k for k in order if stats.get(k)]
    if not keys:
        print("  无需改动")
    for k in keys:
        print("  %-16s %s" % (k, stats[k]))
    if args.write and stats:
        try:
            with open(name, "w", encoding="utf-8", newline="") as fh:
                fh.write(new_text)
        except OSError as exc:
            print("%s: 错误：写入失败（%s）" % (name, exc), file=sys.stderr)
            return 2
    elif args.write and not stats:
        print("  （内容已符合预设，未写入）")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="按风格预设（出版/网络文章/GitHub/字幕）一键应用清洗规则")
    ap.add_argument("files", nargs="*",
                    help="待处理文件；缺省时读 stdin 写 stdout（管道模式）")
    ap.add_argument("--profile", choices=sorted(PROFILES), help="风格预设名称")
    ap.add_argument("--list", action="store_true", help="列出全部预设并退出")
    ap.add_argument("--write", action="store_true", help="写回文件（默认 dry-run）")
    ap.add_argument("--eol", choices=["lf", "crlf", "cr"],
                    help="覆盖预设的换行风格")
    md_group = ap.add_mutually_exclusive_group()
    md_group.add_argument("--md", action="store_true",
                          help="强制开启 Markdown 感知（跳过代码块等）")
    md_group.add_argument("--no-md", action="store_true",
                          help="强制关闭 Markdown 感知")
    args = ap.parse_args(argv)
    _setup_utf8_stdio()

    if args.list:
        print("可用预设（--profile <名称>）：")
        for pname in sorted(PROFILES):
            p = PROFILES[pname]
            print("  %-9s %s ｜ eol=%s" % (pname, p["label"], p["eol"]))
        return 0
    if not args.profile:
        ap.error("请用 --profile 指定预设（--list 可查看全部预设）")
    prof = dict(PROFILES[args.profile])
    if args.eol:
        prof["eol"] = args.eol

    def md_flag(fname):
        if args.no_md:
            return False
        if args.md:
            return True
        return prof["md"] and fname.lower().endswith((".md", ".markdown", ".mdown"))

    errors = 0
    if not args.files:
        if sys.stdin.isatty():
            ap.error("没有输入文件，且 stdin 是终端；请传入文件或用管道喂入")
        raw = sys.stdin.buffer.read()
        try:
            text, _bom, _enc = read_text(raw)
        except UnicodeDecodeError as exc:
            print("stdin: 错误：无法解码（%s）" % exc, file=sys.stderr)
            return 2
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(newline="")
            except Exception:
                pass
        new_text = transform_text(text, prof, bool(args.md), defaultdict(int))
        sys.stdout.write(new_text)
        return 0

    for name in args.files:
        try:
            with open(name, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            print("%s: 错误：无法读取（%s）" % (name, exc), file=sys.stderr)
            errors += 1
            continue
        try:
            text, had_bom, _enc = read_text(raw)
        except UnicodeDecodeError as exc:
            print("%s: 错误：无法解码（%s）" % (name, exc), file=sys.stderr)
            errors += 1
            continue
        errors += report_and_save(name, text, had_bom, prof, args, md_flag(name))
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
