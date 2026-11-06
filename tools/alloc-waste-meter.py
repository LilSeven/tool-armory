#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""簇分配浪费计量器（alloc-waste-meter）

用途：
    文件在磁盘上按"分配簇（cluster / allocation unit）"整块分配：哪怕只写 1 字节，
    理论上也要占走一个完整簇。本工具按簇大小对每个文件向上取整得到"实际占用"，
    与逻辑大小相减得到尾簇浪费（内部碎片），并汇总整个目录树的浪费总量，
    用于量化"海量小文件"场景下被白白吃掉的空间。

两种计量模式：
    默认（簇分配模型）：实际占用 = ceil(逻辑大小 / 簇大小) * 簇大小。
        簇大小自动探测（Windows: GetDiskFreeSpaceW；Unix: os.statvfs().f_bsize），
        可用 --cluster 强制指定。
    --real（OS 实报模式）：优先用真实磁盘占用——Unix: st_blocks*512；
        Windows: GetFileInformationByHandleEx(FileStandardInfo).AllocationSize，
        失败退回 GetCompressedFileSizeW，再退回簇取整。
        注意：NTFS 会把小文件驻留进 MFT（不占簇），此模式下海量小文件的
        浪费会被系统性低估，这正是默认采用簇分配模型的原因。

示例命令：
    python alloc-waste-meter.py C:/Users/me/logs
    python alloc-waste-meter.py D:/data --top 20
    python alloc-waste-meter.py E:/photos --cluster 65536
    python alloc-waste-meter.py ./smallfiles --real
    python alloc-waste-meter.py ./smallfiles --json

退出码：0 正常完成；1 参数或路径错误。
"""

import argparse
import ctypes
import json
import os
import stat
import sys


def _utf8_stdio():
    """Windows 控制台/管道下强制 UTF-8，避免中文输出乱码或 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _load_kernel32():
    if os.name != "nt":
        return None
    try:
        k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        k32.CreateFileW.restype = ctypes.c_void_p
        k32.GetCompressedFileSizeW.restype = ctypes.c_ulong
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


def win_cluster_size(root):
    """root 为盘根目录（如 'C:/'）；返回该卷的簇大小（字节），失败返回 None。"""
    if _K32 is None:
        return None
    spc, bps = ctypes.c_ulong(), ctypes.c_ulong()
    nfree, ntotal = ctypes.c_ulong(), ctypes.c_ulong()
    if not _K32.GetDiskFreeSpaceW(ctypes.c_wchar_p(root), ctypes.byref(spc),
                                  ctypes.byref(bps), ctypes.byref(nfree),
                                  ctypes.byref(ntotal)):
        return None
    return spc.value * bps.value


def win_alloc_size(path):
    """Windows：FileStandardInfo.AllocationSize（含稀疏空洞效果），失败退回
    GetCompressedFileSizeW；两者都失败返回 None。"""
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
    high = ctypes.c_ulong(0)
    low = _K32.GetCompressedFileSizeW(ctypes.c_wchar_p(path), ctypes.byref(high))
    if low == 0xFFFFFFFF and ctypes.get_last_error() != 0:
        return None
    return (high.value << 32) | low


def volume_root(path):
    abspath = os.path.abspath(path)
    drive, _rest = os.path.splitdrive(abspath)
    if drive:
        return drive + os.sep
    return os.path.dirname(abspath) or "."


def guess_cluster_size(path):
    """尽力探测 path 所在卷的分配簇大小。"""
    if os.name == "nt":
        cs = win_cluster_size(volume_root(path))
        if cs:
            return cs
    try:
        bsize = os.statvfs(volume_root(path)).f_bsize
        if bsize and bsize >= 512:
            return bsize
    except (AttributeError, OSError):
        pass
    return 4096


def cluster_ceil(size, cluster):
    """按簇分配模型：实际占用 = ceil(size/cluster)*cluster。"""
    return -(-size // cluster) * cluster


def on_disk_size(st, path, cluster, real=False):
    """实际占用字节数。real=True 时优先用 OS 实报值，拿不到再退回簇取整。"""
    if real:
        blocks = getattr(st, "st_blocks", None)
        if blocks is not None:               # Unix：真实已分配块
            return blocks * 512
        if os.name == "nt":                  # Windows：真实 AllocationSize
            got = win_alloc_size(path)
            if got is not None:
                return got
    return cluster_ceil(st.st_size, cluster)


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.2f} {unit}"
        n /= 1024.0


def scan_tree(root, cluster, real=False):
    """返回 [(浪费, 实际占用, 逻辑大小, 路径), ...] 与跳过数。"""
    files = []
    skipped = 0

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
            od = on_disk_size(st, p, cluster, real)
            files.append((od - st.st_size, od, st.st_size, p))
    return files, skipped


def main(argv=None):
    _utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="alloc-waste-meter",
        description="按分配簇大小计量目录树中每个文件的簇分配浪费（内部碎片）并汇总。")
    parser.add_argument("path", help="要扫描的目录")
    parser.add_argument("--top", type=int, default=10, metavar="N",
                        help="列出浪费最多的前 N 个文件（默认 10）")
    parser.add_argument("--cluster", type=int, default=None, metavar="BYTES",
                        help="强制指定簇大小（默认自动探测所在卷）")
    parser.add_argument("--real", action="store_true",
                        help="改用 OS 实报的磁盘占用（st_blocks / AllocationSize），"
                             "而非簇取整模型（NTFS 驻留小文件会被低估）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    root = args.path
    if not os.path.isdir(root):
        print(f"错误：{root} 不是有效目录", file=sys.stderr)
        return 1
    cluster = args.cluster if args.cluster and args.cluster > 0 else guess_cluster_size(root)

    files, skipped = scan_tree(root, cluster, args.real)
    logical = sum(f[2] for f in files)
    ondisk = sum(f[1] for f in files)
    waste = sum(f[0] for f in files)
    pct = (waste / ondisk * 100.0) if ondisk else 0.0
    top = sorted(files, key=lambda x: -x[0])[:max(0, args.top)]

    if args.json:
        print(json.dumps({
            "root": os.path.abspath(root),
            "cluster_size": cluster,
            "mode": "real" if args.real else "cluster",
            "files": len(files),
            "skipped": skipped,
            "logical_bytes": logical,
            "on_disk_bytes": ondisk,
            "wasted_bytes": waste,
            "waste_percent": round(pct, 2),
            "top": [{"path": p, "wasted": w, "on_disk": od, "logical": lg}
                    for w, od, lg, p in top],
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"扫描根    : {os.path.abspath(root)}")
    print(f"计量模式  : {'OS 实报（--real）' if args.real else '簇分配模型'}（簇 {cluster} B）")
    print(f"文件数    : {len(files)}（跳过 {skipped} 处不可读）")
    print(f"逻辑总量  : {human(logical)}")
    print(f"实际占用  : {human(ondisk)}")
    print(f"簇分配浪费: {human(waste)}（占实际占用的 {pct:.1f}%）")
    print()
    print(f"浪费最多的 {len(top)} 个文件：")
    print(f"{'浪费':>12} {'实际':>12} {'逻辑':>12}  文件")
    for w, od, lg, p in top:
        print(f"{human(w):>12} {human(od):>12} {human(lg):>12}  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
