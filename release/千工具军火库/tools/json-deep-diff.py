#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""json-deep-diff.py —— JSON 深度对比工具（仅用 Python 标准库）。

递归比较两个 JSON 文件，输出新增(+)、删除(-)、修改(~)的具体路径，
路径为 JSONPath 风格（如 $.db.port、$.features[1]）。

用途:
    快速定位两份 JSON（配置、接口返回、导出数据）之间到底改了哪些字段。

示例命令:
    python json-deep-diff.py old.json new.json
    python json-deep-diff.py old.json new.json --max-report 20
    python json-deep-diff.py old.json new.json --quiet

选项:
    --max-report N   每类差异最多详细列出 N 条（默认 100，0 表示不限制）
    --quiet          仅输出统计摘要，不列明细

退出码:
    0 = 运行成功（有无差异均算成功）
    2 = 参数错误 / 文件不存在 / JSON 解析失败
"""

import argparse
import json
import sys

ADDED, REMOVED, CHANGED = "+", "-", "~"


def setup_stdio():
    """让输出在 Windows 各类控制台下不因中文而报编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def short_text(value, limit=60):
    try:
        text = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def fmt_path(parts):
    out = "$"
    for kind, key in parts:
        out += f".{key}" if kind == "key" else f"[{key}]"
    return out


def walk(a, b, parts, out):
    """深度比较 a、b，把差异 (类别, 路径, 旧值, 新值) 追加到 out。"""
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            if key not in a:
                out.append((ADDED, parts + (("key", key),), None, b[key]))
            elif key not in b:
                out.append((REMOVED, parts + (("key", key),), a[key], None))
            else:
                walk(a[key], b[key], parts + (("key", key),), out)
    elif isinstance(a, list) and isinstance(b, list):
        common = min(len(a), len(b))
        for i in range(common):
            walk(a[i], b[i], parts + (("idx", i),), out)
        for i in range(common, len(a)):
            out.append((REMOVED, parts + (("idx", i),), a[i], None))
        for i in range(common, len(b)):
            out.append((ADDED, parts + (("idx", i),), None, b[i]))
    elif a != b:
        out.append((CHANGED, parts, a, b))


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def main(argv=None):
    setup_stdio()
    parser = argparse.ArgumentParser(
        description="递归比较两个 JSON 文件，输出增删改的具体路径。")
    parser.add_argument("old", help="旧 JSON 文件")
    parser.add_argument("new", help="新 JSON 文件")
    parser.add_argument("--max-report", type=int, default=100,
                        help="每类差异最多列出 N 条（0=不限，默认 100）")
    parser.add_argument("--quiet", action="store_true",
                        help="只输出统计摘要，不列明细")
    args = parser.parse_args(argv)

    try:
        old_data = load_json(args.old)
        new_data = load_json(args.new)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    diffs = []
    walk(old_data, new_data, (), diffs)
    groups = {ADDED: [], REMOVED: [], CHANGED: []}
    for kind, path, old_val, new_val in diffs:
        groups[kind].append((path, old_val, new_val))

    labels = {ADDED: "新增", REMOVED: "删除", CHANGED: "修改"}
    if not args.quiet:
        for kind in (ADDED, REMOVED, CHANGED):
            items = groups[kind]
            cap = len(items) if args.max_report == 0 else args.max_report
            for path, old_val, new_val in items[:cap]:
                if kind == CHANGED:
                    detail = f"{short_text(old_val)} -> {short_text(new_val)}"
                else:
                    detail = short_text(new_val if kind == ADDED else old_val)
                print(f"{kind} {fmt_path(path)}  {detail}")
            if len(items) > cap:
                print(f"  ...（{labels[kind]}类还有 {len(items) - cap} 条未显示）")

    if not diffs:
        print("两份 JSON 完全一致。")
    else:
        print(f"摘要: 新增 {len(groups[ADDED])} 处, "
              f"删除 {len(groups[REMOVED])} 处, "
              f"修改 {len(groups[CHANGED])} 处。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
