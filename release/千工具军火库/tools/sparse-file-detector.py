#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""稀疏文件检测器（sparse-file-detector）

用途：
    比较每个文件的"逻辑大小"与"磁盘实际占用"，物理占用明显小于逻辑大小的文件
    即为疑似稀疏文件（NTFS 压缩文件也会命中），并估算单文件与整体的节约量。

磁盘实际占用取值（等价于 Unix 的 st_blocks * 512）：
    1) Unix：os.stat().st_blocks * 512；
    2) Windows：GetFileInformationByHandleEx(FileStandardInfo).AllocationSize
       （Windows 的 os.stat 不提供 st_blocks；该值为真实磁盘占用，
       稀疏文件的空洞已扣除，会小于逻辑大小），失败退回 GetCompressedFileSizeW；
    3) 都不可用的文件记为"无法判定"并跳过。

判定规则：逻辑大小 >= --min-size 且 0 < (逻辑 - 物理) 且差值 >= --min-savings。

示例命令：
    python sparse-file-detector.py D:/vm-images
    python sparse-file-detector.py C:/Users/me --min-size 1MB --min-savings 64KB
    python sparse-file-detector.py ./data --top 20 --json

退出码：0 正常完成；1 参数或路径错误。
"""

import argparse
import ctypes
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


def _load_kernel32():
    if os.name != "nt":
        return None
    try:
        k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        k32.CreateFileW.restype = ctypes.c_void_p
        k32.GetCompressedFileSizeW.restype = ctypes.c_ulong
        k32.GetFileAttributesW.restype = ctypes.c_ulong
        return k32
    except OSError:
        return None


_K32 = _load_kernel32()


class _FileStandardInfo(ctypes.Structure):
    _fields_ = [("AllocationSize", ctypes.c_longlong),
                ("EndOfFile", ctypes.c_longlong),
                ("NumberOfLinks", ctypes.c_ulong),
                ("DeletePending", ctypes.c_ubyte),
                ("Directory", ctypes.c_ubyte)]


def win_alloc_size(path):
    """Windows：FileStandardInfo.AllocationSize（真实磁盘占用），失败返回 None。"""
    if _K32 is None:
        return None
    handle = _K32.CreateFileW(ctypes.c_wchar_p(path), 0x80, 3, None, 3, 0, None)
    if handle and handle != ctypes.c_void_p(-1).value:   # FILE_READ_ATTRIBUTES
        try:
            info = _FileStandardInfo()
            if _K32.GetFileInformationByHandleEx(handle, 1, ctypes.byref(info),
                                                 ctypes.sizeof(info)):
                return info.AllocationSize
        finally:
            _K32.CloseHandle(handle)
    return None


def physical_size(st, path):
    """返回文件磁盘实际占用（字节）；无法判定返回 None。"""
    blocks = getattr(st, "st_blocks", None)
    if blocks is not None:                    # Unix：真实已分配块
        return blocks * 512
    if os.name == "nt" and _K32 is not None:
        got = win_alloc_size(path)
        if got is not None:
            return got
        high = ctypes.c_ulong(0)              # 兜底：GetCompressedFileSizeW
        low = _K32.GetCompressedFileSizeW(ctypes.c_wchar_p(path), ctypes.byref(high))
        if low == 0xFFFFFFFF and ctypes.get_last_error() != 0:
            return None
        return (high.value << 32) | low
    return None


def file_kind(path):
    """借助文件属性细分：稀疏 / 压缩 / 疑似稀疏 / 未知。"""
    if os.name != "nt" or _K32 is None:
        return "疑似稀疏"
    attrs = _K32.GetFileAttributesW(ctypes.c_wchar_p(path))
    if attrs == 0xFFFFFFFF:
        return "未知"
    if attrs & 0x200:          # FILE_ATTRIBUTE_SPARSE_FILE
        return "稀疏"
    if attrs & 0x800:          # FILE_ATTRIBUTE_COMPRESSED
        return "压缩"
    return "疑似稀疏"


def scan(root, min_size, min_savings):
    hits = []
    nfiles = nundecided = skipped = 0

    def walk_error(_err):
        nonlocal skipped
        skipped += 1

    for dirpath, dirnames, filenames in os.walk(root, onerror=walk_error):
        dirnames.sort()
        for name in sorted(filenames):
            p = os.path.join(dirpath, name)
            try:
                st = os.lstat(p)
            except OSError:
                skipped += 1
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            nfiles += 1
            if st.st_size < min_size:
                continue
            phys = physical_size(st, p)
            if phys is None:
                nundecided += 1
                continue
            savings = st.st_size - phys
            if savings > 0 and savings >= min_savings:
                hits.append({"path": p, "kind": file_kind(p),
                             "logical": st.st_size, "physical": phys,
                             "savings": savings})
    return hits, nfiles, nundecided, skipped


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="sparse-file-detector",
        description="比较文件逻辑大小与磁盘实际占用，找出疑似稀疏文件并估算节约量。")
    parser.add_argument("path", help="要扫描的目录")
    parser.add_argument("--min-size", default="4096", metavar="SIZE",
                        help="只检查逻辑大小不小于该值的文件（默认 4096）")
    parser.add_argument("--min-savings", default="4096", metavar="SIZE",
                        help="节约量达到该值才计入（默认 4096）")
    parser.add_argument("--top", type=int, default=20, metavar="N",
                        help="列出节约最多的前 N 个文件（默认 20）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.path):
        print(f"错误：{args.path} 不是有效目录", file=sys.stderr)
        return 1
    try:
        min_size = parse_size(args.min_size)
        min_savings = parse_size(args.min_savings)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    hits, nfiles, nundecided, skipped = scan(args.path, min_size, min_savings)
    hits.sort(key=lambda h: -h["savings"])
    top = hits[:max(0, args.top)]
    logical = sum(h["logical"] for h in hits)
    physical = sum(h["physical"] for h in hits)
    savings = logical - physical

    if args.json:
        print(json.dumps({
            "root": os.path.abspath(args.path),
            "files": nfiles, "undecided": nundecided, "skipped": skipped,
            "suspects": len(hits),
            "logical_bytes": logical, "physical_bytes": physical,
            "estimated_savings_bytes": savings,
            "top": top,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"扫描根      : {os.path.abspath(args.path)}")
    print(f"文件数      : {nfiles}（无法判定 {nundecided}，跳过 {skipped} 处不可读）")
    if not hits:
        print("未发现疑似稀疏文件。")
        return 0
    print(f"疑似稀疏文件: {len(hits)} 个")
    print(f"逻辑合计    : {human(logical)}   物理合计: {human(physical)}")
    pct = (savings / logical * 100.0) if logical else 0.0
    print(f"预计节约    : {human(savings)}（占逻辑的 {pct:.1f}%）")
    print()
    print(f"节约最多的 {len(top)} 个：")
    print(f"{'节约':>12} {'逻辑':>12} {'物理':>12} {'占用率':>9}  类型      文件")
    for h in top:
        ratio = (h["physical"] / h["logical"] * 100.0) if h["logical"] else 0.0
        print(f"{human(h['savings']):>12} {human(h['logical']):>12} "
              f"{human(h['physical']):>12} {ratio:>8.1f}%  {h['kind']:<6}  {h['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
