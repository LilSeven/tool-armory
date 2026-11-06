#!/usr/bin/env python3
r"""只读文件清单（readonly-lister）—— 找出目录树中被标记只读的文件。

批量写入、同步或清理脚本莫名失败时，目标文件带只读属性是常见原因。
本工具递归扫描目录，列出所有带只读属性的文件，便于逐个确认或用
`attrib -r` 批量清除。

Windows 下直接读取 FILE_ATTRIBUTE_READONLY 属性位；其他平台退化为
"用户不可写"判定。

用法:
    python readonly-lister.py <目录> [选项]

示例:
    python readonly-lister.py D:\project
    python readonly-lister.py D:\project --relative
    python readonly-lister.py D:\project --sort size --quiet

选项:
    --relative               输出相对路径（相对起始目录）
    --sort name|path|size|mtime
                             排序方式，默认 path（升序）
    --quiet                  只输出文件路径，不打印末尾统计

退出码: 0 正常（包括没有只读文件）；2 参数错误或目录不存在。
"""

import argparse
import os
import stat
import sys

READONLY_BIT = getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1)


def is_readonly(path, st):
    """判断一个文件是否被标记只读。"""
    attrs = getattr(st, "st_file_attributes", None)
    if attrs is not None:  # Windows: 直接读只读属性位
        return bool(attrs & READONLY_BIT)
    return not os.access(path, os.W_OK)  # 其他平台的退化判定


def scan(root):
    """返回 (只读文件记录列表, 扫描文件总数, 错误信息列表)。"""
    records = []
    errors = []
    total = 0

    def on_walk_error(exc):
        errors.append(str(exc))

    for dirpath, _dirnames, filenames in os.walk(
            root, onerror=on_walk_error, followlinks=False):
        for name in filenames:
            path = os.path.join(dirpath, name)
            total += 1
            try:
                st = os.lstat(path)
            except OSError as exc:
                errors.append("%s: %s" % (path, exc))
                continue
            if is_readonly(path, st):
                records.append((path, st.st_size, st.st_mtime))
    return records, total, errors


SORT_KEYS = {
    "name": lambda r: (os.path.basename(r[0]).lower(), r[0]),
    "path": lambda r: (r[0].lower(), r[0]),
    "size": lambda r: (r[1], r[0]),
    "mtime": lambda r: (r[2], r[0]),
}


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="列出目录树中被标记只读的文件。")
    parser.add_argument("root", help="要扫描的起始目录")
    parser.add_argument("--relative", action="store_true",
                        help="输出相对路径（相对起始目录）")
    parser.add_argument("--sort", choices=sorted(SORT_KEYS), default="path",
                        help="排序方式，默认 path（升序）")
    parser.add_argument("--quiet", action="store_true",
                        help="只输出文件路径，不打印末尾统计")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.root):
        parser.error("目录不存在或不是目录: %s" % args.root)

    records, total, errors = scan(args.root)
    records.sort(key=SORT_KEYS[args.sort])
    for path, _size, _mtime in records:
        if args.relative:
            try:
                path = os.path.relpath(path, args.root)
            except ValueError:
                pass
        print(path)

    if not args.quiet:
        print("合计: %d/%d 个文件只读。" % (len(records), total))
    if errors:
        print("提示: %d 个路径无法访问，已跳过。" % len(errors),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
