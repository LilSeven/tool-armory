#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""章节号规范化——统一章节标题格式并重排连续序号, 报告缺失章节。

识别「第X章/节/卷/回/部/集/篇」（中文/阿拉伯/全角数字）与 Chapter N 标题,
按出现顺序重排为 1..N 连续序号, 统一为目标风格:
    --style arabic   第1章 / 第2章 …   （默认）
    --style chinese  第一章 / 第二章 …
    --style chapter  Chapter 1 / Chapter 2 …
标题副题保留（第一章：初见 → 第1章：初见）; 序章/楔子/番外等无编号标题原样保留。
若原编号跳号/重号/乱序, 在 stderr 报告缺失章节（按章节号推算, 供人工核对）。

用法:
    python chapter-renumber.py input.txt -o output.txt --style arabic
    python chapter-renumber.py input.txt -o output.txt --style chinese --report mapping.txt
    python chapter-renumber.py input.txt --dry-run

退出码: 0=成功; 2=参数/文件错误。
"""

import argparse
import re
import sys
from pathlib import Path

_TAIL = r"(?=\s|[。．.，,、；;：:！!？?·~\-—（《“'\"〔【】）]|$)"

HEADING = re.compile(
    r"^\s*(?:"
    r"第\s*(?P<num>[0-9０-９零〇一二三四五六七八九十百千万两]+)\s*(?P<unit>[章节卷回部集篇])"
    r"|(?:chapter|chap)\s*\.?\s*(?P<en>\d+)"
    r")" + _TAIL,
    re.IGNORECASE,
)
LOOSE_HEADING = re.compile(
    r"^\s*(?:"
    r"第\s*(?P<num>[0-9０-９零〇一二三四五六七八九十百千万两]+)\s*(?P<unit>[章节卷回部集篇])"
    r"|(?:chapter|chap)\s*\.?\s*(?P<en>\d+)"
    r")",
    re.IGNORECASE,
)

_CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_DIGITS = "零一二三四五六七八九"
_UNITS = ["", "十", "百", "千"]
_JOIN_PUNCT = "。．.，,、；;：:！!？?·~-—~"


def _reconfig():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(msg):
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(2)


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


def write_text(path, text, encoding):
    with open(path, "w", encoding=encoding, newline="") as fh:
        fh.write(text)


def cn_to_int(s):
    """中文/阿拉伯数字字符串 → int; 无法解析返回 None。如 十二→12, 第2章的 2→2。"""
    s = s.strip()
    if not s:
        return None
    if all(ch.isdigit() for ch in s):
        return int(s)
    total, num = 0, 0
    for ch in s:
        if ch in _CN_DIGIT:
            num = _CN_DIGIT[ch]
        elif ch == "十":
            total += (num or 1) * 10
            num = 0
        elif ch == "百":
            total += (num or 1) * 100
            num = 0
        elif ch == "千":
            total += (num or 1) * 1000
            num = 0
        elif ch == "万":
            total = (total + num) * 10000
            num = 0
        elif ch in "零〇":
            continue
        else:
            return None
    return total + num


def int_to_cn(n):
    """1..99999999 → 中文数字, 如 12→十二, 103→一百零三。"""
    if n <= 0:
        return str(n)
    if n >= 10000:
        w, r = divmod(n, 10000)
        head = int_to_cn(w) + "万"
        if r:
            if r < 1000:
                head += "零"
            head += int_to_cn(r)
        return head
    if 10 <= n < 20:
        return "十" + (_DIGITS[n % 10] if n % 10 else "")
    out, zero = "", False
    for pos, ch in enumerate(f"{n:04d}"):
        d = int(ch)
        u = _UNITS[3 - pos]
        if d == 0:
            if out:
                zero = True
            continue
        if zero:
            out += "零"
            zero = False
        out += _DIGITS[d] + u
    return out


def make_heading(style, num, unit, rest):
    if style == "arabic":
        prefix = f"第{num}{unit or '章'}"
    elif style == "chinese":
        prefix = f"第{int_to_cn(num)}{unit or '章'}"
    else:
        prefix = f"Chapter {num}"
    if not rest:
        return prefix
    if rest[0] in _JOIN_PUNCT:
        return prefix + rest
    return prefix + " " + rest


def main(argv=None):
    _reconfig()
    ap = argparse.ArgumentParser(
        prog="chapter-renumber",
        description="统一章节标题格式（第一章/第1章/Chapter 1 → 目标风格）并重排连续序号",
    )
    ap.add_argument("input", help="输入 TXT 文件")
    ap.add_argument("-o", "--output", help="输出文件; 缺省打印到 stdout")
    ap.add_argument("--style", choices=("arabic", "chinese", "chapter"), default="arabic",
                    help="目标风格: arabic=第1章(默认), chinese=第一章, chapter=Chapter 1")
    ap.add_argument("--report", help="把 原标题→新标题 映射写入该文件")
    ap.add_argument("--dry-run", action="store_true", help="只打印报告, 不写出/不打印正文")
    ap.add_argument("--loose", action="store_true", help="放宽校验: 章节号后不要求空白/标点")
    ap.add_argument("--encoding", default="auto", help="输入编码, auto=尝试 utf-8/gb18030/big5")
    ap.add_argument("--out-encoding", default="utf-8", help="输出文件编码（默认 utf-8）")
    args = ap.parse_args(argv)

    pattern = LOOSE_HEADING if args.loose else HEADING
    try:
        text = read_text(args.input, args.encoding)
    except OSError as exc:
        die(f"读取输入失败: {exc}")

    lines = text.splitlines()
    new_lines, mapping, nums = [], [], []
    seq = 0
    for lineno, line in enumerate(lines, 1):
        m = pattern.match(line)
        if not m:
            new_lines.append(line)
            continue
        seq += 1
        if m.group("en") is not None:
            orig, unit = int(m.group("en")), None
        else:
            orig, unit = cn_to_int(m.group("num")), m.group("unit")
        rest = line[m.end():].strip()
        new_line = make_heading(args.style, seq, unit, rest)
        new_lines.append(new_line)
        mapping.append((lineno, line.strip(), new_line))
        nums.append(orig)

    report = [f"[chapter-renumber] 重排 {seq} 个章节标题 → 风格 {args.style}"]
    gaps, disorder = [], []
    prev = None
    for orig in nums:
        if orig is None:
            continue
        if prev is not None:
            if orig > prev + 1:
                gaps.append((prev, orig))
            elif orig <= prev:
                disorder.append((prev, orig))
        prev = orig
    if not seq:
        report.append("未发现可重排的章节标题。")
    elif not gaps and not disorder:
        report.append("原编号连续, 未发现缺失章节。")
    else:
        for a, b in gaps:
            missing = f"第{a + 1}章" if b - a == 2 else f"第{a + 1}章~第{b - 1}章"
            report.append(f"缺失: {missing} (原编号 {a} 之后直接是 {b})")
        for a, b in disorder:
            report.append(f"乱序/重号: 原编号 {b} 紧跟 {a} 之后 (未递增)")

    if args.dry_run:
        report.append("（dry-run, 未写出结果）")
        print("\n".join(report), file=sys.stderr)
        return 0

    out_text = "\n".join(new_lines) + ("\n" if new_lines else "")
    if args.output:
        write_text(args.output, out_text, args.out_encoding)
        report.append(f"结果已写入: {args.output}")
    else:
        sys.stdout.write(out_text)

    if args.report:
        rows = ["原行号\t原标题\t→\t新标题"]
        rows += [f"L{ln}\t{old}\t→\t{new}" for ln, old, new in mapping]
        write_text(args.report, "\n".join(rows) + "\n", args.out_encoding)
        report.append(f"映射已写入: {args.report}")

    print("\n".join(report), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
