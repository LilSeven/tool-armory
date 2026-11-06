#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并排 diff 查看器：解析 unified diff，在终端里左右并排、按差异着色显示。

左列是旧文件行（删除行红色），右列是新文件行（新增行绿色），上下文行
两侧同显；相邻的 -/+ 行按出现顺序配对对齐，单侧多出的行另一侧留空。
行超宽时按“显示宽度”截断（中文等全角字符按 2 列计），--width 0 不截断。

用法:
    python diff-side-by-side.py [patch文件|-] [--width N] [--color auto|always|never]
    patch 省略或为 "-" 时从 stdin 读取。

示例:
    git diff | python diff-side-by-side.py
    python diff-side-by-side.py changes.patch --width 100
    diff -u old.txt new.txt | python diff-side-by-side.py --width 0 --color always
"""

import argparse
import os
import re
import shutil
import sys
import unicodedata

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


def _dwidth(s):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _clip(s, width):
    """按显示宽度截断，超出部分以 ~ 结尾；width<=0 表示不截断。"""
    if width <= 0 or _dwidth(s) <= width:
        return s
    out, acc = "", 0
    for ch in s:
        w = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if acc + w > width - 1:
            return out + "~"
        out, acc = out + ch, acc + w
    return out


def _pad(s, width):
    return s + " " * max(0, width - _dwidth(s))


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


def render(events, paint, width):
    """把事件流渲染成并排显示的文本行列表。"""
    nums = [v for e in events if e[0] == "row" for v in (e[2], e[3]) if v is not None]
    num_w = max([4] + [len(str(n)) for n in nums])
    if width is None:
        width = shutil.get_terminal_size(fallback=(100, 24)).columns
    text_w = 0 if width <= 0 else max(8, (width - 2 * (num_w + 1) - 3) // 2)

    out = []
    pending = []

    def flush_pending():
        if not pending:
            return
        olds = [p for p in pending if p[1] == "-"]
        news = [p for p in pending if p[1] == "+"]
        pending.clear()
        for i in range(max(len(olds), len(news))):
            left = olds[i] if i < len(olds) else None
            right = news[i] if i < len(news) else None
            l_no = f"{left[2]:>{num_w}}" if left else " " * num_w
            r_no = f"{right[3]:>{num_w}}" if right else " " * num_w
            l_txt = (left[4] if left else "").expandtabs(4)
            r_txt = (right[4] if right else "").expandtabs(4)
            if text_w:
                l_txt = _pad(_clip(l_txt, text_w), text_w)
                r_txt = _pad(_clip(r_txt, text_w), text_w)
            l_col = paint(l_txt, RED) if left else l_txt
            r_col = paint(r_txt, GREEN) if right else r_txt
            out.append(f"{l_no} {l_col} | {r_no} {r_col}")

    for ev in events:
        if ev[0] == "row" and ev[1] == " ":
            flush_pending()
            txt = ev[4].expandtabs(4)
            if text_w:
                txt = _pad(_clip(txt, text_w), text_w)
            out.append(f"{ev[2]:>{num_w}} {txt} | {ev[3]:>{num_w}} {txt}")
        elif ev[0] == "row":
            pending.append(ev)
        else:
            flush_pending()
            out.append(paint(ev[1], CYAN if ev[0] == "hunk" else DIM))
    flush_pending()
    return out


def main(argv=None):
    _utf8_stdout()
    ap = argparse.ArgumentParser(
        description="解析 unified diff，终端左右并排着色显示差异。")
    ap.add_argument("patch", nargs="?", default="-",
                    help="unified diff 文件路径；'-' 或省略表示读 stdin")
    ap.add_argument("--width", type=int, default=None,
                    help="输出总宽度(列)；0=不截断；缺省=自动检测终端宽度")
    ap.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                    help="着色模式(缺省 auto: 仅输出到终端时着色)")
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
    for line in render(parse_patch(data.decode("utf-8", "replace")), paint, args.width):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
