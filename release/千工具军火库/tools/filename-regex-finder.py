#!/usr/bin/env python3
r"""文件名正则搜索（filename-regex-finder）—— 按正则或通配符在整棵树中查找文件名。

用正则表达式或 shell 通配符对文件名（不含目录部分）做匹配，并可附加
扩展名类型与大小区间过滤，快速定位散落在目录深处的文件。正则采用
search 语义（部分匹配）；Windows 下通配符匹配不区分大小写。

用法:
    python filename-regex-finder.py <目录> <模式> [选项]

示例:
    python filename-regex-finder.py D:\data "report.*\.xlsx"
    python filename-regex-finder.py D:\data "*.log" --type glob --min-size 10MB
    python filename-regex-finder.py . "^test_" --ext .py --ignore-case

选项:
    --type regex|glob     模式类型，默认 regex
    -i, --ignore-case     正则忽略大小写
    --ext .py,.txt        只保留这些扩展名（逗号分隔，带不带点均可）
    --min-size SIZE       最小大小（含），如 512KB、10MB
    --max-size SIZE       最大大小（含）
    --sort path|name|size 排序方式，默认 path（size 为从大到小）

说明: 大小后缀 B/KB/MB/GB/TB 按 1KB=1024B 换算，纯数字为字节。
退出码: 0 正常（包括无匹配）；2 参数错误、模式无效或目录不存在。
统计行输出到 stderr。
"""

import argparse
import fnmatch
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


def normalize_ext(text):
    text = text.strip().lower()
    return text if text.startswith(".") else "." + text


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="按正则或通配符在整棵树中查找文件名，支持类型与大小过滤。")
    parser.add_argument("root", help="要搜索的起始目录")
    parser.add_argument("pattern", help="文件名匹配模式（正则或通配符）")
    parser.add_argument("--type", dest="match_type", choices=("regex", "glob"),
                        default="regex", help="模式类型，默认 regex")
    parser.add_argument("-i", "--ignore-case", action="store_true",
                        help="正则忽略大小写")
    parser.add_argument("--ext", default="", metavar=".py,.txt",
                        help="只保留这些扩展名（逗号分隔）")
    parser.add_argument("--min-size", type=size_arg, default=None,
                        metavar="SIZE", help="最小大小（含）")
    parser.add_argument("--max-size", type=size_arg, default=None,
                        metavar="SIZE", help="最大大小（含）")
    parser.add_argument("--sort", choices=("path", "name", "size"),
                        default="path", help="排序方式，默认 path")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.root):
        parser.error("目录不存在或不是目录: %s" % args.root)

    regex = None
    if args.match_type == "regex":
        try:
            regex = re.compile(args.pattern,
                               re.IGNORECASE if args.ignore_case else 0)
        except re.error as exc:
            parser.error("无效正则 %r: %s" % (args.pattern, exc))
    exts = {normalize_ext(e) for e in args.ext.split(",") if e.strip()}
    if (args.min_size is not None and args.max_size is not None
            and args.min_size > args.max_size):
        parser.error("--min-size 不能大于 --max-size")

    matches = []
    for dirpath, dirnames, filenames in os.walk(args.root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            if args.match_type == "glob":
                if not fnmatch.fnmatch(name, args.pattern):
                    continue
            elif not regex.search(name):
                continue
            if exts and os.path.splitext(name)[1].lower() not in exts:
                continue
            path = os.path.join(dirpath, name)
            try:
                size = os.lstat(path).st_size
            except OSError:
                continue
            if args.min_size is not None and size < args.min_size:
                continue
            if args.max_size is not None and size > args.max_size:
                continue
            matches.append((path, size))

    keys = {
        "path": lambda r: (r[0].lower(), r[0]),
        "name": lambda r: (os.path.basename(r[0]).lower(), r[0]),
        "size": lambda r: (-r[1], r[0]),
    }
    matches.sort(key=keys[args.sort])
    for path, size in matches:
        print("%10s  %s" % (human_size(size), path))
    print("命中 %d 个文件。" % len(matches), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
