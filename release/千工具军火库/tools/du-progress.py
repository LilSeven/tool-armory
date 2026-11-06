#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""du-progress — 带进度的大目录统计。

递归统计目录的总大小与文件/子目录数; 超大目录扫描时在 stderr 上实时刷新:
已扫描文件数(及总数)、吞吐速度(files/s 与 MiB/s)、预计剩余时间(ETA)。
汇总结果输出到 stdout, 进度输出到 stderr, 便于重定向且互不污染。

ETA 依赖一次快速预扫描(只列目录项、不读文件属性)得到文件总数,
可用 --no-eta 跳过预扫描改为单遍模式(无 ETA)。

示例:
    python -I du-progress.py D:\\data          # 实时进度 + 汇总
    python -I du-progress.py . --top 10        # 附加列出最大的 10 个文件
    python -I du-progress.py /var --no-eta     # 单遍扫描, 不做预扫描

退出码: 0 成功(个别无权限文件计入 errors); 1 目录不存在。
"""

import argparse
import heapq
import os
import sys
import time


def human(num, space=True):
    val = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if val < 1024 or unit == "PiB":
            if unit == "B":
                return ("%d" % int(val)) + (" " if space else "") + unit
            return ("%.1f" % val) + (" " if space else "") + unit
        val /= 1024.0


def iter_tree(root, on_file, on_dir, on_error):
    """os.scandir 迭代遍历, 不跟随符号链接; 逐文件回调 (path, size)。"""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = os.scandir(current)
        except OSError as exc:
            on_error(current, exc)
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        on_dir(entry.path)
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            size = entry.stat(follow_symlinks=False).st_size
                        except OSError as exc:
                            on_error(entry.path, exc)
                            continue
                        on_file(entry.path, size)
                except OSError as exc:
                    on_error(entry.path, exc)


def precount(root):
    """快速预扫描: 只数文件个数, 不读属性, 用于估算 ETA。"""
    count = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = os.scandir(current)
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        count += 1
                except OSError:
                    continue
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="du-progress",
        description="统计目录总大小, 大目录时实时显示已扫描文件数、吞吐速度与预计剩余时间。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python -I du-progress.py D:\\data --top 10")
    parser.add_argument("path", nargs="?", default=".",
                        help="要统计的目录 (默认当前目录)")
    parser.add_argument("--top", type=int, default=0, metavar="N",
                        help="汇总时列出最大的 N 个文件 (默认 0 不列)")
    parser.add_argument("--no-eta", action="store_true",
                        help="跳过预扫描, 单遍统计, 不显示预计剩余时间")
    parser.add_argument("--interval", type=float, default=0.2,
                        help="进度刷新间隔秒 (默认 0.2)")
    args = parser.parse_args(argv)

    root = args.path
    if not os.path.isdir(root):
        print("目录不存在: %s" % root, file=sys.stderr)
        return 1

    try:
        sys.stderr.reconfigure(errors="replace")
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    total_files = None if args.no_eta else precount(root)

    stats = {"files": 0, "dirs": 0, "size": 0, "errors": 0}
    top_heap = []
    start = time.perf_counter()
    last_draw = [0.0]

    def draw(force=False):
        now = time.perf_counter()
        if not force and now - last_draw[0] < args.interval:
            return
        last_draw[0] = now
        elapsed = now - start
        f_rate = stats["files"] / elapsed if elapsed > 0 else 0.0
        b_rate = stats["size"] / elapsed / 1048576.0 if elapsed > 0 else 0.0
        if total_files is not None:
            eta = (max(total_files - stats["files"], 0) / f_rate) if f_rate > 0 else None
            eta_text = ("%ds" % eta) if eta is not None else "--"
            done_text = "%d/%d" % (stats["files"], total_files)
        else:
            eta_text = "--"
            done_text = "%d" % stats["files"]
        line = ("\r[du] files=%s dirs=%d size=%s | %.0f files/s %.1f MiB/s"
                " | eta=%s err=%d   ") % (
            done_text, stats["dirs"], human(stats["size"], space=False),
            f_rate, b_rate, eta_text, stats["errors"])
        try:
            sys.stderr.write(line)
            sys.stderr.flush()
        except Exception:
            pass

    def on_file(path, size):
        stats["files"] += 1
        stats["size"] += size
        if args.top > 0:
            item = (size, path)
            if len(top_heap) < args.top:
                heapq.heappush(top_heap, item)
            elif size > top_heap[0][0]:
                heapq.heapreplace(top_heap, item)
        draw()

    def on_dir(path):
        stats["dirs"] += 1

    def on_error(path, exc):
        stats["errors"] += 1

    iter_tree(root, on_file, on_dir, on_error)
    draw(force=True)
    try:
        sys.stderr.write("\n")
    except Exception:
        pass

    elapsed = time.perf_counter() - start
    print("dir    : %s" % os.path.abspath(root))
    print("files  : %d   subdirs: %d   errors: %d" % (
        stats["files"], stats["dirs"], stats["errors"]))
    print("total  : %s (%d B)" % (human(stats["size"]), stats["size"]))
    if total_files is not None:
        print("eta-src: pre-scan counted %d file(s)" % total_files)
    print("elapsed: %.2fs   rate: %.0f files/s, %.1f MiB/s" % (
        elapsed,
        stats["files"] / elapsed if elapsed > 0 else 0.0,
        stats["size"] / elapsed / 1048576.0 if elapsed > 0 else 0.0))
    if args.top > 0 and top_heap:
        print("top %d file(s):" % len(top_heap))
        for size, path in sorted(top_heap, key=lambda it: (-it[0], it[1])):
            print("  %10s  %s" % (human(size), path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
