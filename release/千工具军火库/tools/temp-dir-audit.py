#!/usr/bin/env python3
"""临时目录体检 (temp-dir-audit) —— 统计系统临时目录大小与最老文件年龄，评估可安全清理的空间。

用途:
    遍历系统临时目录（tempfile.gettempdir()，可用 --dir 覆盖）并统计:
      * 总大小（文件字节合计）、文件数、目录数、无法读取项数；
      * 最老文件的年龄（按 mtime 相对当前时间）；
      * “可安全清理”空间: mtime 早于 --days 天（默认 7）的文件大小/数量合计
        （仅为启发式估算，工具只读报告，不删除任何文件）。
    --top N 列出最大的 N 个文件；--json 输出机器可读结果。

示例命令:
    python temp-dir-audit.py                      # 体检系统临时目录
    python temp-dir-audit.py --dir /tmp/demo --days 1 --top 3
    python temp-dir-audit.py --json

只依赖 Python 标准库；只读统计，不删除、不修改任何文件。
"""

import argparse
import json
import os
import sys
import tempfile
import time


def _force_utf8_stdout():
    """管道/重定向场景下尽量以 UTF-8 输出，避免 Windows 默认码页导致乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (stream.encoding or "").lower().replace("-", "")
            if enc and enc != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def human(nbytes):
    """字节数 -> 人类可读字符串（KiB/MiB/GiB/TiB）。"""
    size = float(nbytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%.1f TiB" % size


def human_age(seconds):
    """秒数 -> 人类可读时长。"""
    seconds = max(float(seconds), 0.0)
    for unit, scale in (("秒", 60.0), ("分钟", 60.0), ("小时", 24.0)):
        if seconds < scale:
            return "%.0f %s" % (seconds, unit)
        seconds /= scale
    return "%.1f 天" % seconds


def scan(root, cleanable_before):
    """遍历 root 统计；mtime 早于 cleanable_before（epoch 秒）的文件计入可清理。"""
    error_count = [0]

    def on_error(_exc):
        error_count[0] += 1

    result = {"total_bytes": 0, "files": 0, "dirs": 0, "clean_bytes": 0,
              "clean_files": 0, "oldest_mtime": None, "oldest_path": None,
              "largest": []}
    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
        result["dirs"] += len(dirnames)
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                if os.path.islink(path):
                    continue  # 符号链接不重复计入
                st = os.stat(path)
            except OSError:
                error_count[0] += 1
                continue
            result["files"] += 1
            size = st.st_size
            mtime = st.st_mtime
            result["total_bytes"] += size
            result["largest"].append((size, path))
            if result["oldest_mtime"] is None or mtime < result["oldest_mtime"]:
                result["oldest_mtime"] = mtime
                result["oldest_path"] = path
            if mtime < cleanable_before:
                result["clean_bytes"] += size
                result["clean_files"] += 1
    result["largest"].sort(key=lambda t: t[0], reverse=True)
    result["errors"] = error_count[0]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="temp-dir-audit",
        description="临时目录体检：统计临时目录大小、最老文件年龄与可安全清理空间（只读）",
    )
    parser.add_argument("--dir", default=None, help="要体检的目录（默认为系统临时目录）")
    parser.add_argument("--days", type=float, default=7.0,
                        help="可清理判定: mtime 早于 N 天前（默认 7 天）")
    parser.add_argument("--top", type=int, default=5, help="列出最大的 N 个文件（默认 5）")
    parser.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)
    _force_utf8_stdout()

    root = os.path.abspath(args.dir) if args.dir else tempfile.gettempdir()
    if not os.path.isdir(root):
        print("目录不存在: %s" % root, file=sys.stderr)
        return 1

    now = time.time()
    result = scan(root, now - args.days * 86400.0)
    result["root"] = root
    result["clean_days"] = args.days
    result["oldest_age_seconds"] = (round(now - result["oldest_mtime"], 1)
                                    if result["oldest_mtime"] is not None else None)

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("目录      : %s" % result["root"])
    print("总大小    : %s (%d 个文件, %d 个子目录, 跳过 %d 个不可读项)"
          % (human(result["total_bytes"]), result["files"], result["dirs"], result["errors"]))
    if result["oldest_age_seconds"] is not None:
        print("最老文件  : %s 前  (%s)"
              % (human_age(result["oldest_age_seconds"]), result["oldest_path"]))
    else:
        print("最老文件  : (目录内没有文件)")
    if result["total_bytes"]:
        pct = result["clean_bytes"] * 100.0 / result["total_bytes"]
        print("可安全清理: %s (%d 个文件, 占 %.1f%%)  -- 按 mtime 早于 %.1f 天估算"
              % (human(result["clean_bytes"]), result["clean_files"], pct, args.days))
    if result["largest"] and args.top > 0:
        print("最大的 %d 个文件:" % min(args.top, len(result["largest"])))
        for size, path in result["largest"][:args.top]:
            print("  %10s  %s" % (human(size), path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
