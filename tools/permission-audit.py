#!/usr/bin/env python3
"""permission-audit.py —— 文件权限审计

用途:
    统计文件权限分布(八进制模式直方图; 可执行 / 只读 / 组可写 / 他人可写
    的数量), 并标记权限异常(风险)的文件:
        world-writable(其他人可写, o+w) 与 group-writable(组可写, g+w)。
    只读 / 可执行只计入分布, 不视为异常。

示例命令:
    python permission-audit.py ./bin -r              # 递归审计目录
    python permission-audit.py a.sh b.py -v          # 指定文件, 列出全部明细
    python permission-audit.py ./bin -r --strict     # 有风险文件时退出码 2

平台说明:
    - POSIX: st_mode 即真实权限位, 上述规则完全适用。
    - Windows: NTFS 通过 st_mode 只能体现 只读(0444)/可写(0666), 组/他人
      可写位是合成值, 因此 Windows 上自动跳过这两类规则并打印提示。
    - 退出码: 0=正常完成; 1=存在错误(路径不存在等); 2=--strict 且发现风险文件。
仅用 Python 标准库。
"""

import argparse
import fnmatch
import os
import stat
import sys


def ls_mode(mode):
    """Render the low 9 permission bits ls-l style, e.g. rw-r--r--."""
    out = ""
    for shift in (6, 3, 0):
        t = (mode >> shift) & 7
        out += ("r" if t & 4 else "-") + ("w" if t & 2 else "-") + ("x" if t & 1 else "-")
    return out


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
        prog="permission-audit.py",
        description="Audit file permission bits: distribution summary plus "
                    "world/group-writable risk flags.")
    parser.add_argument("paths", nargs="+", metavar="PATH",
                        help="file or directory (use -r to recurse)")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="recurse into subdirectories")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB",
                        help="only process files whose name matches GLOB (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="skip files/dirs whose name matches GLOB (repeatable)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="list every audited file with its mode")
    parser.add_argument("--strict", action="store_true",
                        help="exit with code 2 when risky files are found")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    is_windows = os.name == "nt"
    check_go = not is_windows  # group/other-writable 规则仅在 POSIX 上有意义

    files, missing = discover(args.paths, args.recursive, args.include, args.exclude)
    errors = 0
    for p in missing:
        print("error: path not found: %s" % p, file=sys.stderr)
        errors += 1

    hist = {}
    n_exec = n_ro = n_gw = n_ww = 0
    risky = []
    rows = []
    for path in files:
        try:
            st = os.stat(path)
        except OSError as exc:
            print("error: cannot stat %s: %s" % (path, exc), file=sys.stderr)
            errors += 1
            continue
        mode = stat.S_IMODE(st.st_mode)
        flags = []
        if mode & 0o111:
            flags.append("executable")
        if not (mode & 0o222):
            flags.append("read-only")
        if check_go:
            if mode & 0o002:
                flags.append("world-writable")
            if mode & 0o020:
                flags.append("group-writable")
        rflags = [f for f in flags if f in ("world-writable", "group-writable")]
        hist[mode] = hist.get(mode, 0) + 1
        if mode & 0o111:
            n_exec += 1
        if not (mode & 0o222):
            n_ro += 1
        if check_go:
            if mode & 0o002:
                n_ww += 1
            if mode & 0o020:
                n_gw += 1
        if rflags:
            risky.append((path, mode, rflags))
        rows.append((path, mode, flags))

    if args.verbose:
        for path, mode, flags in rows:
            tag = ("  flags: " + ",".join(flags)) if flags else ""
            print("%s (0%o)  %s%s" % (ls_mode(mode), mode, path, tag))

    print("-" * 64)
    print("files audited: %d | errors: %d" % (len(rows), errors))
    gw_txt = str(n_gw) if check_go else "n/a"
    ww_txt = str(n_ww) if check_go else "n/a"
    print("executable: %d | read-only: %d | group-writable: %s | world-writable: %s"
          % (n_exec, n_ro, gw_txt, ww_txt))
    print("mode histogram (octal): %s"
          % ("  ".join("0%o x%d" % (m, c) for m, c in sorted(hist.items())) or "(none)"))
    if is_windows:
        print("note: Windows st_mode only distinguishes read-only(0444) vs "
              "writable(0666); group/other-writable bits are synthetic, "
              "those rules were skipped.")
    if risky:
        print("RISKY files (world/group-writable): %d" % len(risky))
        for path, mode, rflags in risky:
            print("  - %s  %s (0%o)  %s" % (path, ",".join(rflags), mode, ls_mode(mode)))
    else:
        print("risky files (world/group-writable): none")

    if errors:
        return 1
    if args.strict and risky:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
