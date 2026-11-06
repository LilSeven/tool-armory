#!/usr/bin/env python3
"""按扩展名归类：把目录中的文件移动到以其扩展名命名的子目录（如 jpg/、pdf/）。

用法:
  python move-by-ext.py <目录> [--map "jpg,jpeg=images:png=images:txt=docs"] [--ext a,b,c]
                       [--dry-run] [--recursive]

选项:
  --map    自定义扩展名分组映射，格式 ext1,ext2=分组:ext3=分组
           （未映射的扩展名仍用扩展名本身作为子目录名）
  --ext    只处理这些扩展名（逗号分隔，大小写不敏感），默认全部
  --dry-run  预演模式，只打印将要执行的操作，不实际移动
  --recursive 递归处理子目录（移动后仍会留在各自位置创建分组子目录）

说明:
  - 无扩展名文件默认归入 "noext" 子目录
  - 目标重名时自动追加序号 (name_1.txt)

示例命令:
  python move-by-ext.py D:/Downloads --dry-run
  python move-by-ext.py D:/Downloads --map "jpg,jpeg=images:png=images"
"""

import argparse
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
    ap = argparse.ArgumentParser(description="按扩展名把文件移动到同名子目录")
    ap.add_argument("directory", help="目标目录")
    ap.add_argument("--map", dest="ext_map", default="",
                    help='扩展名分组映射, 如 "jpg,jpeg=images:png=images"')
    ap.add_argument("--ext", default="", help="只处理这些扩展名(逗号分隔)")
    ap.add_argument("--recursive", action="store_true", help="递归处理子目录")
    ap.add_argument("--dry-run", action="store_true", help="预演，不实际移动")
    args = ap.parse_args(argv)

    base = os.path.abspath(args.directory)
    if not os.path.isdir(base):
        print(f"错误: 目录不存在: {base}", file=sys.stderr)
        return 2

    # 解析映射: {".jpg": "images", ".jpeg": "images", ...}
    mapping = {}
    for item in args.ext_map.split(":"):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            print(f"错误: --map 片段缺少 '=': {item}", file=sys.stderr)
            return 2
        exts, group = item.split("=", 1)
        for e in exts.split(","):
            e = e.strip().lower().lstrip(".")
            if e:
                mapping[e] = group.strip() or e

    only_exts = {e.strip().lower().lstrip(".")
                 for e in args.ext.split(",") if e.strip()}

    moved = skipped = 0
    roots = [base]
    if args.recursive:
        for dirpath, dirnames, _ in os.walk(base):
            dirnames[:] = [d for d in dirnames]  # 遍历全部
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
            ext = os.path.splitext(name)[1].lower().lstrip(".")
            group = ext if ext else "noext"
            if not ext:
                pass  # 保持 group=noext
            elif ext in mapping:
                group = mapping[ext]
            if only_exts and ext not in only_exts:
                skipped += 1
                continue
            dst_dir = os.path.join(dirpath, group)
            if os.path.exists(dst_dir) and not os.path.isdir(dst_dir):
                # 组目录名被同名文件占用，退避为 <组名>_files
                dst_dir = os.path.join(dirpath, group + "_files")
            dst = unique_target(os.path.join(dst_dir, name))
            if os.path.abspath(src) == os.path.abspath(dst):
                continue
            print(f"{'[预演] ' if args.dry_run else ''}{src} -> {dst}")
            if not args.dry_run:
                os.makedirs(dst_dir, exist_ok=True)
                shutil.move(src, dst)
            moved += 1

    verb = "将移动" if args.dry_run else "已移动"
    print(f"{verb} {moved} 个文件，跳过 {skipped} 个（扩展名不在 --ext 范围内）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
