"""多文件内容替换 —— 对一批文本文件执行查找替换（字面或正则），修改前先写 .bak 备份。

用法:
    python replace-in-files.py <目录或文件...> --find <内容> --replace <内容>
                               [--regex] [--glob <模式>] [--encoding <编码>] [--no-backup]

示例:
    python replace-in-files.py ./src --find "foo" --replace "bar" --glob "*.txt"
    python replace-in-files.py a.txt b.txt --find "h\\d+" --replace "N" --regex
    python replace-in-files.py ./src --find "old" --replace "new" --dry-run

说明:
    --regex 时 find 按正则解释（replace 支持 \\1 等反向引用）；默认字面替换。
    修改前将原文件复制为 <原名>.bak；--dry-run 只报告将要修改的文件。
    --no-backup 跳过备份（慎用）。退出码 0 表示成功（即使 0 个文件被修改）。
"""

import argparse
import glob as globmod
import os
import re
import shutil
import sys


def iter_files(targets, pattern):
    """收集目标文件集合（去重、保持顺序）。"""
    seen = set()
    files = []
    for t in targets:
        if os.path.isdir(t):
            for dirpath, _dirnames, filenames in os.walk(t):
                for fn in filenames:
                    if pattern is None or globmod.fnmatch.fnmatch(fn, pattern):
                        f = os.path.join(dirpath, fn)
                        if f not in seen:
                            seen.add(f)
                            files.append(f)
        elif os.path.isfile(t):
            if t not in seen:
                seen.add(t)
                files.append(t)
        else:
            print(f"警告: 跳过不存在的路径: {t}", file=sys.stderr)
    return files


def main(argv=None):
    p = argparse.ArgumentParser(description="批量查找替换文本文件内容，先备份 .bak")
    p.add_argument("targets", nargs="+", help="目录或文件")
    p.add_argument("--find", required=True, help="要查找的内容（或正则）")
    p.add_argument("--replace", required=True, help="替换为的内容")
    p.add_argument("--regex", action="store_true", help="将 find 按正则解释")
    p.add_argument("--glob", dest="pattern", default=None,
                   help="目录模式下按通配符过滤文件名，如 *.txt")
    p.add_argument("--encoding", default="utf-8", help="文件编码（默认 utf-8）")
    p.add_argument("--no-backup", action="store_true", help="不写 .bak 备份")
    p.add_argument("--dry-run", action="store_true", help="只报告，不修改")
    args = p.parse_args(argv)

    try:
        rx = re.compile(args.find) if args.regex else None
    except re.error as e:
        print(f"错误: 正则无效: {e}", file=sys.stderr)
        return 2

    files = iter_files(args.targets, args.pattern)
    changed = 0
    errors = 0
    for f in files:
        try:
            with open(f, "r", encoding=args.encoding, newline="") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as e:
            print(f"跳过 {f}: {e}", file=sys.stderr)
            errors += 1
            continue

        if rx is not None:
            new_text, n = rx.subn(args.replace, text)
        else:
            n = text.count(args.find)
            new_text = text.replace(args.find, args.replace)
        if n == 0:
            continue

        print(f"{f}: {n} 处替换" + (" [dry-run]" if args.dry_run else ""))
        if args.dry_run:
            continue
        try:
            if not args.no_backup:
                shutil.copy2(f, f + ".bak")
            with open(f, "w", encoding=args.encoding, newline="") as fh:
                fh.write(new_text)
        except OSError as e:
            print(f"错误: 写入 {f} 失败: {e}", file=sys.stderr)
            errors += 1
            continue
        changed += 1

    print(f"共修改 {changed} 个文件" +
          (f"，{errors} 个出错" if errors else "") +
          ("（dry-run，未实际写入）" if args.dry_run else ""))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
