#!/usr/bin/env python3
"""点路径 JSON 查询：用 a.b.0.c 风格路径与简易过滤条件从 JSON 中取值或切片输出。

路径段：对象键用名字，数组元素用数字下标；支持负数下标。
切片：用 a[1:3] 形式（可只写一侧）。
过滤：--where "k=v" 匹配数组中对象字段等于 v 的元素（可多次，全部满足才算）。
数值比较：--where "age>=30" 支持 > >= < <= == != 与纯相等。

用法:
    python json-point-query.py data.json users.0.name
    python json-point-query.py data.json "users[1:3]"
    python json-point-query.py data.json users --where "age>=30"
    cat data.json | python json-point-query.py - a.b.c

示例命令:
    python json-point-query.py data.json users.0.name
    python json-point-query.py data.json users --where "city=北京"
"""
import argparse
import json
import operator
import re
import sys

OPS = {
    ">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt,
    "!=": operator.ne, "==": operator.eq, "=": operator.eq,
}
TOKEN_RE = re.compile(
    r"(?P<key>\.?[^.\[\]]+)"
    r"|(?P<slice>\[-?\d*:-?\d*\])"
    r"|(?P<idx>\[-?\d+\])"
)


def parse_literal(s: str):
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            pass
    return s


def compile_filters(where):
    conds = []
    for w in where:
        for opstr in ("!=", ">=", "<=", "==", "=", ">", "<"):
            if opstr in w:
                key, _, val = w.partition(opstr)
                if not key:
                    raise SystemExit(f"错误: --where {w!r} 缺少字段名")
                conds.append((key, OPS[opstr], parse_literal(val), w))
                break
        else:
            raise SystemExit(f"错误: --where {w!r} 缺少比较运算符（如 k=v 或 k>=1）")
    return conds


def resolve(path: str, node):
    if path in (None, "", ".", "$"):
        return node
    consumed = 0
    for m in TOKEN_RE.finditer(path):
        if m.start() != consumed:
            raise SystemExit(f"错误: 无法解析路径 {path!r}（位置 {consumed} 附近）")
        consumed = m.end()
        if m.group("key") is not None:
            key = m.group("key").lstrip(".")
            if isinstance(node, list) and re.fullmatch(r"-?\d+", key):
                node = node[int(key)]
            elif isinstance(node, dict):
                if key not in node:
                    raise SystemExit(f"错误: 键 {key!r} 不存在")
                node = node[key]
            else:
                raise SystemExit(f"错误: 路径段 {key!r} 要求对象，实际为 "
                                 f"{type(node).__name__}")
        elif m.group("idx") is not None:
            if not isinstance(node, list):
                raise SystemExit(f"错误: 下标 {m.group('idx')!r} 要求数组，实际为 "
                                 f"{type(node).__name__}")
            node = node[int(m.group("idx")[1:-1])]
        else:
            if not isinstance(node, list):
                raise SystemExit(f"错误: 切片 {m.group('slice')!r} 要求数组，实际为 "
                                 f"{type(node).__name__}")
            lo, _, hi = m.group("slice")[1:-1].partition(":")
            node = node[slice(int(lo) if lo else None, int(hi) if hi else None)]
    if consumed != len(path):
        raise SystemExit(f"错误: 无法解析路径 {path!r}（位置 {consumed} 附近）")
    return node


def main() -> int:
    ap = argparse.ArgumentParser(description="点路径 + 简易过滤条件查询 JSON")
    ap.add_argument("file", help="JSON 文件；'-' 表示 stdin")
    ap.add_argument("path", nargs="?", default="", help="点路径，如 a.b.0.c 或 users[1:3]")
    ap.add_argument("-w", "--where", action="append", default=[],
                    help="过滤条件（作用于数组），如 age>=30 或 name=Tom；可多次")
    ap.add_argument("-c", "--compact", action="store_true", help="紧凑输出（不缩进）")
    ap.add_argument("-n", "--newline", action="store_true",
                    help="对结果列表逐项输出")
    args = ap.parse_args()

    try:
        raw = sys.stdin.buffer.read() if args.file == "-" else open(args.file, "rb").read()
    except OSError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"错误: JSON 解析失败: {e}", file=sys.stderr)
        return 1

    try:
        result = resolve(args.path, data)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2

    if args.where:
        if not isinstance(result, list):
            print("错误: --where 要求路径结果为数组", file=sys.stderr)
            return 2
        conds = compile_filters(args.where)
        filtered = []
        for item in result:
            if not isinstance(item, dict):
                continue
            ok = True
            for key, op, val, orig in conds:
                if key not in item:
                    ok = False
                    break
                try:
                    if not op(item[key], val):
                        ok = False
                        break
                except TypeError:
                    ok = False
                    break
            if ok:
                filtered.append(item)
        result = filtered

    indent = None if args.compact else 2
    if args.newline and isinstance(result, list):
        for item in result:
            print(json.dumps(item, ensure_ascii=False, indent=indent))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=indent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
