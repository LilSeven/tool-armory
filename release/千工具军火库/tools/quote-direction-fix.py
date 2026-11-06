#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引号方向修复(quote-direction-fix)

按配对栈修复方向颠倒或未闭合的中文弯引号：
  · 孤立的闭引号(如句首的 ”)：方向颠倒 -> 改为开引号 “
  · 扫描结束后仍未闭合的开引号(如结尾的 “)：按配对 -> 改为闭引号 ”
  · 修复后仍无法配对的引号保持原样，作为问题逐处报告
逐处输出 行:列、原字符 -> 新字符 与原因；--check 只报告不改写。
单引号 ‘’ 中前后都是 ASCII 字母的 ’ 视为英文撇号(it's)跳过；
--double-only 可只处理双引号。

用法:
  python -I quote-direction-fix.py [输入文件] [-o 输出文件]
      [--double-only] [--check] [--fail-on-issue]

示例命令:
  printf '”他说：“你好“' | python -I quote-direction-fix.py
  python -I quote-direction-fix.py input.txt -o fixed.txt
  python -I quote-direction-fix.py input.txt --check --fail-on-issue
不指定输入文件时读取 stdin；不指定 -o 时结果写到 stdout。
"""
import argparse
import sys

for _s in (sys.stdout, sys.stderr, sys.stdin):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", newline="")

DOUBLE = ("“", "”")
SINGLE = ("‘", "’")


def line_col(text, pos):
    line = text.count("\n", 0, pos) + 1
    col = pos - (text.rfind("\n", 0, pos) + 1) + 1
    return line, col


def fix_class(text, open_ch, close_ch, is_single):
    """按配对栈修复一类弯引号的方向。

    返回 (新文本, fixes, issues, skipped_apostrophes)；
    fixes/issues 元素为 (pos, 说明)。
    """
    fixes = []   # (pos, old, new, reason)
    issues = []  # (pos, message)
    skipped = 0
    stack = []
    flips = {}          # pos -> 新字符
    stray_fixed = set() # 曾由孤立闭引号翻转来的位置
    n = len(text)

    for i, ch in enumerate(text):
        if ch != open_ch and ch != close_ch:
            continue
        if is_single and ch == close_ch and 0 < i < n - 1:
            prev, nxt = text[i - 1], text[i + 1]
            if prev.isascii() and prev.isalpha() \
                    and nxt.isascii() and nxt.isalpha():
                skipped += 1  # 英文撇号(it's)，跳过
                continue
        if ch == open_ch:
            stack.append(i)
        else:  # 闭引号
            if stack:
                stack.pop()
            else:
                # 孤立的闭引号 -> 翻转为开引号
                flips[i] = open_ch
                stray_fixed.add(i)
                fixes.append((i, ch, open_ch,
                              "孤立的闭引号，方向颠倒，改为开引号"))
                stack.append(i)

    if stack:
        top = stack[-1]
        if top in stray_fixed:
            # 翻回去净效果为零 -> 降级为问题，保持原样
            flips.pop(top, None)
            fixes = [f for f in fixes if f[0] != top]
            issues.append((top, "孤立的闭引号，前后无法配对，保持原样"))
            stack.pop()
        else:
            if text[top] != close_ch:
                flips[top] = close_ch
                fixes.append((top, text[top], close_ch,
                              "结尾未闭合的开引号，按配对改为闭引号"))
            stack.pop()
            if stack:
                stack.pop()  # 新闭引号与次一个开引号配对
        for p in stack:
            issues.append((p, "开引号{}未闭合".format(flips.get(p, text[p]))))

    if flips:
        buf = list(text)
        for p, c in flips.items():
            buf[p] = c
        text2 = "".join(buf)
    else:
        text2 = text
    return text2, fixes, issues, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="按配对栈修复方向颠倒或未闭合的弯引号")
    ap.add_argument("input", nargs="?", help="输入文件(缺省读 stdin)")
    ap.add_argument("-o", "--output", help="输出文件(缺省写 stdout)")
    ap.add_argument("--double-only", action="store_true",
                    help="只处理双引号“”，跳过单引号‘’")
    ap.add_argument("--check", action="store_true",
                    help="只报告修复建议，不改写文本")
    ap.add_argument("--fail-on-issue", action="store_true",
                    help="发现需修复/问题时退出码为 1")
    args = ap.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    classes = [DOUBLE + (False,)]
    if not args.double_only:
        classes.append(SINGLE + (True,))

    fixed = text
    all_fixes = []
    all_issues = []
    skipped = 0
    for open_ch, close_ch, is_single in classes:
        fixed, fx, isu, sk = fix_class(fixed, open_ch, close_ch, is_single)
        all_fixes.extend(fx)
        all_issues.extend(isu)
        skipped += sk

    all_fixes.sort(key=lambda f: f[0])
    all_issues.sort(key=lambda f: f[0])

    if all_fixes:
        if args.check:
            sys.stdout.write("建议修复 {} 处:\n".format(len(all_fixes)))
        else:
            sys.stdout.write("修复 {} 处:\n".format(len(all_fixes)))
        for pos, old, new, reason in all_fixes:
            ln, col = line_col(text, pos)
            sys.stdout.write("  行{} 列{}: {} -> {}  ({})\n".format(
                ln, col, old, new, reason))
    else:
        sys.stdout.write("未发现需要修复的引号方向问题\n")
    if all_issues:
        sys.stdout.write("问题 {} 处:\n".format(len(all_issues)))
        for pos, msg in all_issues:
            ln, col = line_col(text, pos)
            sys.stdout.write("  行{} 列{}: {}\n".format(ln, col, msg))
    if skipped:
        sys.stdout.write("跳过英文撇号 {} 处\n".format(skipped))

    if not args.check:
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                f.write(fixed)
        else:
            sys.stdout.write(fixed)

    if args.fail_on_issue and (all_fixes or all_issues):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
