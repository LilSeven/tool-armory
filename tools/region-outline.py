#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""region-outline —— 提取 #region/#endregion 等折叠标记，输出代码区域大纲树。

扫描源码文件中的折叠区域标记，按嵌套关系输出带行号的大纲树，
并标记未闭合的区域与多余的 endregion。行首注释前缀可选，
大小写不敏感，兼容以下常见写法：

  #region 名称 / #endregion            （C# / C++）
  # region 名称 / # endregion          （Python / PyCharm 风格）
  //#region 名称 / //#endregion        （JS / TS 风格）
  #pragma region 名称 / #pragma endregion
  #Region "名称" / #End Region         （VB 风格）
  {$region 名称} / {$endregion}        （Delphi 风格）
  <!-- #region --> / <!-- #endregion -->（HTML）
  /* #region */ / /* #endregion */     （CSS）
  (* region *) / (* endregion *)       （Pascal 风格）
  -- region / -- endregion             （Lua 风格）

说明：按行匹配注释型标记，字符串/文档字符串里恰好写着 region 的行
也会被计入；区域名以标点运算符开头（如 "region = 1"）的行会被排除。

示例命令:
  python region-outline.py src/                       # 递归扫描目录
  python region-outline.py a.py b.c                   # 指定多个文件
  python region-outline.py src --include "*.py"       # 目录扫描时按 glob 过滤
  python region-outline.py src --max-depth 2 --count  # 限制深度并附加统计

退出码: 0=发现区域; 1=未发现任何区域; 2=参数或 IO 错误。
仅用 Python 标准库。
"""

import argparse
import fnmatch
import locale
import os
import re
import sys
from pathlib import Path

_PREFIX = r"(?://+|#+|-{2,}|;{2,}|%+|\{\$|<!--|/\*+|\(\*|'+|rem\b)?"
_CORE = r"\s*(?:#\s*pragma\s+|pragma\s+|#)?\s*"
OPEN_RE = re.compile(_PREFIX + _CORE + r"region\b\s*:?\s*(?P<name>.*)$", re.IGNORECASE)
CLOSE_RE = re.compile(_PREFIX + _CORE + r"end[\s_]?region\b", re.IGNORECASE)
# 区域名以这些字符开头时视为普通代码行（如 "region = compute()"）
_BAD_START = set("=.+-*/%<>!&|^~[](){};,:")
_SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules"}


def clean_name(name):
    """清理区域名：去掉行尾注释闭合符、成对引号与空白。"""
    s = name.strip()
    while True:
        new = re.sub(r"(?:-->|\*/|\*\)|\}|\)|#)$", "", s).strip()
        if new != s:
            s = new
            continue
        if len(s) >= 2 and s[0] in "\"'`“”" and s[-1] in "\"'`“”":
            s = s[1:-1].strip()
            continue
        break
    return s


def scan_events(text):
    """把文本扫描成 [(行号, "open"|"close", 名字), ...]。"""
    events = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.rstrip()
        if not s.strip():
            continue
        mo = OPEN_RE.match(s)
        if mo:
            name = clean_name(mo.group("name"))
            if not name or name[0] not in _BAD_START:
                events.append((i, "open", name))
                continue
        if CLOSE_RE.match(s):
            events.append((i, "close", ""))
    return events


def build_outline(events):
    """按嵌套关系构建扁平大纲，返回 (nodes, 未闭合数, 多余 endregion 数)。"""
    stack = []
    nodes = []
    stray = 0
    for lineno, kind, name in events:
        if kind == "open":
            node = {"name": name, "start": lineno,
                    "depth": len(stack) + 1, "closed": False, "stray": False}
            nodes.append(node)
            stack.append(node)
        else:
            if stack:
                stack.pop()["closed"] = True
            else:
                stray += 1
                nodes.append({"name": "", "start": lineno, "depth": 1,
                              "closed": True, "stray": True})
    return nodes, len(stack), stray


def render(fp_str, nodes, unclosed, stray, max_depth, show_count):
    lines = [fp_str]
    for n in nodes:
        if n["stray"]:
            lines.append("  L%-5d!! 多余的 endregion" % n["start"])
            continue
        if max_depth and n["depth"] > max_depth:
            continue
        mark = "" if n["closed"] else "   [未闭合]"
        lines.append("  L%-5d%s%s%s"
                     % (n["start"], "  " * (n["depth"] - 1),
                        n["name"] or "(未命名)", mark))
    if show_count:
        opens = sum(1 for n in nodes if not n["stray"])
        lines.append("  [统计] 区域 %d 个, 未闭合 %d 个, 多余 endregion %d 个"
                     % (opens, unclosed, stray))
    return lines


def decode_bytes(raw, encoding):
    for enc in (encoding, "utf-8", locale.getpreferredencoding(False) or "utf-8"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def iter_files(paths, includes):
    """产出 (路径或 None, 是否出错)；目录递归，None 表示路径缺失。"""
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            for root, dirs, files in os.walk(pp):
                dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
                for f in sorted(files):
                    fp = Path(root) / f
                    if include_match(fp, includes):
                        yield fp, False
        elif pp.is_file():
            yield pp, False
        else:
            yield pp, True


def include_match(fpath, includes):
    if not includes:
        return True
    name = fpath.name
    rel = fpath.as_posix()
    return any(fnmatch.fnmatch(name, g) or fnmatch.fnmatch(rel, g) for g in includes)


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog="region-outline",
        description="提取 #region/#endregion 等折叠标记，输出代码区域大纲树。",
    )
    ap.add_argument("paths", nargs="+", help="文件或目录（目录递归扫描）")
    ap.add_argument("--include", action="append", default=[],
                    help="目录扫描时的文件名 glob 过滤，可多次")
    ap.add_argument("--max-depth", type=int, default=0, help="大纲最大深度（0=不限）")
    ap.add_argument("--count", action="store_true", help="每个文件附加统计信息")
    ap.add_argument("--encoding", default="utf-8", help="文件编码（默认 utf-8，失败自动回退）")
    args = ap.parse_args(argv)

    found_any = False
    out_lines = []
    for fp, missing in iter_files(args.paths, args.include):
        if missing:
            print("警告: 路径不存在，已跳过: %s" % fp, file=sys.stderr)
            continue
        try:
            raw = fp.read_bytes()
        except OSError as exc:
            print("警告: 读取失败，已跳过 %s: %s" % (fp, exc), file=sys.stderr)
            continue
        if b"\x00" in raw[:8192]:
            continue  # 二进制文件
        events = scan_events(decode_bytes(raw, args.encoding))
        if not events:
            continue
        nodes, unclosed, stray = build_outline(events)
        out_lines.extend(render(fp.as_posix(), nodes, unclosed, stray,
                                args.max_depth, args.count))
        found_any = True

    if not out_lines:
        print("未发现任何 region 折叠标记", file=sys.stderr)
        return 1
    print("\n".join(out_lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
