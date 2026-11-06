#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env-file-diff.py —— 配置文件对比工具（.env / ini 风格，仅用 Python 标准库）。

比较两份 KEY=VALUE 配置文件的差异：
    + 新增键    - 删除键    ~ 修改键（旧值 -> 新值）
并对疑似敏感的键（password/secret/token/api_key/private 等）打上
[SENSITIVE] 标记，且默认把值掩码为 ***，--no-mask 可查看明文。

支持的写法: # 或 ; 开头的注释行、空行、[section] 小节（键记作 section.key）、
分隔符 = 或 :、值两侧成对引号自动剥除。

示例命令:
    python env-file-diff.py old.env new.env
    python env-file-diff.py old.ini new.ini --no-mask
    python env-file-diff.py old.env new.env --max-report 20

退出码:
    0 = 运行成功
    2 = 文件不存在 / 无法读取
"""

import argparse
import re
import sys

SENSITIVE_RE = re.compile(
    r"(pass(word|wd)?|pwd|secret|token|api[-_]?key|access[-_]?key|"
    r"private[-_]?key|credential|auth|certificate?|sign)",
    re.IGNORECASE)


def setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_env_file(path):
    """解析 .env/ini 风格文件为 {完整键: 值}，小节并入键名（section.key）。"""
    data = {}
    section = ""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line[0] in "#;":
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip().lower()
                continue
            if "=" in line:
                key, _, value = line.partition("=")
            elif ":" in line:
                key, _, value = line.partition(":")
            else:
                print(f"警告: {path}:{lineno} 无法解析，已跳过: {line}",
                      file=sys.stderr)
                continue
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if not key:
                print(f"警告: {path}:{lineno} 键名为空，已跳过", file=sys.stderr)
                continue
            full_key = f"{section}.{key}" if section else key
            data[full_key] = value
    return data


def main(argv=None):
    setup_stdio()
    parser = argparse.ArgumentParser(
        description="比较 .env/ini 风格配置的差异项，并标记疑似敏感的键。")
    parser.add_argument("old", help="旧配置文件")
    parser.add_argument("new", help="新配置文件")
    parser.add_argument("--no-mask", action="store_true",
                        help="不掩码，直接显示疑似敏感键的值")
    parser.add_argument("--max-report", type=int, default=100,
                        help="每类最多列出 N 条（0=不限，默认 100）")
    args = parser.parse_args(argv)

    try:
        old_data = parse_env_file(args.old)
        new_data = parse_env_file(args.new)
    except OSError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    def is_sensitive(key):
        return bool(SENSITIVE_RE.search(key))

    def shown(key, value):
        if not args.no_mask and is_sensitive(key):
            return "***"
        return value

    added = sorted(k for k in new_data if k not in old_data)
    removed = sorted(k for k in old_data if k not in new_data)
    changed = sorted(k for k in new_data
                     if k in old_data and new_data[k] != old_data[k])

    def render(kind, key):
        tag = " [SENSITIVE]" if is_sensitive(key) else ""
        if kind == "~":
            return (f"~ {key}{tag}  "
                    f"{shown(key, old_data[key])} -> {shown(key, new_data[key])}")
        if kind == "+":
            return f"+ {key}{tag}  新值: {shown(key, new_data[key])}"
        return f"- {key}{tag}  旧值: {shown(key, old_data[key])}"

    groups = [("+", "新增", added), ("-", "删除", removed), ("~", "修改", changed)]
    for kind, label, items in groups:
        cap = len(items) if args.max_report == 0 else args.max_report
        for key in items[:cap]:
            print(render(kind, key))
        if len(items) > cap:
            print(f"  ...（{label}类还有 {len(items) - cap} 条未显示）")

    if not (added or removed or changed):
        print("两份配置完全一致。")
        return 0
    sensitive_hits = sum(1 for k in set(added) | set(removed) | set(changed)
                         if is_sensitive(k))
    masked = "，敏感值已掩码显示" if sensitive_hits and not args.no_mask else ""
    print(f"摘要: 新增 {len(added)}, 删除 {len(removed)}, 修改 {len(changed)}"
          f"（疑似敏感键 {sensitive_hits} 个{masked}）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
