#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录配额监视器（quota-watch）

用途：
    统计目标目录树的总大小（仅普通文件的数据量，不含目录项等元数据开销），
    与配额阈值比较并给出结论：
      总大小 >  配额             → stderr 输出 "OVER QUOTA ..." 警告，退出码 2；
      总大小 >= 配额 × --warn%   → 提示"接近配额"，退出码 0；
      其他                       → 输出 OK，退出码 0。
    非零退出码便于 shell / CI / 计划任务脚本直接判断集成，例如：
      python quota-watch.py ./data --quota 500MB || echo 超配额

示例命令：
    python quota-watch.py D:/backup --quota 10GB
    python quota-watch.py ./logs --quota 100MB --warn 50
    python quota-watch.py C:/Users/me/Downloads --quota 1GB --json

退出码：0 正常或接近配额；2 超过配额；1 参数/路径错误。
（注意：argparse 用法错误时默认也以退出码 2 结束，但不会输出 OVER QUOTA，
 脚本可按 stderr 中的 OVER QUOTA 字样或配合 --json 判断。）
"""

import argparse
import json
import os
import re
import stat
import sys

_SIZE_UNITS = {"": 1, "B": 1, "K": 1024, "KB": 1024, "M": 1024 ** 2, "MB": 1024 ** 2,
               "G": 1024 ** 3, "GB": 1024 ** 3, "T": 1024 ** 4, "TB": 1024 ** 4}


def parse_size(text):
    """'4096' / '1MB' / '512k' -> 字节数；无法解析时抛 ValueError。"""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([BKMGT]?)B?", text.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f"无法解析大小：{text!r}")
    return int(float(m.group(1)) * _SIZE_UNITS[m.group(2).upper()])


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.2f} {unit}"
        n /= 1024.0


def dir_size(root):
    """返回 (总字节数, 文件数, 跳过数)。"""
    total = nfiles = skipped = 0

    def walk_error(_err):
        nonlocal skipped
        skipped += 1

    for dirpath, dirnames, filenames in os.walk(root, onerror=walk_error):
        dirnames.sort()
        for name in sorted(filenames):
            try:
                st = os.lstat(os.path.join(dirpath, name))
            except OSError:
                skipped += 1
                continue
            if stat.S_ISREG(st.st_mode):
                total += st.st_size
                nfiles += 1
    return total, nfiles, skipped


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="quota-watch",
        description="检查目录是否超过配额阈值，超限输出警告并以非零退出码退出。")
    parser.add_argument("path", help="要检查的目录")
    parser.add_argument("--quota", required=True, metavar="SIZE",
                        help="配额上限，支持 500MB / 10GB / 1073741824 等写法")
    parser.add_argument("--warn", type=float, default=80.0, metavar="PCT",
                        help="接近配额的告警百分比（默认 80）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    root = args.path
    if not os.path.isdir(root):
        print(f"错误：{root} 不是有效目录", file=sys.stderr)
        return 1
    try:
        quota = parse_size(args.quota)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    if quota <= 0 or not (0 < args.warn <= 100):
        print("错误：--quota 必须为正数，--warn 须在 (0, 100] 内", file=sys.stderr)
        return 1

    total, nfiles, skipped = dir_size(root)
    pct = (total / quota * 100.0) if quota else 0.0
    over = total > quota
    near = (not over) and pct >= args.warn
    status = "OVER QUOTA" if over else ("NEAR QUOTA" if near else "OK")

    if args.json:
        print(json.dumps({
            "root": os.path.abspath(root),
            "used_bytes": total, "files": nfiles, "skipped": skipped,
            "quota_bytes": quota, "used_percent": round(pct, 2),
            "warn_percent": args.warn, "status": status,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"目录   : {os.path.abspath(root)}")
        print(f"已用   : {human(total)}（{nfiles} 个文件，跳过 {skipped} 处不可读）")
        print(f"配额   : {human(quota)}（告警线 {args.warn:.0f}%）")
        print(f"使用率 : {pct:.1f}%  [{status}]")

    if over:
        print(f"OVER QUOTA: {os.path.abspath(root)} 已用 {human(total)}，"
              f"超过配额 {human(quota)}（{pct:.1f}%）", file=sys.stderr)
    elif near:
        print(f"接近配额：已用 {pct:.1f}%，达到告警线 {args.warn:.0f}%。")
    else:
        print("OK：配额充足。")
    return 2 if over else 0


if __name__ == "__main__":
    sys.exit(main())
