#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""命名卫生检查器 / naming-hygiene

用途:
    递归检查文件名/目录名中的"糟糕命名", 输出整改清单(只列出, 不改名):
      error 级 —— Windows 上非法或高危:
        reserved-name     保留设备名(CON, PRN, AUX, NUL, COM1-9, LPT1-9,
                          按首个点号前的主名判定)
        trailing-space    名称末尾有空白(Windows 会静默丢弃, 之后很多程序打不开)
        trailing-dot      名称以点号结尾(同上)
        illegal-char      含 < > : " / \ | ? * 之一
        control-char      含控制字符
      warning 级 —— 合法但容易踩坑:
        leading-space       名称开头空白
        consecutive-spaces  连续多个空格
        space-before-dot    扩展名前有空格("report .txt")
        unicode-space       含全角空格/不间断空格等 Unicode 空白
        leading-dash        以 "-" 开头(命令行工具会当成选项)

    每条给出建议新名(去首尾空白/去尾点/折叠连续空白/替换非法字符/
    规避保留名), 仅供参考。

示例:
    python naming-hygiene.py "K:\data"
    python naming-hygiene.py "K:\data" --errors-only
    python naming-hygiene.py "K:\data" --json

退出码: 0 = 扫描完成(无论是否发现问题); 2 = 根目录无效或参数错误。
仅使用 Python 标准库; 输出为 UTF-8; 只读扫描, 不会重命名任何文件。
"""

import argparse
import json
import os
import re
import sys

ILLEGAL_CHARS = set('<>:"/\\|?*')
RESERVED_NAMES = ({"CON", "PRN", "AUX", "NUL"}
                  | {f"COM{i}" for i in range(1, 10)}
                  | {f"LPT{i}" for i in range(1, 10)})


def setup_streams():
    """让 stdout/stderr 以 UTF-8 输出, 避免中文/特殊字符在 Windows 控制台报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def walk_tree(root, max_depth=None, errors=None, skipped=None):
    """先序遍历目录树, 逐条 yield (dirpath, name, is_dir, depth)。

    - 根的直接子项 depth=0; max_depth 限制下钻层数(None 不限);
    - 目录内条目按名称排序, 输出顺序确定;
    - 符号链接/目录联接不跟随; realpath 已访问过的目录跳过(防环);
    - 无权限等 OSError 记入 errors 列表后继续, 不中断整体扫描。
    """
    stack = [(root, 0)]
    seen = set()
    while stack:
        cur, depth = stack.pop()
        try:
            real = os.path.realpath(cur)
        except OSError:
            real = cur
        if real in seen:
            if skipped is not None:
                skipped.append(cur)
            continue
        seen.add(real)
        try:
            with os.scandir(cur) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            if errors is not None:
                errors.append((cur, str(exc)))
            continue
        subdirs = []
        for ent in entries:
            try:
                is_dir = ent.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            yield cur, ent.name, is_dir, depth
            if is_dir and (max_depth is None or depth + 1 <= max_depth):
                subdirs.append((os.path.join(cur, ent.name), depth + 1))
        for sub in reversed(subdirs):
            stack.append(sub)


def visible(text):
    """控制字符/代理对以 \\uXXXX 显示, 其余字符原样保留。"""
    out = []
    for ch in text:
        o = ord(ch)
        if o < 32 or o == 127 or 0xD800 <= o <= 0xDFFF:
            out.append(f"\\u{o:04X}")
        else:
            out.append(ch)
    return "".join(out)


def check_name(name):
    """检查单个名称, 返回去重后的 [(tag, severity, detail), ...]。

    severity: "error" = Windows 上非法/高危; "warning" = 合法但易踩坑。
    """
    problems = []
    stem = name.split(".", 1)[0].upper()
    if stem in RESERVED_NAMES:
        problems.append(("reserved-name", "error", stem))
    for ch in name:
        o = ord(ch)
        if o < 32 or o == 127:
            problems.append(("control-char", "error", f"U+{o:04X}"))
        elif ch in ILLEGAL_CHARS:
            problems.append(("illegal-char", "error", f"'{ch}'"))
    if name != name.rstrip():
        problems.append(("trailing-space", "error", f"U+{ord(name[-1]):04X}"))
    if name.endswith("."):
        problems.append(("trailing-dot", "error", ""))
    if name != name.lstrip():
        problems.append(("leading-space", "warning", f"U+{ord(name[0]):04X}"))
    if "  " in name:
        problems.append(("consecutive-spaces", "warning", ""))
    if re.search(r"\s+\.", name):
        problems.append(("space-before-dot", "warning", ""))
    if any(ord(c) > 127 and c.isspace() for c in name):
        problems.append(("unicode-space", "warning", ""))
    if name.startswith("-"):
        problems.append(("leading-dash", "warning", ""))
    deduped = []
    for p in problems:
        if p not in deduped:
            deduped.append(p)
    return deduped


def suggest(name):
    """根据问题生成建议新名(尽力而为, 不保证在目标目录中唯一)。"""
    s = "".join("_" if (ord(c) < 32 or ord(c) == 127 or c in ILLEGAL_CHARS) else c
                for c in name)
    s = re.sub(r"\s+", " ", s)   # 全角/连续空白折叠为单个半角空格
    s = s.strip()
    s = re.sub(r" +\.", ".", s)  # 扩展名前的空格去掉
    s = s.rstrip(".")
    if s.split(".", 1)[0].upper() in RESERVED_NAMES:
        s = "_" + s
    if s.startswith("-"):
        s = "_" + s
    return s or "_"


def main(argv=None):
    setup_streams()
    parser = argparse.ArgumentParser(
        prog="naming-hygiene",
        description="检查末尾空格/点号、非法字符、连续空格等糟糕命名并输出整改清单。",
    )
    parser.add_argument("root", nargs="?", default=".",
                        help="要扫描的根目录 (默认: 当前目录)")
    parser.add_argument("--max-depth", type=int, default=None,
                        help="最多下钻层数(根的直接子项为第 1 层), 默认不限")
    parser.add_argument("--errors-only", action="store_true",
                        help="只显示 error 级问题, 不显示 warning")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"错误: 根目录不存在或不是目录: {root}", file=sys.stderr)
        return 2

    errors, skipped = [], []
    n_files = n_dirs = 0
    items = []       # (是否有error, 相对路径, "file"|"dir", problems, 建议名)
    tag_count = {}
    for dirpath, name, is_dir, _depth in walk_tree(root, args.max_depth, errors, skipped):
        if is_dir:
            n_dirs += 1
        else:
            n_files += 1
        problems = check_name(name)
        if not problems:
            continue
        has_error = any(sev == "error" for _t, sev, _d in problems)
        if args.errors_only and not has_error:
            continue
        rel = os.path.relpath(os.path.join(dirpath, name), root)
        items.append((has_error, rel, "dir" if is_dir else "file", problems, suggest(name)))
        for tag, _sev, _detail in problems:
            tag_count[tag] = tag_count.get(tag, 0) + 1

    items.sort(key=lambda t: (not t[0], t[1]))
    n_error = sum(1 for it in items if it[0])
    n_warn = len(items) - n_error

    if args.json:
        payload = {
            "root": root,
            "files": n_files,
            "dirs": n_dirs,
            "items": [
                {"path": rel, "type": typ,
                 "severity": "error" if has_error else "warning",
                 "problems": [{"tag": t, "severity": s, "detail": d}
                              for t, s, d in problems],
                 "suggestion": sug}
                for has_error, rel, typ, problems, sug in items
            ],
            "error_count": n_error,
            "warning_count": n_warn,
            "tag_summary": dict(sorted(tag_count.items())),
            "errors": [{"path": p, "error": m} for p, m in errors],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"扫描根目录: {root}")
    print(f"条目统计: 文件 {n_files}, 目录 {n_dirs}")
    if items:
        print(f"整改清单: 共 {len(items)} 条 (error {n_error} / warning {n_warn}); "
              '建议仅供参考, 不会自动改名:')
        for has_error, rel, typ, problems, sug in items:
            sev = "error  " if has_error else "warning"
            kind = "目录" if typ == "dir" else "文件"
            tags_str = ", ".join(f"{t}({d})" if d else t for t, _s, d in problems)
            print(f'  [{sev}] [{kind}] {visible(rel)} :: {tags_str} → 建议: "{visible(sug)}"')
    else:
        print("整改清单: 未发现命名问题")
    print("标签统计: "
          + (", ".join(f"{k} {v}" for k, v in sorted(tag_count.items())) or "无"))
    if errors or skipped:
        print(f"无法访问 {len(errors)} 处; 跳过重复/环形目录 {len(skipped)} 处")
    return 0


if __name__ == "__main__":
    sys.exit(main())
