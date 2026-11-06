#!/usr/bin/env python3
r"""递归内容搜索（content-grep-lite）—— 在目录树的文本文件中按正则查找。

递归遍历目录，对文本文件逐行做正则匹配，结果以 `文件:行号:内容` 的形式
输出，适合快速定位配置项、日志关键字或代码片段。自动跳过二进制文件
（开头 8KB 含 NUL 字节）和超过 --max-size 的文件；编码默认 auto，
依次尝试 UTF-8 → GBK → Latin-1。

用法:
    python content-grep-lite.py <目录> <正则> [选项]

示例:
    python content-grep-lite.py D:\logs "ERROR\s+\d+"
    python content-grep-lite.py . "TODO" --include "*.py" --ignore-case
    python content-grep-lite.py . "配置" --encoding gbk --max-size 4MB

选项:
    -i, --ignore-case     忽略大小写
    --include GLOB        只搜索文件名匹配该通配符的文件（可多次指定）
    --exclude GLOB        跳过文件名匹配该通配符的文件（可多次指定）
    --encoding NAME       文件编码，默认 auto（utf-8 → gbk → latin-1）
    --max-size SIZE       跳过超过该大小的文件，默认 8MB（如 4MB、512KB）

说明: 统计行输出到 stderr，stdout 只含 `文件:行号:内容` 结果，便于管道。
退出码: 0 正常（包括无匹配）；2 参数错误、正则无效或目录不存在。
"""

import argparse
import codecs
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
DEFAULT_MAX_SIZE = 8 * 1024 * 1024


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


def decode(data, encoding):
    """按指定编码解码字节串；auto 依次尝试 utf-8 / gbk / latin-1。"""
    if encoding != "auto":
        return data.decode(encoding, errors="replace")
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="在目录树的文本文件中按正则搜索，输出 文件:行号:内容。")
    parser.add_argument("root", help="要搜索的起始目录")
    parser.add_argument("pattern", help="Python 正则表达式")
    parser.add_argument("-i", "--ignore-case", action="store_true",
                        help="忽略大小写")
    parser.add_argument("--include", action="append", default=[],
                        metavar="GLOB", help="只搜索文件名匹配的文件（可多次）")
    parser.add_argument("--exclude", action="append", default=[],
                        metavar="GLOB", help="跳过文件名匹配的文件（可多次）")
    parser.add_argument("--encoding", default="auto",
                        help="文件编码，默认 auto（utf-8 → gbk → latin-1）")
    parser.add_argument("--max-size", type=size_arg, default=DEFAULT_MAX_SIZE,
                        metavar="SIZE", help="跳过超过该大小的文件，默认 8MB")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.root):
        parser.error("目录不存在或不是目录: %s" % args.root)
    if args.encoding != "auto":
        try:
            codecs.lookup(args.encoding)
        except LookupError:
            parser.error("未知编码: %s" % args.encoding)
    try:
        pattern = re.compile(args.pattern,
                             re.IGNORECASE if args.ignore_case else 0)
    except re.error as exc:
        parser.error("无效正则 %r: %s" % (args.pattern, exc))

    matched_lines = 0
    text_files = 0
    skipped = 0
    for dirpath, dirnames, filenames in os.walk(args.root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            if args.include and not any(fnmatch.fnmatch(name, g)
                                        for g in args.include):
                continue
            if args.exclude and any(fnmatch.fnmatch(name, g)
                                    for g in args.exclude):
                continue
            path = os.path.join(dirpath, name)
            try:
                if os.lstat(path).st_size > args.max_size:
                    skipped += 1
                    continue
                with open(path, "rb") as fh:
                    data = fh.read()
            except OSError:
                skipped += 1
                continue
            if b"\x00" in data[:8192]:  # 二进制文件，跳过
                skipped += 1
                continue
            text_files += 1
            text = decode(data, args.encoding)
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    matched_lines += 1
                    print("%s:%d:%s" % (path, lineno, line))
    print("已扫描 %d 个文本文件，命中 %d 行，跳过 %d 个文件。"
          % (text_files, matched_lines, skipped), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
