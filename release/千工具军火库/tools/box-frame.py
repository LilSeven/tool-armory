#!/usr/bin/env python3
"""文本加框 —— 给多行文本画 ASCII/Unicode 边框, 支持圆角与双线等样式。

用途:
    读取一行或多行文本, 按选定样式画出包住它们的边框。
    内置 East Asian 全角宽度计算, 中文等宽字符也能与边框对齐。

样式(--style):
    ascii    +----+
    unicode  ┌────┐   (默认)
    rounded  ╭────╮   (圆角)
    double   ╔════╗   (双线)
    heavy    ┏━━━━┓   (粗线)

示例命令:
    python box-frame.py -s rounded "你好\\nbox frame\\n第二行"
    python box-frame.py --style double --align center -w 30 A B C
    python box-frame.py -s ascii -t 标题 "内容一行"
    printf 'line1\\nline2\\nline3' | python box-frame.py     # 从 stdin 读多行

说明:
    * 多个参数用空格连接; 参数中的字面 \\n 会被当作换行。
    * 无参数且标准输入不是终端时, 从 stdin 读取多行文本。
    * 退出码: 0 = 正常; 2 = 参数错误。
"""

import argparse
import sys
import unicodedata

# 左上, 横线, 右上, 左下, 右下, 竖线
STYLES = {
    "ascii":   ("+", "-", "+", "+", "+", "|"),
    "unicode": ("┌", "─", "┐", "└", "┘", "│"),
    "rounded": ("╭", "─", "╮", "╰", "╯", "│"),
    "double":  ("╔", "═", "╗", "╚", "╝", "║"),
    "heavy":   ("┏", "━", "┓", "┗", "┛", "┃"),
}


def char_width(ch):
    """单个字符的终端显示宽度: 全角(W/F)为 2, 其余为 1。"""
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def display_width(s):
    return sum(char_width(c) for c in s)


def pad_to(s, width, align):
    """按显示宽度补空格, 支持 left/center/right 对齐。"""
    gap = max(0, width - display_width(s))
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def frame(lines, style="unicode", pad=1, align="left", min_width=0, title=None):
    """给多行文本画框, 返回多行字符串。"""
    tl, hz, tr, bl, br, vt = STYLES[style]
    content = max([display_width(l) for l in lines] + [0])
    inner = max(content + pad * 2, min_width, 1)
    # 内容行宽 = vt + pad + (inner - 2*pad) + pad + vt = inner + 2 列
    # 边框行宽 = 角 + inner 条横线 + 角 = inner + 2 列, 两者严格对齐
    if title:
        label = "[ %s ]" % title
        w = display_width(label)
        if w <= inner - 2:
            top = tl + hz + label + hz * (inner - w - 1) + tr
        else:                                   # 标题放不下就退化为普通边框
            top = tl + hz * inner + tr
    else:
        top = tl + hz * inner + tr
    rows = [top]
    for line in lines:
        rows.append(vt + " " * pad + pad_to(line, inner - pad * 2, align) + " " * pad + vt)
    rows.append(bl + hz * inner + br)
    return "\n".join(rows)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        if not sys.stdin.isatty():      # 管道输入按 UTF-8 读, 避免 GBK 误码
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="文本加框: 给多行文本画 ASCII/Unicode 边框")
    ap.add_argument("text", nargs="*", help="文本(多参数用空格连接, 字面 \\n 表示换行)")
    ap.add_argument("-s", "--style", default="unicode", choices=sorted(STYLES),
                    help="边框样式, 默认 unicode")
    ap.add_argument("-p", "--pad", type=int, default=1,
                    help="内容与边框间的水平留白, 默认 1")
    ap.add_argument("-a", "--align", default="left",
                    choices=("left", "center", "right"), help="对齐方式, 默认 left")
    ap.add_argument("-w", "--width", type=int, default=0, help="最小内容区宽度")
    ap.add_argument("-t", "--title", default=None, help="嵌入上边框的标题")
    ns = ap.parse_args(argv)

    if ns.text:
        text = " ".join(ns.text).replace("\\n", "\n")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        text = ""
    if text.endswith("\n"):                     # 抵消管道输入末尾的换行
        text = text[:-1]
    lines = [l.rstrip("\r") for l in text.split("\n")]
    print(frame(lines, ns.style, max(0, ns.pad), ns.align, max(0, ns.width), ns.title))
    return 0


if __name__ == "__main__":
    sys.exit(main())
