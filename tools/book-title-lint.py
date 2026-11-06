#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""书名号规范检查(book-title-lint)

检查书名号《》与篇名号〈〉的使用是否符合层级规范(GB/T 15834)：
  · 书名号内再嵌套书名应使用篇名号〈〉 —— 《内嵌《 记为违规
  · 篇名号〈〉不能独立用于最外层       —— 〈…〉独立出现 记为违规
  · 《》〈〉交叉、孤立或未闭合记为结构错误
  · 书名号内直接用双引号给提示：嵌套篇名通常应使用〈〉
  · 双引号内疑似书名(如“红楼梦”)给提示：通常应使用书名号《》
逐条输出 行:列 级别 与说明。默认退出码恒为 0；
--fail-on-issue 时发现问题的退出码为 1，--no-suggest 关闭两类提示。

用法:
  python -I book-title-lint.py [输入文件] [--fail-on-issue] [--no-suggest]

示例命令:
  printf '这本《《论语》心得》很有意思' | python -I book-title-lint.py
  printf '〈荷塘月色〉是名篇' | python -I book-title-lint.py
  python -I book-title-lint.py input.txt --fail-on-issue
不指定输入文件时读取 stdin。
"""
import argparse
import sys

for _s in (sys.stdout, sys.stderr, sys.stdin):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", newline="")

BT_OPEN, BT_CLOSE = "《", "》"
PT_OPEN, PT_CLOSE = "〈", "〉"
# 疑似书名的结尾字(启发式，仅用于“提示”级)
TITLE_SUFFIX = set("记传志录论书经史集典报刊谱说篇章卷歌剧赋词曲铭乘汇编选")


def line_col(text, pos):
    line = text.count("\n", 0, pos) + 1
    col = pos - (text.rfind("\n", 0, pos) + 1) + 1
    return line, col


def analyze(text, suggest=True):
    findings = []  # (级别, pos, 说明)
    stack = []     # ("bt"|"pt", pos)
    d_in = False
    d_open_pos = None
    for i, ch in enumerate(text):
        if ch == BT_OPEN:
            if stack and stack[-1][0] == "bt":
                findings.append(
                    ("违规", i, "书名号《内又用《，嵌套书名应使用篇名号〈〉"))
            stack.append(("bt", i))
        elif ch == PT_OPEN:
            if not stack:
                findings.append(
                    ("违规", i, "篇名号〈〉独立于书名号使用，外层应改为《》"))
            elif stack[-1][0] == "pt":
                findings.append(("违规", i, "篇名号〈内再用〈，层级过深"))
            stack.append(("pt", i))
        elif ch == BT_CLOSE:
            if not stack:
                findings.append(("结构错误", i, "孤立的闭书名号》"))
            elif stack[-1][0] != "bt":
                findings.append(
                    ("结构错误", i, "》与最近的开篇名号〈类型不匹配(交叉嵌套)"))
                stack.pop()
            else:
                stack.pop()
        elif ch == PT_CLOSE:
            if not stack:
                findings.append(("结构错误", i, "孤立的闭篇名号〉"))
            elif stack[-1][0] != "pt":
                findings.append(
                    ("结构错误", i, "〉与最近的开书名号《类型不匹配(交叉嵌套)"))
                stack.pop()
            else:
                stack.pop()
        elif ch == "“":
            if stack and suggest:
                findings.append(
                    ("提示", i, "书名号内使用双引号，嵌套篇名通常应使用〈〉"))
            if not d_in:
                d_in = True
                d_open_pos = i
        elif ch == "”":
            if d_in:
                d_in = False
                if suggest and d_open_pos is not None:
                    content = text[d_open_pos + 1:i]
                    if (2 <= len(content) <= 30
                            and "《" not in content and "》" not in content
                            and content[-1] in TITLE_SUFFIX):
                        findings.append(
                            ("提示", d_open_pos,
                             "“{}”疑似书名，通常应使用书名号《》".format(content)))
                d_open_pos = None
    for _kind, pos in stack:
        findings.append(("结构错误", pos, "书名号/篇名号未闭合"))
    findings.sort(key=lambda f: f[1])
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="检查书名号《》与篇名号〈〉的层级使用是否正确")
    ap.add_argument("input", nargs="?", help="输入文件(缺省读 stdin)")
    ap.add_argument("--fail-on-issue", action="store_true",
                    help="发现问题时退出码为 1")
    ap.add_argument("--no-suggest", action="store_true",
                    help="关闭“疑似书名”等启发式提示")
    args = ap.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    findings = analyze(text, suggest=not args.no_suggest)
    if not findings:
        sys.stdout.write("未发现问题：书名号使用符合规范\n")
        return 0

    for level, pos, msg in findings:
        ln, col = line_col(text, pos)
        sys.stdout.write("[{}] 行{} 列{}: {}\n".format(level, ln, col, msg))
    n_violation = sum(1 for f in findings if f[0] == "违规")
    n_struct = sum(1 for f in findings if f[0] == "结构错误")
    n_hint = len(findings) - n_violation - n_struct
    sys.stdout.write("共 {} 条问题 (违规 {} / 结构错误 {} / 提示 {})\n".format(
        len(findings), n_violation, n_struct, n_hint))
    return 1 if args.fail_on_issue else 0


if __name__ == "__main__":
    sys.exit(main())
