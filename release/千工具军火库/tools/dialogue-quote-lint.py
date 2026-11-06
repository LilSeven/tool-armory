#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小说对话引号检查——检查对话引号是否成对、是否与叙述错层混用, 输出待修列表。

按行（TXT 小说通常一段一行）检查:
  1. 先闭后开: 行内闭引号（”/」/』）出现在对应开引号之前（错层）;
  2. 未闭合: 含开引号的行行末仍有未闭合引号（常见漏写收尾引号）;
  3. 段落末悬挂: 空行前仍有未闭合引号（对话疑似跨段/错层, 按段落边界复位）;
  4. 文件末悬挂: 全文结束时仍有未闭合引号;
  5. 直引号奇数: 半角 " 一行内数量为奇数, 无法两两配对;
  6. 风格混用: 同一行同时出现半角直引号 " 与弯/角引号（常见复制粘贴错层）;
  7. 汇总: 各风格引号全文开/闭总数是否相等（不等会标注）。
待修列表含 行号/类型/说明/原文摘录, 输出到 stdout 或 --output 文件。

用法:
    python dialogue-quote-lint.py 小说.txt
    python dialogue-quote-lint.py 小说.txt -o 待修列表.txt
    python dialogue-quote-lint.py 小说.txt --strict          # 有问题时退出码 1
    python dialogue-quote-lint.py 小说.txt --style corner    # 只查「」『』
    python dialogue-quote-lint.py 小说.txt --singles         # 同时查 ‘’ 与 ''

退出码: 0=检查完成（无论是否发现问题）; 1=--strict 且发现问题; 2=参数/文件错误。
"""

import argparse
import sys
from pathlib import Path

PAIRS = [
    ("curly", "“", "”"),
    ("corner", "「", "」"),
    ("corner2", "『", "』"),
    ("straight", '"', '"'),
]
SINGLES = [
    ("curly-single", "‘", "’"),
    ("straight-single", "'", "'"),
]
GROUPS = {
    "all": None,
    "curly": ("curly",),
    "corner": ("corner", "corner2"),
    "straight": ("straight",),
}


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


def select_pairs(style, singles):
    names = GROUPS[style]
    out = []
    for name, o, c in PAIRS:
        if names is None or name in names:
            out.append((name, o, c))
    if singles:
        for name, o, c in SINGLES:
            if style == "all" or name == style + "-single":
                out.append((name, o, c))
    return out


def main(argv=None):
    _reconfig()
    ap = argparse.ArgumentParser(
        prog="dialogue-quote-lint",
        description="检查小说对话引号是否成对、是否与叙述错层混用, 输出待修列表",
    )
    ap.add_argument("input", help="输入 TXT 文件")
    ap.add_argument("-o", "--output", help="待修列表输出文件; 缺省打印到 stdout")
    ap.add_argument("--style", choices=("all", "curly", "corner", "straight"), default="all",
                    help="检查范围: all=全部(默认), curly=“”, corner=「」『』, straight=\"")
    ap.add_argument("--singles", action="store_true", help="同时检查单引号 ‘’ 与 ''")
    ap.add_argument("--strict", action="store_true", help="发现问题则退出码 1")
    ap.add_argument("--encoding", default="auto", help="输入编码, auto=尝试 utf-8/gb18030/big5")
    args = ap.parse_args(argv)

    pairs = select_pairs(args.style, args.singles)
    if not pairs:
        die("没有可检查的引号风格")
    try:
        text = read_text(args.input, args.encoding)
    except OSError as exc:
        die(f"读取输入失败: {exc}")

    lines = text.splitlines()
    counts = {name: [0, 0] for name, _, _ in pairs}  # [开, 闭]
    depth = {name: 0 for name, o, c in pairs if o != c}
    findings = []
    prev_line = ""

    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            for name, o, c in pairs:
                if o != c and depth[name] > 0:
                    findings.append((lineno, "段落末悬挂",
                                     f"{o} 在上一段末仍未闭合(深度 {depth[name]}), 已按段落边界复位",
                                     prev_line))
                    depth[name] = 0
            continue
        hit_open = set()
        has_straight = False
        has_directional = False
        straight_cnt = 0
        for ch in line:
            for name, o, c in pairs:
                if ch == o and o != c:
                    counts[name][0] += 1
                    depth[name] += 1
                    hit_open.add(name)
                    has_directional = True
                elif ch == o and o == c:
                    counts[name][0] += 1
                    straight_cnt += 1
                    if name == "straight":
                        has_straight = True
                elif ch == c and o != c:
                    counts[name][1] += 1
                    depth[name] -= 1
                    has_directional = True
                    if depth[name] < 0:
                        findings.append((lineno, "先闭后开",
                                         f"{c} 出现在 {o} 之前(疑似错层)", line))
                        depth[name] = 0
        for name, o, c in pairs:
            if o != c and depth[name] > 0 and name in hit_open:
                findings.append((lineno, "未闭合",
                                 f"{o} 行末仍有 {depth[name]} 层未闭合(疑似漏写收尾引号)", line))
        if straight_cnt % 2 == 1:
            findings.append((lineno, "直引号奇数",
                             f"半角 \" 出现 {straight_cnt} 次, 无法两两配对", line))
        if has_straight and has_directional:
            findings.append((lineno, "风格混用",
                             "同一行混用半角直引号与弯/角引号, 疑似复制粘贴错层", line))
        prev_line = line

    last = len(lines)
    for name, o, c in pairs:
        if o != c and depth[name] > 0:
            findings.append((last, "文件末悬挂",
                             f"{o} 至文件末尾仍未闭合(深度 {depth[name]})", prev_line))
    for name, o, c in pairs:
        if o == c:
            counts[name][1] = counts[name][0]

    out = [f"==== 对话引号待修列表: {args.input} ===="]
    if findings:
        for lineno, kind, msg, excerpt in findings:
            exc = excerpt.strip()
            if len(exc) > 50:
                exc = exc[:50] + "…"
            out.append(f"行 {lineno} [{kind}] {msg} | {exc}")
    else:
        out.append("未发现引号问题。")
    out.append("==== 汇总 ====")
    parts = []
    for name, o, c in pairs:
        opens, closes = counts[name]
        if opens == 0 and closes == 0:
            continue
        if o == c:
            mark = "(奇数, 需人工核对)" if opens % 2 else ""
            parts.append(f"{o}{o} 共{opens}个{mark}")
        else:
            mark = "(开闭不等!)" if opens != closes else ""
            parts.append(f"{o}{c} 开{opens} 闭{closes}{mark}")
    out.append("引号统计: " + (" | ".join(parts) if parts else "无引号"))
    out.append(f"检查 {len(lines)} 行, 共 {len(findings)} 处疑似问题。")
    report = "\n".join(out) + "\n"

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as fh:
            fh.write(report)
        print(f"待修列表已写入: {args.output}")
    else:
        sys.stdout.write(report)
    return 1 if (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
