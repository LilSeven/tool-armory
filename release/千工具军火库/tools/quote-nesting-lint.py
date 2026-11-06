#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引号嵌套规范检查(quote-nesting-lint)

检查中文引号嵌套是否符合“外双内单”规范(GB/T 15834)：
  · 双引号 “” 内再引用应使用单引号 ‘’ —— “内嵌“ 记为违规
  · 单引号 ‘’ 内再引用应使用双引号     —— ‘内嵌‘ 记为违规
  · 直角引号同理：「」内应用『』       —— 「内嵌「、『内嵌『 记为违规
  · 交叉、孤立、未闭合的引号记为结构错误
逐条输出 行:列 级别 与说明。默认退出码恒为 0；
--fail-on-issue 时发现问题的退出码为 1。

用法:
  python -I quote-nesting-lint.py [输入文件] [--fail-on-issue]

示例命令:
  printf '他说：“内有‘单引’合规”' | python -I quote-nesting-lint.py
  printf '他说：“内有“双引”违规”' | python -I quote-nesting-lint.py
  python -I quote-nesting-lint.py input.txt --fail-on-issue
不指定输入文件时读取 stdin。
"""
import argparse
import sys

for _s in (sys.stdout, sys.stderr, sys.stdin):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", newline="")

OPEN = {"“": "dq", "‘": "sq", "「": "kq", "『": "ks"}
CLOSE = {"”": "dq", "’": "sq", "」": "kq", "』": "ks"}
OPEN_CHAR = {"dq": "“", "sq": "‘", "kq": "「", "ks": "『"}
NAME = {"dq": "双引号“”", "sq": "单引号‘’",
        "kq": "直角引号「」", "ks": "直角引号『』"}
SAME_NEST_MSG = {
    "dq": "双引号“内嵌套双引号，内层应改用单引号‘’",
    "sq": "单引号‘内嵌套单引号，内层应改用双引号“",
    "kq": "直角引号「内嵌套「，内层应改用『』",
    "ks": "直角引号『内嵌套『，超出规范层级",
}


def line_col(text, pos):
    line = text.count("\n", 0, pos) + 1
    col = pos - (text.rfind("\n", 0, pos) + 1) + 1
    return line, col


def analyze(text):
    findings = []  # (级别, pos, 说明)
    stack = []     # (kind, pos)
    for i, ch in enumerate(text):
        if ch in OPEN:
            kind = OPEN[ch]
            if stack and stack[-1][0] == kind:
                findings.append(("违规", i, SAME_NEST_MSG[kind]))
            stack.append((kind, i))
        elif ch in CLOSE:
            kind = CLOSE[ch]
            if not stack:
                findings.append(("结构错误", i, "孤立的闭引号" + ch))
            elif stack[-1][0] != kind:
                findings.append((
                    "结构错误", i,
                    "闭引号{}与最近的开引号{}类型不匹配(交叉嵌套)".format(
                        ch, OPEN_CHAR[stack[-1][0]])))
                stack.pop()  # 弹出以继续扫描
            else:
                stack.pop()
    for kind, pos in stack:
        findings.append(("结构错误", pos,
                         "开引号{}未闭合".format(OPEN_CHAR[kind])))
    findings.sort(key=lambda f: f[1])
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="检查中文引号嵌套是否符合外双内单规范")
    ap.add_argument("input", nargs="?", help="输入文件(缺省读 stdin)")
    ap.add_argument("--fail-on-issue", action="store_true",
                    help="发现问题时退出码为 1")
    args = ap.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    findings = analyze(text)
    if not findings:
        sys.stdout.write("未发现问题：引号嵌套符合外双内单规范\n")
        return 0

    for level, pos, msg in findings:
        ln, col = line_col(text, pos)
        sys.stdout.write("[{}] 行{} 列{}: {}\n".format(level, ln, col, msg))
    n_violation = sum(1 for f in findings if f[0] == "违规")
    n_struct = len(findings) - n_violation
    sys.stdout.write("共 {} 条问题 (违规 {} / 结构错误 {})\n".format(
        len(findings), n_violation, n_struct))
    return 1 if args.fail_on_issue else 0


if __name__ == "__main__":
    sys.exit(main())
