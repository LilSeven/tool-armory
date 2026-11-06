#!/usr/bin/env python3
"""zip-integrity-test.py —— 压缩包完整性测试

用途:
    在给定目录(或文件列表)中找出压缩包, 用 zipfile / tarfile 逐包做完整性
    测试并列出坏包清单:
      - zip 类(zipfile.ZipFile.testzip): 逐成员解压并校验 CRC32;
      - tar 类(tarfile): 读取全部成员头, 并逐个成员解包读取数据,
        可发现 gzip/bzip2/xz 流截断与 CRC 错误。

示例命令:
    python zip-integrity-test.py ./archives                # 扫描目录(不递归)
    python zip-integrity-test.py ./archives -r             # 递归扫描
    python zip-integrity-test.py a.zip b.tar.gz            # 直接指定文件
    python zip-integrity-test.py ./archives -r --strict    # 有坏包时退出码 2

识别的扩展名:
    zip 类: .zip .jar .war .ear .whl .egg .apk .epub .docx .xlsx .pptx .odt
    tar 类: .tar .tar.gz .tgz .tar.bz2 .tbz2 .tbz .tar.xz .txz .tar.lzma .tlz

输出:
    每包一行 OK / BAD / UNVERIFIABLE(带密码或压缩算法不受支持, 无法自动校验),
    最后给出汇总并单独列出坏包清单。
    退出码: 0=扫描完成(无论是否发现坏包); 1=存在错误(路径不存在等);
            2=--strict 且发现坏包。
仅用 Python 标准库。
"""

import argparse
import fnmatch
import os
import sys
import tarfile
import zipfile

ZIP_EXTS = (".zip", ".jar", ".war", ".ear", ".whl", ".egg", ".apk",
            ".epub", ".docx", ".xlsx", ".pptx", ".odt")
TAR_EXTS = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tbz",
            ".tar.xz", ".txz", ".tar.lzma", ".tlz")


def archive_kind(name):
    low = os.path.basename(name).lower()
    for ext in TAR_EXTS:
        if low.endswith(ext):
            return "tar"
    for ext in ZIP_EXTS:
        if low.endswith(ext):
            return "zip"
    return None


def test_zip(path):
    """Return (ok, detail): ok=True good, False broken, None unverifiable."""
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if any(zi.flag_bits & 0x1 for zi in zf.infolist()):
            return None, "password-protected entries (%d)" % len(names)
        bad = zf.testzip()  # 逐成员解压并校验 CRC32
        if bad is not None:
            return False, "CRC error in member: %s" % bad
        return True, "%d member(s)" % len(names)


def test_tar(path):
    with tarfile.open(path, "r:*") as tf:
        members = tf.getmembers()
        for m in members:
            if not m.isreg():
                continue
            fh = tf.extractfile(m)
            if fh is None:
                continue
            while fh.read(1 << 20):
                pass
        return True, "%d member(s)" % len(members)


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
        prog="zip-integrity-test.py",
        description="Integrity-test archive files (zip/tar family) and list broken ones.")
    parser.add_argument("paths", nargs="+", metavar="PATH",
                        help="archive file(s) or a directory to scan (use -r to recurse)")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="recurse into subdirectories")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB",
                        help="additionally filter scanned files by GLOB (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="skip files/dirs whose name matches GLOB (repeatable)")
    parser.add_argument("--strict", action="store_true",
                        help="exit with code 2 when any BAD archive is found")
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

    tested = []
    ignored = 0
    for path in files:
        kind = archive_kind(path)
        if kind is None:
            ignored += 1
            continue
        try:
            if kind == "zip":
                ok, detail = test_zip(path)
            else:
                ok, detail = test_tar(path)
        except (RuntimeError, NotImplementedError) as exc:
            # unsupported compression method / feature => cannot verify
            ok, detail = None, str(exc)
        except Exception as exc:  # 坏包可能抛出各种异常, 统一按 BAD 处理
            ok, detail = False, "%s: %s" % (type(exc).__name__, exc)
        label = {True: "OK", False: "BAD", None: "UNVERIFIABLE"}[ok]
        tested.append((label, path, kind, detail))

    for label, path, kind, detail in tested:
        if label == "OK":
            print("%-12s %s (%s, %s)" % (label, path, kind, detail))
        else:
            print("%-12s %s (%s) -- %s" % (label, path, kind, detail))

    bad = [t for t in tested if t[0] == "BAD"]
    unver = sum(1 for t in tested if t[0] == "UNVERIFIABLE")
    print("-" * 64)
    print("archives tested: %d (OK=%d BAD=%d UNVERIFIABLE=%d) | "
          "ignored non-archive files: %d | errors: %d"
          % (len(tested), len(tested) - len(bad) - unver, len(bad), unver,
             ignored, errors))
    if bad:
        print("broken archives (%d):" % len(bad))
        for label, path, kind, detail in bad:
            print("  - %s (%s)" % (path, detail))
    else:
        print("broken archives: none")

    if errors:
        return 1
    if args.strict and bad:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
