#!/usr/bin/env python3
r"""目录树打印器（tree-printer）

用途:
    递归打印目录树并显示每项大小：文件显示自身大小，目录显示其中
    全部内容的累计大小（累计大小不受显示深度限制）。可控制最大深度、
    排序方式（名称/大小/修改时间）以及是否包含隐藏文件（以 . 开头
    或带 Windows 隐藏属性）。

示例命令:
    python tree-printer.py K:\proj
    python tree-printer.py K:\proj --depth 5 --sort size
    python tree-printer.py K:\proj --sort time
    python tree-printer.py K:\proj --all --bytes
    python tree-printer.py K:\proj --depth 0        # 0 = 不限深度

退出码:
    0 = 正常完成
    2 = 参数错误或目录不存在
"""

import argparse
import datetime
import os
import stat
import sys

HIDDEN_ATTR = 0x2  # FILE_ATTRIBUTE_HIDDEN


def _safe_stdout():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass


def human(n):
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            break
        value /= 1024.0
    return "%d B" % int(value) if unit == "B" else "%.1f %s" % (value, unit)


def is_hidden_path(path, name):
    if name.startswith("."):
        return True
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & HIDDEN_ATTR)


def build_node(path, name, totals, opts):
    """递归构建节点树并累计大小；目录大小 = 子项大小之和。"""
    node = {"name": name, "path": path, "is_dir": False, "is_link": False,
            "hidden": False, "size": 0, "mtime": 0.0, "children": [], "error": ""}
    try:
        st = os.lstat(path)
    except OSError as exc:
        node["error"] = str(exc)
        return node
    node["mtime"] = st.st_mtime
    node["hidden"] = is_hidden_path(path, name)
    if stat.S_ISLNK(st.st_mode):
        node["is_link"] = True
        totals["links"] += 1
        try:
            node["size"] = os.stat(path).st_size
        except OSError:
            node["size"] = 0
        return node
    if stat.S_ISDIR(st.st_mode):
        node["is_dir"] = True
        totals["dirs"] += 1
        try:
            entries = list(os.scandir(path))
        except OSError as exc:
            node["error"] = str(exc)
            return node
        total = 0
        for entry in entries:
            if not opts.all and is_hidden_path(entry.path, entry.name):
                continue
            child = build_node(entry.path, entry.name, totals, opts)
            node["children"].append(child)
            total += child["size"]
        node["size"] = total
        return node
    totals["files"] += 1
    totals["bytes"] += st.st_size
    node["size"] = st.st_size
    return node


def sort_tree(node, opts):
    if opts.sort == "size":
        key = lambda n: (-n["size"], n["name"].lower())
    elif opts.sort == "time":
        key = lambda n: (-n["mtime"], n["name"].lower())
    else:  # name: 目录优先，再按名称
        key = lambda n: (not n["is_dir"], n["name"].lower())
    node["children"].sort(key=key)
    for child in node["children"]:
        sort_tree(child, opts)


def render(node, opts, out, prefix="", budget=None):
    """渲染 node 的子项。budget=None 不限层数，否则为剩余可显示层数。"""
    if budget is not None and budget <= 0:
        return
    kids = node["children"]
    for i, child in enumerate(kids):
        last = (i == len(kids) - 1)
        branch = "└── " if last else "├── "
        label = child["name"]
        if child["is_dir"]:
            label += "/"
        if child["is_link"]:
            label += " [链接]"
        if child["error"]:
            label += " [错误: %s]" % child["error"]
        size_text = "%d B" % child["size"] if opts.bytes else human(child["size"])
        line = "%s%s%-40s %10s" % (prefix, branch, label, size_text)
        if opts.sort == "time":
            line += "  %s" % datetime.datetime.fromtimestamp(
                child["mtime"]).strftime("%Y-%m-%d %H:%M")
        out.append(line)
        if child["is_dir"] and not child["is_link"]:
            render(child, opts, out,
                   prefix + ("    " if last else "│   "),
                   None if budget is None else budget - 1)


def main(argv=None):
    _safe_stdout()
    sys.setrecursionlimit(20000)
    parser = argparse.ArgumentParser(
        description="递归打印目录树并显示每项大小，可控制深度、排序方式与是否含隐藏文件。")
    parser.add_argument("directory", help="要打印的目录")
    parser.add_argument("-d", "--depth", type=int, default=3,
                        help="最大显示深度（根下直接子项为第 1 层）；0=不限，默认 3")
    parser.add_argument("-s", "--sort", choices=("name", "size", "time"), default="name",
                        help="排序方式: name=名称(目录优先), size=大小降序, time=修改时间降序")
    parser.add_argument("-a", "--all", action="store_true",
                        help="包含隐藏文件/目录（. 开头或 Windows 隐藏属性）")
    parser.add_argument("-b", "--bytes", action="store_true", help="以原始字节数显示大小")
    args = parser.parse_args(argv)

    root = args.directory
    if not os.path.isdir(root):
        print("错误: 目录不存在或不是目录: %s" % root, file=sys.stderr)
        return 2
    root = os.path.abspath(root)

    totals = {"dirs": 0, "files": 0, "links": 0, "bytes": 0}
    tree = build_node(root, os.path.basename(root) or root, totals, args)
    sort_tree(tree, args)

    out = ["%s  [%s]" % (tree["name"],
                         "%d B" % tree["size"] if args.bytes else human(tree["size"]))]
    render(tree, args, out, "", None if args.depth == 0 else args.depth)
    print("\n".join(out))
    print()
    print("已扫描: %d 个目录, %d 个文件, %d 个链接, 总计 %s（累计大小不受显示深度限制）"
          % (totals["dirs"], totals["files"], totals["links"],
             "%d B" % totals["bytes"] if args.bytes else human(totals["bytes"])))
    if tree["error"]:
        print("警告: 根目录读取异常: %s" % tree["error"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
