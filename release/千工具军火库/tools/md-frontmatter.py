#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown 前置元数据（YAML frontmatter）解析 / 校验 / 修改。

只支持 frontmatter 常用子集：标量（字符串/数字/布尔/null）、单引号/双引号字符串、
`- item` 块列表与 `[a, b]` 内联列表、`#` 注释。不支持嵌套映射。

用法:
  python md-frontmatter.py note.md --show                     # 打印解析后的字段
  python md-frontmatter.py note.md --get title
  python md-frontmatter.py note.md --set title="新标题" --set tags="a,b" --set draft=false
  python md-frontmatter.py note.md --del obsolete_key
  python md-frontmatter.py note.md --require title --require tags   # 校验必填字段
  python md-frontmatter.py note.md --set title="x" --in-place      # 写回原文件

行为:
  - 无 frontmatter 时 --set 会新建一个；--get/--require 返回空/失败。
  - 修改类操作默认打印修改后的完整文件到 stdout，--in-place 直接写回（自动备份 .bak）。
  - 退出码: 0 成功；1 校验失败；2 文件/参数错误。
"""

import argparse
import json
import shutil
import sys

BOOLS = {"true": True, "false": False, "yes": True, "no": False,
         "True": True, "False": False}


def parse_value(raw):
    s = raw.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [parse_value(x) for x in split_items(inner)] if inner else []
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    low = s.lower()
    if low in ("true", "false", "yes", "no"):
        return BOOLS.get(s, BOOLS[low])
    if s in ("null", "~", ""):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def split_items(s):
    items, buf, quote = [], "", None
    for ch in s:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf += ch
        elif ch == ",":
            items.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        items.append(buf.strip())
    return items


def parse_frontmatter(text):
    """返回 (meta_dict, body_text, fm_lines 或 None)。"""
    if not text.startswith("---"):
        return {}, text, None
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return {}, text, None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text, None
    fm_lines = lines[1:end]
    body = "\n".join(lines[end + 1:])
    meta, cur_key = {}, None
    for line in fm_lines:
        if not line.strip() or line.strip().startswith("#"):
            continue
        if cur_key is not None and line.strip().startswith("- "):  # 列表项（支持缩进或不缩进）
            item = line.strip()
            if item.startswith("- "):
                if not isinstance(meta[cur_key], list):
                    meta[cur_key] = [] if meta[cur_key] is None else [meta[cur_key]]
                meta[cur_key].append(parse_value(item[2:]))
            continue
        key, sep, raw = line.partition(":")
        if not sep:
            continue
        cur_key = key.strip()
        if raw.strip() == "":
            meta[cur_key] = None  # 可能后面跟列表
        else:
            meta[cur_key] = parse_value(raw)
            cur_key = None if raw.strip() else cur_key
    return meta, body, fm_lines


def render_value(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        for x in v:
            pass
        return "\n" + "\n".join("- %s" % render_value(x) for x in v)
    s = str(v)
    if s == "" or any(c in s for c in ":#{}[],&*?|-<>=!%@\"'`\n") and not (s.startswith("[") and s.endswith("]")):
        return "'%s'" % s.replace("'", "''")
    return s


def dumps_meta(meta):
    out = ["---"]
    for k, v in meta.items():
        if isinstance(v, list):
            out.append("%s:" % k)
            for x in v:
                out.append("- %s" % render_value(x))
        else:
            out.append("%s: %s" % (k, render_value(v)))
    out.append("---")
    return "\n".join(out)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="Markdown frontmatter 处理")
    ap.add_argument("mdfile")
    ap.add_argument("--show", action="store_true", help="打印解析后的字段（JSON）")
    ap.add_argument("--get", metavar="KEY")
    ap.add_argument("--set", metavar="KEY=VALUE", action="append", default=[])
    ap.add_argument("--del", metavar="KEY", dest="del_keys", action="append", default=[])
    ap.add_argument("--require", metavar="KEY", action="append", default=[],
                    help="校验必填字段（可多次）")
    ap.add_argument("--in-place", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    try:
        with open(args.mdfile, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print("读取错误: %s" % e, file=sys.stderr)
        sys.exit(2)

    meta, body, _ = parse_frontmatter(text)

    if (args.show or args.get is not None) and (args.set or args.del_keys):
        print("错误: --show/--get 是只读操作，不能与 --set/--del 混用", file=sys.stderr)
        sys.exit(2)

    if args.show:
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.get is not None:
        if args.get in meta:
            v = meta[args.get]
            print(json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v)
            sys.exit(0)
        print("(无字段 %r)" % args.get, file=sys.stderr)
        sys.exit(1)

    missing = [k for k in args.require if k not in meta or meta[k] in (None, "", [])]
    if missing:
        print("校验失败: 缺少必填字段: %s" % ", ".join(missing))
        sys.exit(1)
    if args.require:
        print("校验通过: 必填字段齐全 (%s)" % ", ".join(args.require))
        sys.exit(0)

    changed = False
    for item in args.set:
        key, sep, val = item.partition("=")
        if not sep:
            print("错误: --set 需要 KEY=VALUE 形式: %r" % item, file=sys.stderr)
            sys.exit(2)
        meta[key.strip()] = parse_value(val)
        changed = True
    for key in args.del_keys:
        if key in meta:
            del meta[key]
            changed = True

    if not changed:
        print("无修改操作：请加 --show/--get/--set/--del/--require", file=sys.stderr)
        sys.exit(2)

    new_text = dumps_meta(meta) + "\n" + body
    if args.in_place:
        if not args.no_backup:
            shutil.copy2(args.mdfile, args.mdfile + ".bak")
        with open(args.mdfile, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        print("已写回 %s" % args.mdfile, file=sys.stderr)
    else:
        sys.stdout.write(new_text)


if __name__ == "__main__":
    main()
