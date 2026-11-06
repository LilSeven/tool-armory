"""批量时间戳修改 —— 把一批文件的修改/访问时间设为指定时刻，或对齐到目录中最早/最晚文件。

用法:
    python touch-files.py <文件或目录...> [--atime | --mtime | --both] --time "<ISO时间>"
    python touch-files.py <文件或目录...> [--glob <模式>] --align earliest|latest
    python touch-files.py ... --dry-run

示例:
    python touch-files.py a.txt b.txt --time "2024-01-01 08:30:00"
    python touch-files.py ./src --glob "*.py" --align latest --mtime
    python touch-files.py ./logs --time "2024-06-01T12:00:00" --dry-run

说明:
    --time 接受 "YYYY-MM-DD HH:MM:SS"、"YYYY-MM-DDTHH:MM:SS" 或 "YYYY-MM-DD"（本地时间）。
    --align earliest 将所有文件对齐到集合中最早修改时间，latest 对齐到最晚。
    默认同时设置访问与修改时间；--atime / --mtime 只设其一。
    --dry-run 只列出将发生的变化。退出码 0 表示成功。
"""

import argparse
import datetime
import os
import sys


def parse_time(s):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt).timestamp()
        except ValueError:
            continue
    raise ValueError(f"无法解析时间: {s!r}")


def iter_files(targets, pattern):
    seen = set()
    files = []
    for t in targets:
        if os.path.isdir(t):
            for dirpath, _dirnames, filenames in os.walk(t):
                for fn in filenames:
                    if pattern is None or fnmatch_simple(fn, pattern):
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


def fnmatch_simple(name, pattern):
    import fnmatch
    return fnmatch.fnmatch(name, pattern)


def fmt_ts(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def main(argv=None):
    p = argparse.ArgumentParser(description="批量设置/对齐文件时间戳")
    p.add_argument("targets", nargs="+", help="文件或目录")
    p.add_argument("--time", default=None, help="目标时间，本地时间")
    p.add_argument("--align", choices=["earliest", "latest"], default=None,
                   help="对齐到集合中最早/最晚的修改时间")
    p.add_argument("--glob", dest="pattern", default=None, help="目录模式下文件名过滤")
    p.add_argument("--atime", action="store_true", help="只设置访问时间")
    p.add_argument("--mtime", action="store_true", help="只设置修改时间")
    p.add_argument("--dry-run", action="store_true", help="只列出变化，不修改")
    args = p.parse_args(argv)

    if bool(args.time) == bool(args.align):
        print("错误: --time 与 --align 必须且只能提供一个。", file=sys.stderr)
        return 2

    files = iter_files(args.targets, args.pattern)
    if not files:
        print("没有匹配的文件。")
        return 0

    if args.time:
        try:
            target_ts = parse_time(args.time)
        except ValueError as e:
            print(f"错误: {e}", file=sys.stderr)
            return 2
        label = fmt_ts(target_ts)
    else:
        mtimes = {f: os.stat(f).st_mtime for f in files}
        pick = min if args.align == "earliest" else max
        ref = pick(mtimes, key=mtimes.get)
        target_ts = mtimes[ref]
        label = f"{args.align} ({ref} @ {fmt_ts(target_ts)})"

    set_atime = not args.mtime or args.atime
    set_mtime = not args.atime or args.mtime

    print(f"目标时间: {label}" + (" [dry-run]" if args.dry_run else ""))
    changed = 0
    for f in files:
        st = os.stat(f)
        new_atime = target_ts if set_atime else st.st_atime
        new_mtime = target_ts if set_mtime else st.st_mtime
        if abs(new_atime - st.st_atime) < 1e-6 and abs(new_mtime - st.st_mtime) < 1e-6:
            print(f"跳过（无变化）: {f}")
            continue
        old = f"a={fmt_ts(st.st_atime)} m={fmt_ts(st.st_mtime)}"
        new = f"a={fmt_ts(new_atime)} m={fmt_ts(new_mtime)}"
        print(f"{f}: {old} -> {new}")
        if not args.dry_run:
            os.utime(f, (new_atime, new_mtime))
        changed += 1
    print(f"共处理 {changed} 个文件" + ("（dry-run，未实际修改）" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
