#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YAML 转 JSON（子集）：内置迷你 YAML 解析器，报错时给出确切行号。

支持的 YAML 子集:
    * 缩进式映射        key: value
    * 块列表            - item，支持 "- key: value" 及任意嵌套
    * 行内流程式        [a, b] 与 {k: v}
    * 标量              null / ~ / 空、true / false、整数、浮点（含 1e3）、
                        .nan / .inf、单引号与双引号字符串
    * 注释              行首或空白后的 # 到行尾被忽略（引号内除外）
不支持: Tab 缩进、多行块标量 (| >)、锚点/引用 (& *)、标签 (!)、多文档 (---)；
遇到不支持的语法会报错并给出确切行号。重复键也报错。

用法:
    python yaml2json-lite.py data.yaml
    python yaml2json-lite.py data.yaml -o out.json
    cat data.yaml | python yaml2json-lite.py -
    python yaml2json-lite.py data.yaml --compact
"""

import argparse
import json
import re
import sys

INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")


class YAMLError(Exception):
    """带行号的 YAML 解析错误。"""


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


# ---------- 词法辅助 ----------

def strip_comment(line):
    """去掉行注释：未被引号包裹、且位于行首或空白之后的 # 起到行尾。"""
    out = []
    quote = None
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if quote == "'":
            out.append(c)
            if c == "'":
                if i + 1 < n and line[i + 1] == "'":  # '' 是转义的引号
                    out.append("'")
                    i += 2
                    continue
                quote = None
            i += 1
        elif quote == '"':
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(line[i + 1])
                i += 2
                continue
            if c == '"':
                quote = None
            i += 1
        else:
            if c in "\"'":
                quote = c
                out.append(c)
                i += 1
            elif c == "#" and (i == 0 or line[i - 1] in " \t"):
                break
            else:
                out.append(c)
                i += 1
    return "".join(out).rstrip()


def convert_scalar(text):
    t = text.strip()
    if t in ("", "null", "Null", "NULL", "~"):
        return None
    if t in ("true", "True", "TRUE"):
        return True
    if t in ("false", "False", "FALSE"):
        return False
    if t == ".nan":
        return float("nan")
    if t in (".inf", "+.inf"):
        return float("inf")
    if t == "-.inf":
        return float("-inf")
    if INT_RE.match(t):
        return int(t)
    if FLOAT_RE.match(t):
        return float(t)
    return t


def parse_quoted(s, lineno):
    """s 以引号开头；返回 (字符串, 剩余文本)。"""
    quote = s[0]
    i = 1
    n = len(s)
    buf = []
    if quote == "'":
        while i < n:
            c = s[i]
            if c == "'":
                if i + 1 < n and s[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                return "".join(buf), s[i + 1:]
            buf.append(c)
            i += 1
        raise YAMLError("行 %d: 单引号字符串未闭合" % lineno)
    escapes = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "a": "\a",
               "b": "\b", "f": "\f", "v": "\v", "e": "\x1b",
               '"': '"', "\\": "\\", "/": "/", " ": " "}
    while i < n:
        c = s[i]
        if c == "\\":
            if i + 1 >= n:
                raise YAMLError("行 %d: 转义符 \\ 后缺少字符" % lineno)
            esc = s[i + 1]
            if esc == "u":
                if i + 6 > n:
                    raise YAMLError("行 %d: \\u 转义不完整" % lineno)
                try:
                    buf.append(chr(int(s[i + 2:i + 6], 16)))
                except ValueError:
                    raise YAMLError("行 %d: 非法的 \\u 转义 %r" % (lineno, s[i:i + 6]))
                i += 6
                continue
            if esc == "x":
                if i + 4 > n:
                    raise YAMLError("行 %d: \\x 转义不完整" % lineno)
                try:
                    buf.append(chr(int(s[i + 2:i + 4], 16)))
                except ValueError:
                    raise YAMLError("行 %d: 非法的 \\x 转义 %r" % (lineno, s[i:i + 4]))
                i += 4
                continue
            buf.append(escapes.get(esc, esc))
            i += 2
            continue
        if c == '"':
            return "".join(buf), s[i + 1:]
        buf.append(c)
        i += 1
    raise YAMLError("行 %d: 双引号字符串未闭合" % lineno)


def parse_flow(s, lineno):
    """解析整段行内流程式值（以 [ 或 { 开头），要求整段消费完。"""
    pos = 0
    n = len(s)

    def skip_ws():
        nonlocal pos
        while pos < n and s[pos] in " \t":
            pos += 1

    def token(stop):
        nonlocal pos
        skip_ws()
        if pos < n and s[pos] in "\"'":
            val, rest = parse_quoted(s[pos:], lineno)
            pos = n - len(rest)
            return val
        start = pos
        while pos < n and s[pos] not in stop:
            pos += 1
        return convert_scalar(s[start:pos])

    def value():
        nonlocal pos
        skip_ws()
        if pos >= n:
            raise YAMLError("行 %d: 流程式值意外结束" % lineno)
        c = s[pos]
        if c == "[":
            pos += 1
            arr = []
            skip_ws()
            if pos < n and s[pos] == "]":
                pos += 1
                return arr
            while True:
                arr.append(value())
                skip_ws()
                if pos >= n:
                    raise YAMLError("行 %d: 流程式数组缺少 ']'" % lineno)
                if s[pos] == ",":
                    pos += 1
                    continue
                if s[pos] == "]":
                    pos += 1
                    return arr
                raise YAMLError("行 %d: 流程式数组中应有 ',' 或 ']'" % lineno)
        if c == "{":
            pos += 1
            obj = {}
            skip_ws()
            if pos < n and s[pos] == "}":
                pos += 1
                return obj
            while True:
                key = token(":")
                skip_ws()
                if pos >= n or s[pos] != ":":
                    raise YAMLError("行 %d: 流程式映射的键后应有 ':'" % lineno)
                pos += 1
                obj[key] = value()
                skip_ws()
                if pos >= n:
                    raise YAMLError("行 %d: 流程式映射缺少 '}'" % lineno)
                if s[pos] == ",":
                    pos += 1
                    continue
                if s[pos] == "}":
                    pos += 1
                    return obj
                raise YAMLError("行 %d: 流程式映射中应有 ',' 或 '}'" % lineno)
        return token(",]}")

    v = value()
    skip_ws()
    if pos != n:
        raise YAMLError("行 %d: 流程式值后有多余内容 %r" % (lineno, s[pos:]))
    return v


# ---------- 块解析 ----------

def split_key(body, lineno):
    """找 'key:' 的分隔点：引号外的 ':'，其后是空格或行尾。返回 (键, 值文本)。"""
    quote = None
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if quote:
            if quote == '"' and c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'":
            quote = c
            i += 1
            continue
        if c == ":" and (i + 1 == n or body[i + 1] in " \t"):
            raw = body[:i].strip()
            if not raw:
                raise YAMLError("行 %d: 缺少键名" % lineno)
            if raw[0] in "\"'":
                key, rest = parse_quoted(raw, lineno)
                if rest.strip():
                    raise YAMLError("行 %d: 键名引号后有多余内容 %r"
                                    % (lineno, rest.strip()))
                return key, body[i + 1:]
            return raw, body[i + 1:]
        i += 1
    raise YAMLError("行 %d: 缺少 ':'（应为 'key: value' 形式）" % lineno)


def parse_inline(rest, lineno):
    """解析 'key:' 之后的行内值（标量 / 引号串 / 流程式）。"""
    c = rest[0]
    if c in "[{":
        return parse_flow(rest, lineno)
    if c in "\"'":
        value, tail = parse_quoted(rest, lineno)
        if tail.strip():
            raise YAMLError("行 %d: 标量后有多余内容 %r" % (lineno, tail.strip()))
        return value
    if c in "|>&*!%":
        raise YAMLError("行 %d: 不支持的 YAML 语法 %r（本工具只支持映射/列表/标量子集）"
                        % (lineno, rest))
    return convert_scalar(rest)


def _item_kind(rest, lineno):
    """判定 '- ' 之后的行内内容是 嵌套列表(seq) / 映射(map) / 标量(inline)。"""
    if rest == "-" or rest.startswith("- "):
        return "seq"
    if rest[0] in "[{":  # 行内流程式
        return "inline"
    try:
        split_key(rest, lineno)
    except YAMLError:
        return "inline"  # 纯标量 / 引号字符串
    return "map"


def parse_node(logical, i):
    """解析从 logical[i] 开始的块，返回 (值, 下一索引)。"""
    _, body, indent = logical[i]
    if body == "-" or body.startswith("- "):
        return parse_sequence(logical, i, indent)
    return parse_mapping(logical, i, indent)


def parse_sequence(logical, i, indent):
    items = []
    n = len(logical)
    while i < n:
        lineno, body, ind = logical[i]
        if ind < indent:
            break
        if ind > indent:
            raise YAMLError("行 %d: 意外的缩进" % lineno)
        if body != "-" and not body.startswith("- "):
            break  # 序列到此结束；多余内容由调用方/顶层处理
        rest = "" if body == "-" else body[2:].strip()
        if not rest:
            if i + 1 < n and logical[i + 1][2] > indent:
                value, i = parse_node(logical, i + 1)
            else:
                value = None
                i += 1
        else:
            kind = _item_kind(rest, lineno)
            if kind == "inline":
                value = parse_inline(rest, lineno)
                i += 1
            else:
                # 把 "- xxx" 换成缩进 +2 的虚拟行，再按嵌套列表/映射解析
                logical[i] = (lineno, rest, indent + 2)
                value, i = parse_node(logical, i)
        items.append(value)
    return items, i


def parse_mapping(logical, i, indent):
    result = {}
    n = len(logical)
    while i < n:
        lineno, body, ind = logical[i]
        if ind < indent:
            break
        if ind > indent:
            raise YAMLError("行 %d: 意外的缩进" % lineno)
        if body == "-" or body.startswith("- "):
            raise YAMLError("行 %d: 映射中混入列表项 '-'" % lineno)
        key, rest = split_key(body, lineno)
        rest = rest.strip()
        if not rest:
            if i + 1 < n:
                _, nbody, nind = logical[i + 1]
                if nind > indent:
                    value, i = parse_node(logical, i + 1)
                elif nind == indent and (nbody == "-" or nbody.startswith("- ")):
                    # YAML 允许列表项与所属键同缩进
                    value, i = parse_sequence(logical, i + 1, indent)
                else:
                    value = None
                    i += 1
            else:
                value = None
                i += 1
        else:
            value = parse_inline(rest, lineno)
            i += 1
        if key in result:
            raise YAMLError("行 %d: 重复的键 %r" % (lineno, key))
        result[key] = value
    return result, i


def parse_lines(text):
    logical = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = strip_comment(raw)
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped in ("---", "..."):
            if logical:
                raise YAMLError("行 %d: 不支持多文档（遇到 %r）" % (lineno, stripped))
            continue
        ws_end = len(line) - len(line.lstrip(" \t"))
        if "\t" in line[:ws_end]:
            raise YAMLError("行 %d: 缩进中不能使用制表符 (Tab)" % lineno)
        indent = len(line) - len(line.lstrip(" "))
        logical.append((lineno, stripped, indent))
    return logical


def parse(text):
    logical = parse_lines(text)
    if not logical:
        return None
    lineno, body, _ = logical[0]
    if len(logical) == 1 and not (body == "-" or body.startswith("- ")):
        try:
            split_key(body, lineno)
        except YAMLError:
            return parse_inline(body, lineno)  # 单行纯标量文档
    value, i = parse_node(logical, 0)
    if i != len(logical):
        eline, ebody, _ = logical[i]
        raise YAMLError("行 %d: 存在无法解析的多余内容 %r" % (eline, ebody))
    return value


def main(argv=None):
    _setup_streams()

    parser = argparse.ArgumentParser(
        prog="yaml2json-lite",
        description="用内置迷你解析器把 YAML 子集转成 JSON，报错带确切行号。")
    parser.add_argument("input", nargs="?", default="-",
                        help="输入 YAML 路径，'-' 或省略表示 stdin")
    parser.add_argument("-o", "--output", help="输出 JSON 路径（默认 stdout）")
    parser.add_argument("--compact", action="store_true", help="单行输出 JSON")
    args = parser.parse_args(argv)

    try:
        if args.input == "-":
            text = sys.stdin.read()
        else:
            with open(args.input, "r", encoding="utf-8-sig") as f:
                text = f.read()
    except OSError as e:
        print("错误: 无法读取 %s: %s" % (args.input, e), file=sys.stderr)
        return 1
    if text.startswith("\ufeff"):
        text = text[1:]

    try:
        data = parse(text)
    except YAMLError as e:
        print("yaml2json-lite: %s" % e, file=sys.stderr)
        return 1

    text_out = json.dumps(data, ensure_ascii=False,
                          indent=None if args.compact else 2)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8", newline="\n") as f:
                f.write(text_out + "\n")
        except OSError as e:
            print("错误: 无法写入 %s: %s" % (args.output, e), file=sys.stderr)
            return 1
    else:
        print(text_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
