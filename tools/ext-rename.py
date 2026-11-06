#!/usr/bin/env python3
"""扩展名改写 (ext-rename) —— 批量修改文件扩展名。

用途:
    扫描目录(默认不递归)中的文件, 把匹配旧扩展名的文件改成新扩展名;
    也可以给无扩展名文件追加扩展名(--extless-to), 或删除扩展名(--strip)。
    匹配扩展名不区分大小写(JPEG 与 jpeg 等价), 新扩展名统一转小写。
    默认 dry-run 只打印将要发生的改动, 加 -y/--yes 才真正执行重命名。

示例:
    python ext-rename.py ./photos --from jpeg --to jpg -y
    python ext-rename.py ./photos --from JPEG --to jpg -y      # 匹配不区分大小写
    python ext-rename.py ./data   --extless-to txt -y          # 无扩展名 -> 追加 .txt
    python ext-rename.py ./logs   --strip -y                   # 删除扩展名 (a.txt -> a)

退出码: 0 成功(含被跳过的冲突); 1 有重命名执行失败; 2 参数/目录错误。
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _norm(ext: str) -> str:
    """统一扩展名写法: 去掉前导点并转小写。"""
    return ext.lstrip(".").lower()


def build_plan(directory: Path, args: argparse.Namespace):
    """返回 [(旧Path, 新文件名), ...], 只含名字确实会变的文件。"""
    plan = []
    for p in sorted(directory.iterdir()):
        if not p.is_file():
            continue
        if not args.include_hidden and p.name.startswith("."):
            continue
        name, ext = p.name, p.suffix
        if args.strip:
            if not ext:
                continue
            new_name = p.stem
        elif args.extless_to:
            if ext:
                continue
            new_name = f"{name}.{_norm(args.extless_to)}"
        else:
            if not ext or _norm(ext) != _norm(args.old_ext):
                continue
            new_name = f"{p.stem}.{_norm(args.new_ext)}"
        if new_name != name:
            plan.append((p, new_name))
    return plan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="批量修改文件扩展名(默认 dry-run 预览, -y 才执行)。")
    ap.add_argument("directory", help="目标目录")
    ap.add_argument("--from", dest="old_ext", metavar="EXT",
                    help="旧扩展名, 如 jpeg (与 --to 搭配)")
    ap.add_argument("--to", dest="new_ext", metavar="EXT",
                    help="新扩展名, 如 jpg")
    ap.add_argument("--extless-to", dest="extless_to", metavar="EXT",
                    help="给无扩展名文件追加该扩展名")
    ap.add_argument("--strip", action="store_true", help="删除文件扩展名")
    ap.add_argument("-y", "--yes", action="store_true",
                    help="真正执行重命名(缺省仅预览)")
    ap.add_argument("--include-hidden", action="store_true",
                    help="包含以点开头的隐藏文件")
    args = ap.parse_args(argv)

    modes = [bool(args.old_ext), bool(args.extless_to), args.strip]
    if sum(modes) != 1:
        ap.error("--from/--to、--extless-to、--strip 三种模式必须且只能选其一")
    if args.old_ext and not args.new_ext:
        ap.error("使用 --from 时必须同时提供 --to")

    d = Path(args.directory)
    if not d.is_dir():
        print(f"错误: 目录不存在或不是目录: {d}", file=sys.stderr)
        return 2

    plan = build_plan(d, args)
    if not plan:
        print("没有需要改写扩展名的文件。")
        return 0

    tag = "[dry-run] " if not args.yes else ""
    done = skipped = errors = 0
    for old, new_name in plan:
        target = old.with_name(new_name)
        if target.exists():
            print(f"{tag}跳过 {old.name} -> {new_name} (目标已存在)")
            skipped += 1
            continue
        if args.yes:
            try:
                old.rename(target)
                print(f"已重命名 {old.name} -> {new_name}")
                done += 1
            except OSError as e:
                print(f"失败   {old.name} -> {new_name}: {e}", file=sys.stderr)
                errors += 1
        else:
            print(f"将重命名 {old.name} -> {new_name}")

    print(f"完成: 成功 {done}, 跳过 {skipped}, 失败 {errors} (共 {len(plan)} 项)"
          + ("" if args.yes else " [dry-run, 加 -y 执行]"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
