#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正则解释器（regex-explainer）：逐 token 解析正则表达式，输出人类可读的中文逐段解释。

用法:
    python -I regex-explainer.py "\\d{2,4}"
    python -I regex-explainer.py "^(\\w+)@([a-z]+\\.[a-z]{2,})$" --flags i

示例输出（输入 \\d{2,4}）:
    \\d{2,4}  ->  2 到 4 位数字

只使用 Python 标准库（re / argparse）。不保证覆盖全部语法，
无法识别的片段会标注 [未识别] 并原样展示。
"""
import argparse
import re
import sys

# 常用转义序列 -> 中文
ESCAPES = {
    r"\d": "数字（0-9）",
    r"\D": "非数字字符",
    r"\w": "单词字符（字母、数字、下划线）",
    r"\W": "非单词字符",
    r"\s": "空白字符（空格、制表符、换行等）",
    r"\S": "非空白字符",
    r"\b": "单词边界",
    r"\B": "非单词边界",
    r"\A": "字符串开头",
    r"\Z": "字符串结尾",
    r"\n": "换行符",
    r"\r": "回车符",
    r"\t": "制表符",
    r"\\": "反斜杠字符 \\",
    r"\.": "点号字符 .",
}

CHAR_CLASS_MEANING = {
    "0-9": "数字",
    "a-z": "小写字母",
    "A-Z": "大写字母",
    "a-zA-Z": "英文字母",
    "A-Za-z": "英文字母",
    "a-zA-Z0-9": "字母或数字",
    "0-9a-f": "十六进制数字",
    "0-9a-fA-F": "十六进制数字",
}


def describe_char_class(body: str) -> str:
    """描述字符类 [...] 的内容。"""
    neg = body.startswith("^")
    inner = body[1:] if neg else body
    parts = []
    for key, meaning in CHAR_CLASS_MEANING.items():
        if key in inner:
            parts.append(meaning)
            inner = inner.replace(key, "")
    # 剩余单字符
    leftovers = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner):
            seq = "\\" + inner[i + 1]
            leftovers.append(ESCAPES.get(seq, seq))
            i += 2
        else:
            leftovers.append("字符 " + repr(ch) if ch not in "]^-" else "字符 " + repr(ch))
            i += 1
    if leftovers:
        parts.extend(leftovers)
    if not parts:
        return "字符类 [...]（内容为空或无法解析）"
    text = " 或 ".join(parts) if len(parts) > 1 else parts[0]
    return ("任意非以下字符：" + text) if neg else ("以下任意字符：" + text)


def explain(pattern: str) -> list:
    """逐段解析正则，返回 [(片段, 解释), ...]。"""
    segments = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]

        # 转义序列
        if ch == "\\" and i + 1 < n:
            seq = pattern[i:i + 2]
            segments.append((seq, ESCAPES.get(seq, "转义字符 " + seq[1])))
            i += 2
            continue

        # 字符类
        if ch == "[":
            j = i + 1
            if j < n and pattern[j] == "^":
                j += 1
            if j < n and pattern[j] == "]":  # 首个 ] 视为字面量
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            body = pattern[i + 1:j]
            segments.append((pattern[i:j + 1], describe_char_class(body)))
            i = j + 1
            continue

        # 分组
        if ch == "(":
            if pattern.startswith("(?=", i):
                segments.append((pattern[i:i + 3], "正向先行断言（后面必须紧跟，但不消耗字符）"))
                i += 3
            elif pattern.startswith("(?!", i):
                segments.append((pattern[i:i + 3], "负向先行断言（后面必须不是，但不消耗字符）"))
                i += 3
            elif pattern.startswith("(?<=", i):
                segments.append((pattern[i:i + 4], "正向后行断言（前面必须是，但不消耗字符）"))
                i += 4
            elif pattern.startswith("(?<!", i):
                segments.append((pattern[i:i + 4], "负向后行断言（前面必须不是，但不消耗字符）"))
                i += 4
            elif pattern.startswith("(?:", i):
                segments.append((pattern[i:i + 3], "非捕获分组（只分组，不保存结果）"))
                i += 3
            elif pattern.startswith("(?P<", i):
                end = pattern.find(">", i)
                name = pattern[i + 4:end] if end != -1 else "?"
                segments.append((pattern[i:end + 1] if end != -1 else "(?P<",
                                 "命名捕获组，名字为 %r" % name))
                i = (end + 1) if end != -1 else n
            else:
                idx = len([s for s, _ in segments if "捕获组" in _]) + 1
                segments.append((ch, "捕获组（保存匹配结果，可用 \\%d 或 group(%d) 引用）" % (idx, idx)))
                i += 1
            continue

        # 量词
        if ch == "*":
            segments.append((ch, "前一个元素重复 0 次或多次（贪婪，尽可能多）"))
            i += 1
        elif ch == "+":
            segments.append((ch, "前一个元素重复 1 次或多次（贪婪）"))
            i += 1
        elif ch == "?":
            segments.append((ch, "前一个元素出现 0 次或 1 次（可选）"))
            i += 1
        elif ch == "{":
            j = pattern.find("}", i)
            if j == -1:
                segments.append((ch, "字面量字符 {"))
                i += 1
                continue
            body = pattern[i + 1:j]
            m = re.match(r"^(\d+)(,(\d+)?)?$", body)
            if not m:
                segments.append((pattern[i:j + 1], "字面量片段 %r" % pattern[i:j + 1]))
            elif m.group(2) is None:
                segments.append((pattern[i:j + 1], "前一个元素精确重复 %s 次" % m.group(1)))
            elif m.group(3) is None:
                segments.append((pattern[i:j + 1], "前一个元素重复 %s 次或更多" % m.group(1)))
            else:
                segments.append((pattern[i:j + 1], "前一个元素重复 %s 到 %s 次" % (m.group(1), m.group(3))))
            i = j + 1
        elif ch in "}?+*" and pattern[i:i + 1] == "?" :
            i += 1
        # 懒惰/占有后缀
        elif ch in "*+?" and False:
            pass
        else:
            meaning = {
                ".": "任意单个字符（默认不匹配换行）",
                "^": "行/字符串开头",
                "$": "行/字符串结尾",
                "|": "或（左右两边任选其一）",
                ")": "分组结束",
            }.get(ch)
            if meaning:
                segments.append((ch, meaning))
            else:
                segments.append((ch, "字面量字符 %r" % ch))
            i += 1

    # 二次遍历：为懒惰后缀 ? 附加说明
    out = []
    for idx, (frag, desc) in enumerate(segments):
        if frag == "?" and idx > 0 and ("重复" in out[-1][1] or "贪婪" in out[-1][1] or "可选" in out[-1][1]):
            out[-1] = (out[-1][0] + frag, out[-1][1] + "；后随 ? 表示懒惰匹配（尽可能少）")
        else:
            out.append((frag, desc))
    return out


def main():
    ap = argparse.ArgumentParser(description="逐 token 解释正则表达式（中文）")
    ap.add_argument("pattern", help="要解释的正则表达式")
    ap.add_argument("--flags", default="", help="标志，如 i/m/s（用于展示合法编译验证）")
    args = ap.parse_args()

    flag_map = {"i": re.I, "m": re.M, "s": re.S, "x": re.X, "a": re.A}
    flags = 0
    for c in args.flags:
        if c in flag_map:
            flags |= flag_map[c]
        else:
            print("未知标志: %r" % c, file=sys.stderr)
            return 2
    try:
        re.compile(args.pattern, flags)
        status = "（已验证：该正则可被 Python re 编译）"
    except re.error as e:
        status = "（警告：无法编译：%s）" % e

    print("正则: %s" % args.pattern)
    print("逐段解释:")
    for frag, desc in explain(args.pattern):
        print("  %-14s ->  %s" % (repr(frag), desc))
    print(status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
