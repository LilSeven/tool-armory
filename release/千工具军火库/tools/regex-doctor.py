#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正则隐患体检（regex-doctor）：静态检查正则中的性能与正确性隐患并给出建议。

检查项:
    1. 嵌套量词（如 (a+)+ 、(a*)*）—— 潜在灾难性回溯
    2. 捕获组未使用（仅分组用途却用了捕获组）—— 建议改为 (?:...)
    3. 未转义的元字符（如字符类外的 . + ? * { } 疑似笔误处给出提示）
    4. 无法匹配空输入却写 form (a|) 之类的空分支
    5. 贪婪量词后紧跟 .*/.+ 的整行吞并模式 —— 建议懒惰或收窄字符类
    6. 常见笔误：\\d 后接 {0}、字符类中多余连字符等

用法:
    python -I regex-doctor.py "(a+)+b"
    python -I regex-doctor.py "(\\d+)\\.(\\d+)" --strict

退出码: 0 = 无高危问题；1 = 存在警告；2 = 参数/编译错误。
"""
import argparse
import re
import sys

HIGH = "高危"
WARN = "警告"
INFO = "提示"


def find_nested_quantifier(pattern: str):
    """粗略检测 嵌套量词：形如 X* 或 X+ 或 X{n,} 紧跟量词。"""
    issues = []
    # ( ... +|*  )  紧跟 +|*  简单括号配对
    stack = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "[":
            # 跳过字符类
            j = i + 1
            if j < n and pattern[j] == "^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 2 if pattern[j] == "\\" else 1
            i = j + 1
            continue
        if ch == "(":
            stack.append(i)
        elif ch == ")":
            if stack:
                open_i = stack.pop()
                # 括号后跟量词，括号内也以量词结尾？
                inner = pattern[open_i + 1:i]
                after = pattern[i + 1:i + 4]
                quant_inner = re.search(r"[+*]\??|\{\d+(,\d*)?\}\??$", inner)
                quant_after = re.match(r"[+*]|\{\d+(,\d*)?\}", after)
                if quant_inner and quant_after and not pattern.startswith("(?:", open_i):
                    issues.append((HIGH, i + 1,
                                   "嵌套量词 (%s)%s —— 可能引发灾难性回溯，建议改写或用原子组思路收窄内层" %
                                   (inner, quant_after.group(0))))
        i += 1
    return issues


def find_unused_groups(pattern: str):
    """检测看起来只做分组、不做引用的捕获组（提示性）。"""
    issues = []
    depth_refs = set()
    # 找反向引用 \1..\9
    for m in re.finditer(r"\\(\d)", pattern):
        depth_refs.add(int(m.group(1)))
    count = 0
    stack = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "(":
            if pattern.startswith("(?:", i) or pattern.startswith("(?=", i) \
               or pattern.startswith("(?!", i) or pattern.startswith("(?<", i):
                pass  # 非捕获
            else:
                count += 1
        i += 1
    if count and not depth_refs and count >= 3:
        issues.append((INFO, 0,
                       "共 %d 个捕获组且未见反向引用：若无需提取结果，建议改为 (?:...) 非捕获组以提速" % count))
    return issues


def find_unescaped_metachars(pattern: str):
    """检测容易笔误的未转义元字符（提示级）。"""
    issues = []
    # 量词 {0} / {,5} 这类可疑量词
    for m in re.finditer(r"\{(\d*)\}", pattern):
        body = m.group(1)
        if body == "" or body == "0":
            issues.append((WARN, m.start() + 1,
                           "量词 {%s} —— 重复 0 次等于删除该元素，多半是笔误" % body))
    # 字符类中的裸 ] 或空类 []
    if "[]" in pattern:
        issues.append((WARN, pattern.index("[]") + 1, "空字符类 [] —— 除作为 ] 字面量的特殊写法外多为笔误"))
    # 疑似忘了转义的点号（夹在数字之间像 IP/版本号）
    for m in re.finditer(r"(?<=\d)\.(?=\d)", pattern):
        issues.append((INFO, m.start() + 1,
                       "数字间的裸点号 %r 可匹配任意字符（如 1a2），若是小数点请写 \\." % m.group(0)))
    return issues


def find_greedy_swallow(pattern: str):
    """检测贪婪 .* / .+ 紧跟另一模式的吞并风险。"""
    issues = []
    for m in re.finditer(r"(?<!\\)\.\*(?![?])", pattern):
        rest = pattern[m.end():]
        if rest and not rest.startswith(("$", "|", ")")):
            issues.append((WARN, m.start() + 1,
                           "贪婪 .* 后还有内容 %r —— 回溯代价高，建议用懒惰 .*? 或收窄为 [^x]*" % rest[:8]))
    for m in re.finditer(r"(?<!\\)\.\+(?![?])", pattern):
        rest = pattern[m.end():]
        if rest and not rest.startswith(("$", "|", ")")):
            issues.append((WARN, m.start() + 1,
                           "贪婪 .+ 后还有内容 %r —— 建议懒惰 .+? 或收窄字符类" % rest[:8]))
    return issues


def find_empty_alternation(pattern: str):
    """检测 | 后紧跟 ) 或 | 结尾这类空分支。"""
    issues = []
    for m in re.finditer(r"\|\s*\)", pattern):
        issues.append((INFO, m.start() + 1, "空分支 |) —— 使整体可匹配空串，确认是否有意为之"))
    if pattern.endswith("|"):
        issues.append((INFO, len(pattern), "以 | 结尾 —— 存在空分支，整体可匹配空串"))
    return issues


def check(pattern: str):
    findings = []
    findings += find_nested_quantifier(pattern)
    findings += find_unused_groups(pattern)
    findings += find_unescaped_metachars(pattern)
    findings += find_greedy_swallow(pattern)
    findings += find_empty_alternation(pattern)
    return findings


def main():
    ap = argparse.ArgumentParser(description="静态体检正则的隐患并给建议")
    ap.add_argument("pattern", help="要检查的正则表达式")
    ap.add_argument("--strict", action="store_true", help="有任何提示也返回退出码 1")
    args = ap.parse_args()

    try:
        re.compile(args.pattern)
    except re.error as e:
        print("正则无法编译，先修正语法: %s" % e, file=sys.stderr)
        return 2

    findings = check(args.pattern)
    if not findings:
        print("未发现常见隐患，正则看起来健康。")
        return 0

    rank = {HIGH: 0, WARN: 1, INFO: 2}
    findings.sort(key=lambda f: (rank[f[0]], f[1]))
    for level, pos, msg in findings:
        print("[%s] 位置 %d: %s" % (level, pos, msg))
    worst = findings[0][0]
    print("-" * 40)
    print("共 %d 条发现（高危 %d / 警告 %d / 提示 %d）" % (
        len(findings),
        sum(1 for f in findings if f[0] == HIGH),
        sum(1 for f in findings if f[0] == WARN),
        sum(1 for f in findings if f[0] == INFO)))
    if worst == HIGH or (args.strict and findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
