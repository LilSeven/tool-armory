#!/usr/bin/env python3
"""归档轮换清理：按数量或保留天数把旧文件移入归档目录或删除（如日志只留最近 10 份），支持预演。

用途
    对目录中的旧文件做轮换：--keep-count 按数量保留最新 N 份，或 --keep-days
    按修改时间保留最近 D 天内的文件；超出的文件移动到归档目录（--archive）
    或直接删除（--delete）。默认 --dry-run 预演，确认后加 --apply 才真正执行。

示例命令
    python archive-rotator.py logs/ --keep-count 10 -a archive/          # 预演：留最近10份
    python archive-rotator.py logs/ --keep-count 10 -a archive/ --apply  # 实际执行
    python archive-rotator.py tmp/ --keep-days 30 --delete --apply       # 删除30天前文件
    python archive-rotator.py logs/ --keep-count 5 -a arc/ -p "*.log"    # 只轮换 *.log

参数
    directory      目标目录
    --keep-count N 只保留最新 N 个文件（按修改时间排序）
    --keep-days D  只保留最近 D 天内修改的文件
    -a/--archive   归档目录（移走旧文件；与 --delete 二选一）
    --delete       直接删除旧文件（与 -a 二选一）
    -p/--pattern   文件名 glob 过滤（默认 *，只处理文件不处理子目录）
    --apply        实际执行；缺省为预演
"""
import argparse
import glob
import os
import shutil
import sys
import time

def collect(directory, pattern):
    out = []
    for p in sorted(glob.glob(os.path.join(directory, pattern))):
        if os.path.isfile(p) and not os.path.islink(p):
            out.append((os.path.getmtime(p), p))
    out.sort()  # 旧的在前
    return [p for _, p in out]

def main(argv=None):
    ap = argparse.ArgumentParser(description="按数量或天数轮换归档/删除旧文件，默认预演")
    ap.add_argument("directory", help="目标目录")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--keep-count", type=int, metavar="N", help="只保留最新 N 个文件")
    g.add_argument("--keep-days", type=int, metavar="D", help="只保留最近 D 天内修改的文件")
    g2 = ap.add_mutually_exclusive_group(required=True)
    g2.add_argument("-a", "--archive", metavar="DIR", help="旧文件移入该归档目录")
    g2.add_argument("--delete", action="store_true", help="直接删除旧文件")
    ap.add_argument("-p", "--pattern", default="*", help="文件名 glob（默认 *）")
    ap.add_argument("--apply", action="store_true", help="实际执行（缺省为预演）")
    args = ap.parse_args(argv)

    directory = args.directory
    if not os.path.isdir(directory):
        print("错误：目录不存在：%s" % directory)
        return 1
    if args.keep_count is not None and args.keep_count < 0:
        ap.error("--keep-count 不能为负数")
    if args.keep_days is not None and args.keep_days < 0:
        ap.error("--keep-days 不能为负数")

    files = collect(directory, args.pattern)
    stale = []
    if args.keep_count is not None:
        # collect 按修改时间升序（旧的在前），留下的最新 count 个在尾部
        stale = files[:max(len(files) - args.keep_count, 0)]
        rule = "按数量：保留最新 %d 个" % args.keep_count
    else:
        cutoff = time.time() - args.keep_days * 86400
        stale = [p for p in files if os.path.getmtime(p) < cutoff]
        rule = "按天数：保留最近 %d 天" % args.keep_days

    mode = "删除" if args.delete else "归档到 %s" % args.archive
    print("规则：%s；动作：%s；模式：%s" % (rule, mode, "执行" if args.apply else "预演"))
    if not stale:
        print("没有需要轮换的文件。")
        return 0

    if args.archive and args.apply:
        os.makedirs(args.archive, exist_ok=True)

    n_ok = 0
    for p in stale:
        age_days = (time.time() - os.path.getmtime(p)) / 86400
        if args.delete:
            print("  [删除] %s（%.1f 天前）" % (p, age_days))
            if args.apply:
                os.remove(p)
        else:
            target, renamed = unique_target(args.archive, os.path.basename(p))
            print("  [归档] %s -> %s（%.1f 天前）%s"
                  % (p, target, age_days, "（重名加序号）" if renamed else ""))
            if args.apply:
                shutil.move(p, target)
        n_ok += 1

    print("完成：处理 %d 个旧文件%s" % (n_ok, "" if args.apply else "（预演，未实际改动）"))
    return 0

def unique_target(dest_dir, filename):
    target = os.path.join(dest_dir, filename)
    if not os.path.exists(target):
        return target, False
    stem, ext = os.path.splitext(filename)
    for i in range(1, 1000):
        cand = os.path.join(dest_dir, "%s_%d%s" % (stem, i, ext))
        if not os.path.exists(cand):
            return cand, True
    return None, True

if __name__ == "__main__":
    sys.exit(main())
