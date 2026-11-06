#!/usr/bin/env python3
"""防冲突重命名 (collision-safe-rename) —— 重命名时若目标名已存在, 自动在扩展名前追加序号(如 file_1.txt), 绝不覆盖既有文件。

改写规则(可组合, 至少提供一个):
    --replace 旧串 新串   把文件名中的旧串替换为新串
    --prefix 字符串        在文件名前加前缀
    --suffix 字符串        在扩展名前加后缀 (report.txt --suffix _v2 -> report_v2.txt)
    --lowercase           文件名整体转小写
冲突处理:
    目标名已存在(包括本批其它文件刚占用的新名)时, 依次尝试 名_1.扩展名、名_2.扩展名 ...;
    原名在改写后不变或改写结果为空的文件跳过; 可加 -n/--dry-run 只预览。

示例:
    python collision-safe-rename.py ./files --replace IMG img
    python collision-safe-rename.py ./files --prefix backup_
    python collision-safe-rename.py ./files --suffix _v2 --lowercase -n

退出码: 0 成功(含被跳过的文件); 1 有重命名执行失败; 2 参数/目录错误。
"""

import argparse
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def transform(name: str, args: argparse.Namespace) -> str:
    out = name
    if args.replace:
        out = out.replace(args.replace[0], args.replace[1])
    if args.prefix:
        out = args.prefix + out
    if args.suffix:
        stem, ext = os.path.splitext(out)
        out = stem + args.suffix + ext
    if args.lowercase:
        out = out.lower()
    return out


def resolve_collision(desired: str, taken: set) -> str:
    """目标名被占用时, 在扩展名前追加 _1、_2 ... 直到可用。"""
    if desired not in taken:
        return desired
    stem, ext = os.path.splitext(desired)
    n = 1
    while f"{stem}_{n}{ext}" in taken:
        n += 1
    return f"{stem}_{n}{ext}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="按规则批量重命名, 目标名冲突时自动追加序号, 绝不覆盖既有文件。")
    ap.add_argument("directory", help="目标目录")
    ap.add_argument("--replace", nargs=2, metavar=("旧串", "新串"),
                    help="替换文件名中的子串")
    ap.add_argument("--prefix", metavar="STR", help="文件名前缀")
    ap.add_argument("--suffix", metavar="STR", help="扩展名前追加的后缀")
    ap.add_argument("--lowercase", action="store_true", help="文件名转小写")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="只预览, 不实际重命名")
    args = ap.parse_args(argv)

    if not (args.replace or args.prefix or args.suffix or args.lowercase):
        ap.error("至少需要提供一种改写规则: --replace / --prefix / --suffix / --lowercase")

    d = Path(args.directory)
    if not d.is_dir():
        print(f"错误: 目录不存在或不是目录: {d}", file=sys.stderr)
        return 2

    files = [p for p in sorted(d.iterdir()) if p.is_file()]
    # taken 是保守占用集合: 原名与所有新旧名都占住, 保证绝不覆盖任何既有文件
    taken = {p.name for p in files}
    done = skipped = errors = 0
    for p in files:
        desired = transform(p.name, args)
        if not desired or desired == p.name:
            skipped += 1
            continue
        final = resolve_collision(desired, taken)
        taken.add(final)  # 原名不从 taken 移除, 防止后续文件占用旧位
        note = f" (冲突, 自动改为 {final})" if final != desired else ""
        if args.dry_run:
            print(f"[dry-run] {p.name} -> {final}{note}")
            done += 1
            continue
        try:
            p.rename(d / final)
            print(f"已重命名 {p.name} -> {final}{note}")
            done += 1
        except OSError as e:
            print(f"失败   {p.name} -> {final}: {e}", file=sys.stderr)
            errors += 1

    print(f"完成: 成功 {done}, 跳过 {skipped}, 失败 {errors} (共 {len(files)} 个文件)"
          + (" [dry-run]" if args.dry_run else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
