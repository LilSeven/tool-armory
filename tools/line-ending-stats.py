#!/usr/bin/env python3
"""line-ending-stats.py —— 换行符统计器

用途:
    统计文件或目录中 CRLF(\\r\\n) / LF(\\n) / 独立 CR(\\r) 三种换行符的使用
    与混用情况; 同一文件中出现两种及以上换行符时判定为 MIXED(混杂), 并列出
    这些问题文件, 便于跨平台协作时排查换行符不一致。

示例命令:
    python line-ending-stats.py src/ -r                      # 递归统计整个目录
    python line-ending-stats.py a.txt b.py -v                # 指定文件, 列出全部明细
    python line-ending-stats.py . -r --include "*.py" --include "*.md"
    python line-ending-stats.py . -r --fail-on-mixed         # 发现混杂文件时退出码 2

说明:
    - 含 NUL 字节的文件视为二进制, 跳过判定并单独计数。
    - 独立 CR 是经典 Mac OS (pre-OSX) 的换行风格。
    - 退出码: 0=正常完成; 1=存在错误(路径不存在/不可读); 2=--fail-on-mixed
      且发现混杂文件。
仅用 Python 标准库。
"""

import argparse
import fnmatch
import os
import sys

CHUNK_SIZE = 1 << 20  # 1 MiB
CLASS_ORDER = ("CRLF", "LF", "CR", "MIXED", "none")


def count_line_endings(path):
    """Count line terminators chunk by chunk.

    Returns (crlf, lone_lf, lone_cr, has_nul).
    """
    crlf = lf = cr = 0
    pending_cr = False
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            if b"\x00" in chunk:
                return 0, 0, 0, True
            if pending_cr:
                pending_cr = False
                if chunk[:1] == b"\n":
                    # 上一块末尾的 \r 与本块开头的 \n 其实是一对 CRLF
                    crlf += 1
                    cr -= 1
                    lf -= 1
            n = chunk.count(b"\r\n")
            crlf += n
            cr += chunk.count(b"\r") - n
            lf += chunk.count(b"\n") - n
            pending_cr = chunk.endswith(b"\r")
    return crlf, lf, cr, False


def classify(crlf, lf, cr):
    kinds = sum(1 for n in (crlf, lf, cr) if n)
    if kinds == 0:
        return "none"
    if kinds == 1:
        return "CRLF" if crlf else ("LF" if lf else "CR")
    return "MIXED"


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


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="line-ending-stats.py",
        description="Count CRLF/LF/CR usage per file and flag files with mixed line endings.")
    parser.add_argument("paths", nargs="+", metavar="PATH",
                        help="file or directory (directories need -r to recurse)")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="recurse into subdirectories")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB",
                        help="only process files whose name matches GLOB (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="skip files/dirs whose name matches GLOB (repeatable)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="list every text file (default: only MIXED ones)")
    parser.add_argument("--fail-on-mixed", action="store_true",
                        help="exit with code 2 when mixed-ending files are found")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    files, missing = discover(args.paths, args.recursive, args.include, args.exclude)
    errors = 0
    for p in missing:
        print("error: path not found: %s" % p, file=sys.stderr)
        errors += 1

    class_counts = dict.fromkeys(CLASS_ORDER, 0)
    tot_crlf = tot_lf = tot_cr = 0
    n_binary = 0
    mixed_files = []

    for path in files:
        try:
            crlf, lf, cr, has_nul = count_line_endings(path)
        except OSError as exc:
            print("error: cannot read %s: %s" % (path, exc), file=sys.stderr)
            errors += 1
            continue
        if has_nul:
            n_binary += 1
            if args.verbose:
                print("%-5s %-22s %s" % ("BIN", "-", path))
            continue
        cls = classify(crlf, lf, cr)
        class_counts[cls] += 1
        tot_crlf += crlf
        tot_lf += lf
        tot_cr += cr
        if cls == "MIXED":
            mixed_files.append(path)
        if args.verbose or cls == "MIXED":
            print("%-5s crlf=%-7d lf=%-7d cr=%-5d %s" % (cls, crlf, lf, cr, path))

    print("-" * 64)
    print("text files: %d (CRLF=%d LF=%d CR=%d MIXED=%d none=%d) | "
          "binary skipped: %d | errors: %d"
          % (sum(class_counts.values()), class_counts["CRLF"], class_counts["LF"],
             class_counts["CR"], class_counts["MIXED"], class_counts["none"],
             n_binary, errors))
    print("terminator totals: CRLF=%d lone-LF=%d lone-CR=%d"
          % (tot_crlf, tot_lf, tot_cr))
    if mixed_files:
        print("files with mixed line endings (%d):" % len(mixed_files))
        for p in mixed_files:
            print("  - %s" % p)
    else:
        print("files with mixed line endings: none")

    if errors:
        return 1
    if args.fail_on_mixed and mixed_files:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
