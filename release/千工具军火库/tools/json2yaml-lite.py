#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON 转 YAML（子集）：纯标准库手写的序列化器。

输出支持的 YAML 子集:
    * 缩进式映射        key: value（嵌套默认缩进 2 格，--indent 可调 1~8）
    * 块列表            - item（容器项内容与 "- " 后对齐）
    * 标量              null / true / false / 整数 / 浮点 / .nan / .inf / 字符串
    * 空容器            {} 与 []
    * 有歧义的字符串自动加双引号（转义规则与 JSON 兼容）
不支持锚点、标签、| > 多行块标量等高级特性。

用法:
    python json2yaml-lite.py data.json
    python json2yaml-lite.py data.json -o out.yaml
    cat data.json | python json2yaml-lite.py -
    python json2yaml-lite.py data.json --indent 4
"""

import argparse
import json
import math
import re
import sys

INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
# 这些词不加引号会被读成 null/布尔/特殊浮点，统一加引号
RESERVED = {"null", "~", "true", "false", "yes", "no", "on", "off",
            ".nan", ".inf", "-.inf", "+.inf"}


def _setup_streams():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")
        except Exception:
            pass
    try:
        if sys.stdin is not None:
            sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass


def needs_quote(s):
    """判断字符串裸写是否会被误读，是则加双引号。"""
    if s == "" or s != s.strip():
        return True
    if any(ord(c) < 32 for c in s):
        return True
    if s.lower() in RESERVED:
        return True
    if INT_RE.match(s) or FLOAT_RE.match(s):
        return True
    if s[0] in "-?:,[]{}#&*!|>'\"%@`":
        return True
    if ": " in s or s.endswith(":") or " #" in s:
        return True
    return False


def scalar_text(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v):
            return ".nan"
        if math.isinf(v):
            return ".inf" if v > 0 else "-.inf"
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False) if needs_quote(v) else v
    raise TypeError("不支持的标量类型: %r" % (v,))


def emit(value, indent, unit, out):
    """把值写入 out（每项一行），indent 为当前层缩进格数。"""
    pad = " " * indent
    if isinstance(value, dict):
        if not value:
            out.append(pad + "{}")
            return
        for key, item in value.items():
            k = key if isinstance(key, str) else str(key)
            key_text = json.dumps(k, ensure_ascii=False) if needs_quote(k) else k
            if isinstance(item, dict) and item:
                out.append("%s%s:" % (pad, key_text))
                emit(item, indent + unit, unit, out)
            elif isinstance(item, list) and item:
                out.append("%s%s:" % (pad, key_text))
                emit(item, indent + unit, unit, out)
            elif isinstance(item, dict):
                out.append("%s%s: {}" % (pad, key_text))
            elif isinstance(item, list):
                out.append("%s%s: []" % (pad, key_text))
            else:
                out.append("%s%s: %s" % (pad, key_text, scalar_text(item)))
        return
    if isinstance(value, list):
        if not value:
            out.append(pad + "[]")
            return
        for item in value:
            if isinstance(item, (dict, list)) and item:
                sub = []
                # 容器项内容固定缩进 2 格，与 "- " 前缀对齐
                emit(item, indent + 2, unit, sub)
                out.append(pad + "- " + sub[0][indent + 2:])
                out.extend(sub[1:])
            elif isinstance(item, dict):
                out.append(pad + "- {}")
            elif isinstance(item, list):
                out.append(pad + "- []")
            else:
                out.append("%s- %s" % (pad, scalar_text(item)))
        return
    out.append(pad + scalar_text(value))


def read_text(path):
    if path == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except OSError as e:
            raise SystemExit("错误: 无法读取 %s: %s" % (path, e))
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


def main(argv=None):
    _setup_streams()

    parser = argparse.ArgumentParser(
        prog="json2yaml-lite",
        description="JSON → YAML 子集（手写序列化器，只用标准库）。")
    parser.add_argument("input", nargs="?", default="-",
                        help="输入 JSON 路径，'-' 或省略表示 stdin")
    parser.add_argument("-o", "--output", help="输出 YAML 路径（默认 stdout）")
    parser.add_argument("--indent", type=int, default=2,
                        help="嵌套缩进格数，默认 2，范围 1~8")
    args = parser.parse_args(argv)

    if not 1 <= args.indent <= 8:
        raise SystemExit("错误: --indent 应在 1~8 之间，收到 %d" % args.indent)

    try:
        data = json.loads(read_text(args.input))
    except ValueError as e:
        raise SystemExit("错误: JSON 解析失败: %s" % e)

    lines = []
    emit(data, 0, args.indent, lines)
    text = "\n".join(lines) + "\n"

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        except OSError as e:
            raise SystemExit("错误: 无法写入 %s: %s" % (args.output, e))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
