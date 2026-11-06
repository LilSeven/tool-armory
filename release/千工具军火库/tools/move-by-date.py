#!/usr/bin/env python3
"""按日期归档：把文件按修改时间移动到 年/月 分层目录，模板可配。

用法:
  python move-by-date.py <目录> [--template "%Y/%Y-%m"] [--use-name] [--dry-run] [--recursive]

选项:
  --template  目录模板，基于文件修改时间格式化，默认 "%Y/%Y-%m"
              例如 2026/2026-11/；可用 "%Y/%m" 得到 2026/11/
  --use-name  以文件名（不含扩展名）作为最后一级目录前缀（可选附加）
  --dry-run   预演模式，只打印将要执行的操作
  --recursive 递归处理子目录

说明:
  - 默认模板 "%Y/%Y-%m" 会生成 2026/2026-11/ 这样的层级
  - 目标重名时自动追加序号 (name_1.txt)

示例命令:
  python move-by-date.py D:/photos --dry-run
  python move-by-date.py D:/photos --template "%Y/%m"
"""

import argparse
import datetime
import os
import shutil
import sys


def unique_target(dst: str) -> str:
    if not os.path.exists(dst):
        return dst
    root, ext = os.path.splitext(dst)
    i = 1
    while os.path.exists(f"{root}_{i}{ext}"):
        i += 1
    return f"{root}_{i}{ext}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="按修改时间把文件移动到年/月分层目录")
    ap.add_argument("directory", help="目标目录")
    ap.add_argument("--template", default="%Y/%Y-%m",
                    help='日期目录模板，默认 "%Y/%Y-%m"')
    ap.add_argument("--recursive", action="store_true", help="递归处理子目录")
    ap.add_argument("--dry-run", action="store_true", help="预演，不实际移动")
    args = ap.parse_args(argv)

    base = os.path.abspath(args.directory)
    if not os.path.isdir(base):
        print(f"错误: 目录不存在: {base}", file=sys.stderr)
        return 2

    moved = 0
    roots = [base]
    if args.recursive:
        for dirpath, _, _ in os.walk(base):
            roots.append(os.path.abspath(dirpath))
        roots = sorted(set(roots))

    for dirpath in roots:
        try:
            entries = os.listdir(dirpath)
        except OSError:
            continue
        for name in sorted(entries):
            src = os.path.join(dirpath, name)
            if not os.path.isfile(src):
                continue
            st = os.stat(src)
            dt = datetime.datetime.fromtimestamp(st.st_mtime)
            rel = dt.strftime(args.template)
            if not rel or rel.startswith(os.sep) or ".." in rel:
                print(f"错误: 模板结果非法: {rel!r}", file=sys.stderr)
                return 2
            dst_dir = os.path.join(base, rel)
            dst = unique_target(os.path.join(dst_dir, name))
            if os.path.abspath(src) == os.path.abspath(dst):
                continue
            print(f"{'[预演] ' if args.dry_run else ''}{src} -> {dst}")
            if not args.dry_run:
                os.makedirs(dst_dir, exist_ok=True)
                shutil.move(src, dst)
            moved += 1

    verb = "将移动" if args.dry_run else "已移动"
    print(f"{verb} {moved} 个文件 (模板: {args.template})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
