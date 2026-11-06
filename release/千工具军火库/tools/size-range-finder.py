#!/usr/bin/env python3
r"""大小区间找文件（size-range-finder）—— 找出大小落在指定区间的文件。

按文件大小过滤整棵目录树：只给下限可找 100MB 以上的大文件，只给上限
可找 1KB 以下的碎文件，两者都给可圈定区间（如 1MB–10MB）。默认按大小
从大到小输出，便于快速定位占用空间的大户。

用法:
    python size-range-finder.py <目录> [选项]

示例:
    python size-range-finder.py D:\ --min 100MB
    python size-range-finder.py D:\tmp --max 1KB
    python size-range-finder.py . --min 1MB --max 10MB --top 20

选项:
    --min SIZE            最小大小（含），如 100MB
    --max SIZE            最大大小（含），如 1KB
    --sort size|path|name 排序方式，默认 size（从大到小）
    --top N               只显示排序后的前 N 个，默认全部

说明: 大小后缀 B/KB/MB/GB/TB 按 1KB=1024B 换算，纯数字为字节。
退出码: 0 正常（包括无匹配文件）；2 参数错误或目录不存在。
统计行输出到 stderr。
"""

import argparse
import os
import re
import sys

UNITS = {
    "": 1, "B": 1,
    "K": 1024, "KB": 1024, "KIB": 1024,
    "M": 1024 ** 2, "MB": 1024 ** 2, "MIB": 1024 ** 2,
    "G": 1024 ** 3, "GB": 1024 ** 3, "GIB": 1024 ** 3,
    "T": 1024 ** 4, "TB": 1024 ** 4, "TIB": 1024 ** 4,
}


def parse_size(text):
    """把 '100MB' 这类大小描述换算成字节数；无法识别时抛 ValueError。"""
    s = str(text).strip().upper().replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([A-Z]*)", s)
    if not m or m.group(2) not in UNITS:
        raise ValueError("无法识别的大小 %r（示例: 512KB、100MB、2GB）" % text)
    return int(float(m.group(1)) * UNITS[m.group(2)])


def size_arg(text):
    try:
        return parse_size(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def human_size(num):
    """字节数 → 人类可读大小，如 49B、200.0KB、1.5MB。"""
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return "%dB" % num if unit == "B" else "%.1f%s" % (num, unit)
        num /= 1024.0


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="找出大小落在指定区间的全部文件。")
    parser.add_argument("root", help="要扫描的起始目录")
    parser.add_argument("--min", dest="min_size", type=size_arg, default=None,
                        metavar="SIZE", help="最小大小（含）")
    parser.add_argument("--max", dest="max_size", type=size_arg, default=None,
                        metavar="SIZE", help="最大大小（含）")
    parser.add_argument("--sort", choices=("size", "path", "name"),
                        default="size", help="排序方式，默认 size 从大到小")
    parser.add_argument("--top", type=int, default=0, metavar="N",
                        help="只显示排序后的前 N 个，默认全部")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.root):
        parser.error("目录不存在或不是目录: %s" % args.root)
    if args.min_size is None and args.max_size is None:
        parser.error("至少需要指定 --min 或 --max 之一")
    if (args.min_size is not None and args.max_size is not None
            and args.min_size > args.max_size):
        parser.error("--min 不能大于 --max")

    matches = []
    walked = 0
    for dirpath, dirnames, filenames in os.walk(args.root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            try:
                size = os.lstat(path).st_size
            except OSError:
                continue
            walked += 1
            if args.min_size is not None and size < args.min_size:
                continue
            if args.max_size is not None and size > args.max_size:
                continue
            matches.append((path, size))

    keys = {
        "size": lambda r: (-r[1], r[0]),
        "path": lambda r: (r[0].lower(), r[0]),
        "name": lambda r: (os.path.basename(r[0]).lower(), r[0]),
    }
    matches.sort(key=keys[args.sort])
    shown = matches if args.top <= 0 else matches[:args.top]
    for path, size in shown:
        print("%10s  %s" % (human_size(size), path))
    total = sum(s for _p, s in matches)
    print("扫描 %d 个文件，命中 %d 个，合计 %s。"
          % (walked, len(matches), human_size(total)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
