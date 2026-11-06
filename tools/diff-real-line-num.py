#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diff 真实行号：解析 unified diff，在 hunk 头旁补充新旧版本文件中的实际行号范围，
并为 hunk 内每行标注它在旧/新文件中的真实行号，免去逐行手数。

输出示例:
    @@ -3,7 +3,8 @@   <= old L3-L9; new L3-L10
      3    3  context line
      4       -removed line
           4  +added line
每行前两列分别为该行在旧文件/新文件中的真实行号（删除行没有新号、
新增行没有旧号），其后保留原 diff 行内容（含 +/-/空格 前缀）；
hunk 头行尾注释给出整个 hunk 覆盖的旧/新文件实际行号范围
（计数为 0 的一侧按 GNU 惯例标注插入点，如 "new after L3"）。

用法:
    python diff-real-line-num.py [patch文件|-] [--color auto|always|never]
    patch 省略或为 "-" 时从 stdin 读取。

示例:
    git diff | python diff-real-line-num.py
    python diff-real-line-num.py changes.patch --color always
"""

import argparse
import os
import re
import sys

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
RESET = "\033[0m"
DIM, CYAN = "\033[2m", "\033[36m"
RED, GREEN = "\033[31m", "\033[32m"


def _utf8_stdout():
    """尽量把 stdout 切到 UTF-8，避免 Windows 控制台中文乱码。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _color_enabled(mode):
    if mode == "always":
        return True
    if mode == "never":
        return False
    return (sys.stdout.isatty()
            and not os.environ.get("NO_COLOR")
            and os.environ.get("TERM", "") != "dumb")


def _make_paint(enabled):
    def paint(text, code):
        if not enabled or not code:
            return text
        return code + text + RESET
    return paint


def parse_patch(text):
    """解析 unified diff 文本为事件列表:
      ("hdr", line)                        文件头/杂项行
      ("hunk", line)                       @@ hunk 头
      ("row", kind, old_no, new_no, text)  正文行, kind ∈ "-+ "
      ("nonl", line)                       \\ No newline ... 行
    old_no/new_no 是该行在旧/新文件中的真实行号（不存在的一侧为 None）。
    """
    events = []
    in_hunk = False
    o_no = n_no = 0
    o_rem = n_rem = 0
    for raw in text.splitlines():
        line = raw[:-1] if raw.endswith("\r") else raw
        m = HUNK_RE.match(line)
        if m:
            in_hunk = True
            o_no, n_no = int(m.group(1)), int(m.group(3))
            o_rem = int(m.group(2)) if m.group(2) is not None else 1
            n_rem = int(m.group(4)) if m.group(4) is not None else 1
            events.append(("hunk", line))
            continue
        if in_hunk:
            if line.startswith("\\"):
                events.append(("nonl", line))
                continue
            head = line[:1]
            if head == "-" and o_rem > 0:
                events.append(("row", "-", o_no, None, line[1:]))
                o_no, o_rem = o_no + 1, o_rem - 1
                continue
            if head == "+" and n_rem > 0:
                events.append(("row", "+", None, n_no, line[1:]))
                n_no, n_rem = n_no + 1, n_rem - 1
                continue
            if (head == " " or line == "") and o_rem > 0 and n_rem > 0:
                events.append(("row", " ", o_no, n_no, line[1:]))
                o_no, n_no = o_no + 1, n_no + 1
                o_rem, n_rem = o_rem - 1, n_rem - 1
                continue
            in_hunk = False  # 计数已尽/无法识别：后续行按 hunk 外杂项处理
        events.append(("hdr", line))
    return events


def _range_txt(lo, cnt, side):
    if cnt > 0:
        return f"{side} L{lo}-L{lo + cnt - 1}"
    if lo <= 0:
        return f"{side} before L1 (0 lines)"
    return f"{side} after L{lo} (0 lines)"


def annotate(events, paint):
    """给事件流加上真实行号：hunk 头旁补充行号范围，正文每行前缀行号两列。"""
    nums = [v for e in events if e[0] == "row" for v in (e[2], e[3]) if v is not None]
    num_w = max([4] + [len(str(n)) for n in nums])
    out = []
    for ev in events:
        if ev[0] == "hunk":
            m = HUNK_RE.match(ev[1])
            o_lo = int(m.group(1))
            o_cnt = int(m.group(2)) if m.group(2) is not None else 1
            n_lo = int(m.group(3))
            n_cnt = int(m.group(4)) if m.group(4) is not None else 1
            note = (f"   <= {_range_txt(o_lo, o_cnt, 'old')}; "
                    f"{_range_txt(n_lo, n_cnt, 'new')}")
            out.append(paint(ev[1], CYAN) + paint(note, DIM))
        elif ev[0] == "row":
            _, sign, o_no, n_no, txt = ev
            o_col = f"{o_no:>{num_w}}" if o_no is not None else " " * num_w
            n_col = f"{n_no:>{num_w}}" if n_no is not None else " " * num_w
            color = RED if sign == "-" else (GREEN if sign == "+" else "")
            out.append(f"{o_col} {n_col} {paint(sign + txt, color)}")
        else:  # hdr / nonl
            out.append(paint(ev[1], DIM))
    return out


def main(argv=None):
    _utf8_stdout()
    ap = argparse.ArgumentParser(
        description="在 unified diff 的 hunk 头旁补充新旧文件实际行号，并给每行标注真实行号。")
    ap.add_argument("patch", nargs="?", default="-",
                    help="unified diff 文件路径；'-' 或省略表示读 stdin")
    ap.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                    help="着色模式(缺省 auto)")
    args = ap.parse_args(argv)

    try:
        if args.patch == "-":
            data = sys.stdin.buffer.read()
        else:
            with open(args.patch, "rb") as fh:
                data = fh.read()
    except OSError as exc:
        print(f"错误: 读取失败: {exc}", file=sys.stderr)
        return 2

    paint = _make_paint(_color_enabled(args.color))
    for line in annotate(parse_patch(data.decode("utf-8", "replace")), paint):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
