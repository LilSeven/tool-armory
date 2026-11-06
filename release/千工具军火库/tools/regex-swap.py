#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正则替换预览器（regex-swap）：先用 dry-run 展示正则替换前后的 diff，
确认后再写回文件。默认 dry-run；加 --yes 跳过确认直接写回。

用法:
    python -I regex-swap.py -f config.txt -p "OLD_\\d+" -r "NEW_0"          # 仅预览 diff
    python -I regex-swap.py -f config.txt -p "OLD_\\d+" -r "NEW_0" --yes    # 直接写回
    python -I regex-swap.py -f a.txt -p "x" -r "y" --yes --backup           # 写回并留 .bak

diff 格式:
    - 旧行        （将被替换的原始行）
    + 新行        （替换后的行）

只使用 Python 标准库（re / argparse / difflib）。
"""
import argparse
import difflib
import re
import sys
import shutil


def main():
    ap = argparse.ArgumentParser(description="正则批量替换，先预览 diff 再写回")
    ap.add_argument("-f", "--file", required=True, help="目标文件路径")
    ap.add_argument("-p", "--pattern", required=True, help="要查找的正则表达式")
    ap.add_argument("-r", "--replacement", required=True, help="替换文本（支持 \\1、\\g<name> 反向引用）")
    ap.add_argument("-e", "--encoding", default="utf-8", help="文件编码，默认 utf-8")
    ap.add_argument("-i", "--ignore-case", action="store_true", help="忽略大小写")
    ap.add_argument("--yes", action="store_true", help="跳过确认直接写回（非交互场景）")
    ap.add_argument("--backup", action="store_true", help="写回前保存原文件为 <file>.bak")
    args = ap.parse_args()

    flags = re.IGNORECASE if args.ignore_case else 0
    try:
        pattern = re.compile(args.pattern, flags)
    except re.error as e:
        print("正则编译失败: %s" % e, file=sys.stderr)
        return 2

    try:
        with open(args.file, "r", encoding=args.encoding, errors="strict") as f:
            original = f.read()
    except OSError as e:
        print("无法读取文件: %s" % e, file=sys.stderr)
        return 2
    except UnicodeDecodeError as e:
        print("解码失败（-e 指定正确编码）: %s" % e, file=sys.stderr)
        return 2

    replaced, count = pattern.subn(args.replacement, original)
    print("匹配替换次数: %d" % count)

    if count == 0:
        print("没有可替换的内容，文件保持不变。")
        return 0

    diff = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        replaced.splitlines(keepends=True),
        fromfile="原文件 " + args.file,
        tofile="替换后",
    ))
    if diff:
        sys.stdout.writelines(diff)
    else:
        print("(替换仅影响行尾/空白，无逐行 diff 差异)")

    if not args.yes:
        try:
            answer = input("确认写回文件? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("已取消，未写回。")
            return 0

    if args.backup:
        shutil.copy2(args.file, args.file + ".bak")
        print("已备份到 %s.bak" % args.file)

    with open(args.file, "w", encoding=args.encoding) as f:
        f.write(replaced)
    print("已写回 %s（共替换 %d 处）" % (args.file, count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
