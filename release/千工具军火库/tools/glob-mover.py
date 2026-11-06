#!/usr/bin/env python3
"""模式批量移动复制：按 glob 通配符批量移动或复制文件到目标目录，目标重名时自动加序号防覆盖。

用途
    把匹配一个或多个 glob 模式的文件移动（--move）或复制（默认）到目标目录；
    若目标目录已存在同名文件，自动改名为 name_1.ext、name_2.ext …，绝不覆盖。

示例命令
    python glob-mover.py "*.log" -d backup/            # 复制所有 log 到 backup/
    python glob-mover.py "img/**/*.png" -d out --move  # 移动（含递归）png 到 out/
    python glob-mover.py "a.txt" "b.txt" -d dst/ -n    # 预演，只显示计划不执行

参数
    patterns   一个或多个 glob 通配符（支持 ** 递归）
    -d/--dest  目标目录（不存在则自动创建）
    --move     移动而非复制（默认复制）
    -n/--dry-run  预演：只打印将要执行的动作，不做任何改动
"""
import argparse
import glob
import os
import shutil
import sys

def unique_path(dest_dir, filename):
    """在 dest_dir 中为 filename 生成不冲突的路径；重名则加 _1.._999 序号。"""
    target = os.path.join(dest_dir, filename)
    if not os.path.exists(target):
        return target, False
    stem, ext = os.path.splitext(filename)
    for i in range(1, 1000):
        cand = os.path.join(dest_dir, "%s_%d%s" % (stem, i, ext))
        if not os.path.exists(cand):
            return cand, True
    return None, True

def main(argv=None):
    ap = argparse.ArgumentParser(description="按 glob 批量移动/复制文件，重名自动加序号")
    ap.add_argument("patterns", nargs="+", help="glob 通配符，如 *.log 或 dir/**/*.txt")
    ap.add_argument("-d", "--dest", required=True, help="目标目录")
    ap.add_argument("--move", action="store_true", help="移动文件（默认为复制）")
    ap.add_argument("-n", "--dry-run", action="store_true", help="预演模式，不实际执行")
    args = ap.parse_args(argv)

    dest_dir = args.dest
    if not args.dry_run:
        os.makedirs(dest_dir, exist_ok=True)

    files = []
    seen = set()
    for pat in args.patterns:
        for p in sorted(glob.glob(pat, recursive=True)):
            if os.path.isfile(p) and not os.path.islink(p):
                ap_ = os.path.abspath(p)
                if ap_ not in seen:
                    seen.add(ap_)
                    files.append(p)

    if not files:
        print("未匹配到任何文件。")
        return 0

    verb = "移动" if args.move else "复制"
    done = renamed = 0
    for src in files:
        target, was_renamed = unique_path(dest_dir, os.path.basename(src))
        if target is None:
            print("跳过（无法生成不冲突的文件名）: %s" % src)
            continue
        if was_renamed:
            renamed += 1
        display = os.path.basename(target)
        if args.dry_run:
            print("[预演] %s: %s -> %s%s" % (verb, src, target, "（重名，已加序号）" if was_renamed else ""))
        else:
            if args.move:
                shutil.move(src, target)
            else:
                shutil.copy2(src, target)
            print("%s: %s -> %s" % (verb, src, display))
        done += 1

    print("完成：%s %d 个文件（其中 %d 个因重名加了序号）%s"
          % (verb, done, renamed, "（预演，未实际执行）" if args.dry_run else ""))
    return 0

if __name__ == "__main__":
    sys.exit(main())
