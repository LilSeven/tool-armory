#!/usr/bin/env python3
"""BOM 添加与移除（bom-ops）：批量给文本文件添加或移除
UTF-8 / UTF-16 LE / UTF-16 BE 的 BOM 标记。

用法:
    python bom-ops.py add [--utf8|--utf16le|--utf16be] <文件...> [--force]
    python bom-ops.py remove <文件...>
    python bom-ops.py check <文件...>
示例:
    python bom-ops.py add --utf8 a.txt b.txt
    python bom-ops.py add --utf16le a.txt --force
    python bom-ops.py remove a.txt b.txt
    python bom-ops.py check a.txt

说明:
    add 直接在文件头部前置对应 BOM 字节，不做任何转码；
    若文件已有（别的）BOM 则默认跳过并提示，--force 可替换为目标 BOM。
    remove 移除文件头部已知的 BOM 字节（若无则不动）。
    check 报告每个文件当前的 BOM 状态。

退出码: 0 完成（个别跳过不算失败）；1 有文件操作失败；2 用法错误。
"""

import argparse
import os
import sys

# 顺序重要：UTF-32 LE 前缀包含 UTF-16 LE BOM，需先判长 BOM。
# 但本工具只管理 UTF-8 / UTF-16 LE/BE，故把 UTF-32 识别为“其他 BOM”。
KNOWN = [
    ("utf-8", b"\xef\xbb\xbf"),
    ("utf-16-le", b"\xff\xfe"),
    ("utf-16-be", b"\xfe\xff"),
]
OTHER_BOMS = [
    ("utf-32-le", b"\xff\xfe\x00\x00"),
    ("utf-32-be", b"\x00\x00\xfe\xff"),
]


def detect_bom(data):
    """返回 (BOM 名称, BOM 字节)；无 BOM 返回 (None, b"")。"""
    for name, bom in OTHER_BOMS:
        if data.startswith(bom):
            return name, bom
    for name, bom in KNOWN:
        if data.startswith(bom):
            return name, bom
    return None, b""


def read(path):
    with open(path, "rb") as f:
        return f.read()


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def do_add(args):
    if args.utf16le:
        target, bom = "utf-16-le", b"\xff\xfe"
    elif args.utf16be:
        target, bom = "utf-16-be", b"\xfe\xff"
    else:
        target, bom = "utf-8", b"\xef\xbb\xbf"
    failed = 0
    for path in args.files:
        try:
            data = read(path)
        except OSError as e:
            print("[失败] %s: %s" % (path, e), file=sys.stderr)
            failed += 1
            continue
        name, old = detect_bom(data)
        if name == target:
            print("[跳过] %s: 已有 %s BOM" % (path, target))
            continue
        if name is not None:
            if not args.force:
                print("[跳过] %s: 已有 %s BOM（加 --force 可替换为 %s）"
                      % (path, name, target))
                continue
            data = data[len(old):]
        try:
            write(path, bom + data)
        except OSError as e:
            print("[失败] %s: %s" % (path, e), file=sys.stderr)
            failed += 1
            continue
        note = "（替换原 %s BOM）" % name if name else ""
        print("[完成] %s: 已添加 %s BOM%s" % (path, target, note))
    return 1 if failed else 0


def do_remove(args):
    failed = 0
    for path in args.files:
        try:
            data = read(path)
        except OSError as e:
            print("[失败] %s: %s" % (path, e), file=sys.stderr)
            failed += 1
            continue
        name, bom = detect_bom(data)
        if name is None:
            print("[跳过] %s: 无 BOM" % path)
            continue
        try:
            write(path, data[len(bom):])
        except OSError as e:
            print("[失败] %s: %s" % (path, e), file=sys.stderr)
            failed += 1
            continue
        print("[完成] %s: 已移除 %s BOM" % (path, name))
    return 1 if failed else 0


def do_check(args):
    for path in args.files:
        try:
            data = read(path)
        except OSError as e:
            print("[失败] %s: %s" % (path, e), file=sys.stderr)
            continue
        name, _ = detect_bom(data)
        if name:
            print("%s: 有 %s BOM" % (path, name))
        else:
            print("%s: 无 BOM" % path)
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="批量添加/移除/检查 UTF-8 与 UTF-16 LE/BE 的 BOM")
    sub = ap.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add", help="添加 BOM（默认 UTF-8）")
    g = p_add.add_mutually_exclusive_group()
    g.add_argument("--utf8", action="store_true", help="UTF-8 BOM（默认）")
    g.add_argument("--utf16le", action="store_true", help="UTF-16 LE BOM")
    g.add_argument("--utf16be", action="store_true", help="UTF-16 BE BOM")
    p_add.add_argument("files", nargs="+", help="目标文件")
    p_add.add_argument("--force", action="store_true",
                       help="文件已有其他 BOM 时替换为目标 BOM")
    p_add.set_defaults(func=do_add)

    p_rm = sub.add_parser("remove", help="移除 BOM")
    p_rm.add_argument("files", nargs="+", help="目标文件")
    p_rm.set_defaults(func=do_remove)

    p_ck = sub.add_parser("check", help="检查 BOM 状态")
    p_ck.add_argument("files", nargs="+", help="目标文件")
    p_ck.set_defaults(func=do_check)

    args = ap.parse_args(argv)
    if not args.cmd:
        ap.error("请指定子命令: add / remove / check")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
