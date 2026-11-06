#!/usr/bin/env python3
"""hex-head-dump.py —— 文件头十六进制查看器

用途:
    批量输出文件开头若干字节的十六进制转储(仿 hexdump -C 格式: 偏移量 +
    十六进制 + ASCII 预览), 辅助人工识别未知文件格式(魔数/文件头)。

示例命令:
    python hex-head-dump.py unknown.bin                  # 默认显示前 64 字节
    python hex-head-dump.py a.bin b.img -n 128           # 指定文件, 前 128 字节
    python hex-head-dump.py ./samples -r -n 32           # 递归目录, 每文件前 32 字节
    python hex-head-dump.py ./samples -r --include "*.bin" --width 8

说明:
    - 文件不足 -n 字节时输出全部内容; 空文件注明 (empty)。
    - 每行: 8 位十六进制偏移 + 两个 8 字节十六进制组 + ASCII 预览(不可打印
      字符显示为 ".")。
    - 退出码: 0=全部成功; 1=有路径不存在或文件无法读取。
仅用 Python 标准库。
"""

import argparse
import fnmatch
import os
import sys


def discover(paths, recursive, includes, excludes):
    """Expand input paths into a flat, deterministic file list.

    Returns (files, missing).
    """
    files, missing = [], []
    seen = set()

    def wanted(path):
        name = os.path.basename(path)
        if excludes and any(fnmatch.fnmatch(name, pat) for pat in excludes):
            return False
        if includes and not any(fnmatch.fnmatch(name, pat) for pat in includes):
            return False
        return True

    for p in paths:
        key = os.path.abspath(p)
        if key in seen:
            continue
        seen.add(key)
        if os.path.isfile(p):
            if wanted(p):
                files.append(p)
        elif os.path.isdir(p):
            if recursive:
                for root, dirs, names in os.walk(p):
                    dirs[:] = sorted(
                        d for d in dirs
                        if not (excludes and any(fnmatch.fnmatch(d, pat) for pat in excludes))
                    )
                    for n in sorted(names):
                        fp = os.path.join(root, n)
                        if wanted(fp):
                            files.append(fp)
            else:
                for n in sorted(os.listdir(p)):
                    fp = os.path.join(p, n)
                    if os.path.isfile(fp) and wanted(fp):
                        files.append(fp)
        else:
            missing.append(p)
    return files, missing


def hexdump(data, width=16):
    """Return hexdump -C style lines for data (offsets start at 0)."""
    half = max(1, width // 2)
    lines = []
    for off in range(0, len(data), width):
        chunk = data[off:off + width]
        cells = ["%02x" % b for b in chunk]
        left = " ".join(cells[:half])
        right = " ".join(cells[half:])
        text = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in chunk)
        lines.append("%08x  %-*s  %-*s  |%s|"
                     % (off, half * 3 - 1, left, (width - half) * 3 - 1, right, text))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="hex-head-dump.py",
        description="Batch hex dump of the first N bytes of files "
                    "(magic-number / file-head inspection).")
    parser.add_argument("paths", nargs="+", metavar="PATH",
                        help="file or directory (use -r to recurse)")
    parser.add_argument("-n", "--bytes", type=int, default=64, metavar="N",
                        help="how many head bytes to dump per file (default: 64)")
    parser.add_argument("--width", type=int, default=16, metavar="W",
                        help="bytes per hex line (default: 16)")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="recurse into directories")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB",
                        help="only process files whose name matches GLOB (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="skip files/dirs whose name matches GLOB (repeatable)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    if args.bytes <= 0:
        parser.error("--bytes must be a positive integer")
    if args.width <= 0:
        parser.error("--width must be a positive integer")

    files, missing = discover(args.paths, args.recursive, args.include, args.exclude)
    errors = 0
    for p in missing:
        print("error: path not found: %s" % p, file=sys.stderr)
        errors += 1

    for path in files:
        try:
            with open(path, "rb") as fh:
                head = fh.read(args.bytes)
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
        except OSError as exc:
            print("error: cannot read %s: %s" % (path, exc), file=sys.stderr)
            errors += 1
            continue
        print("==> %s <==  (size=%d bytes, head=%d)" % (path, size, len(head)))
        if size == 0:
            print("(empty file)")
        for line in hexdump(head, args.width):
            print(line)
        print()

    if errors:
        print("done with %d error(s)" % errors, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
