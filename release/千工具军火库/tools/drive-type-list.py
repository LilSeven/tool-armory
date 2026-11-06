#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""磁盘类型清单（drive-type-list）

用途：
    枚举系统中的盘符（Windows 下 A-Z，经 GetLogicalDrives 位掩码），用
    GetDriveTypeW 区分本地磁盘、可移动磁盘、网络驱动器、光驱、内存盘，
    并经 shutil.disk_usage 给出每个盘的总容量、已用、可用与使用率；
    容量无法读取（如未插盘的光驱、断连的网络映射盘）时以 "-" 显示。
    非 Windows 回退：Linux 解析 /proc/mounts；macOS 枚举 /Volumes
    （类型细分受限，一律标注"本地磁盘"）。

示例命令：
    python drive-type-list.py
    python drive-type-list.py --json
    python drive-type-list.py --json > drives.json

退出码：0 正常完成。
"""

import argparse
import ctypes
import json
import os
import shutil
import sys
import unicodedata

DRIVE_TYPE_NAMES = {
    2: "可移动",
    3: "本地磁盘",
    4: "网络驱动器",
    5: "光驱",
    6: "内存盘",
}

_PSEUDO_FS = {"proc", "sysfs", "devtmpfs", "devpts", "mqueue", "hugetlbfs",
              "securityfs", "debugfs", "tracefs", "pstore", "bpf", "cgroup",
              "cgroup2", "configfs", "fusectl", "autofs", "binfmt_misc",
              "nsfs", "ramfs", "squashfs", "efivarfs", "selinuxfs"}
_NETWORK_FS = {"nfs", "nfs4", "cifs", "smbfs", "smb2", "sshfs", "ncpfs", "9p"}
_REMOVABLE_FS = {"vfat", "exfat", "msdos", "udf", "iso9660"}


def human(n):
    if n is None:
        return "-"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.2f} {unit}"
        n /= 1024.0


def disp_width(s):
    """估算终端显示宽度：东亚全角字符按 2 列计。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def pad(s, width):
    return s + " " * max(0, width - disp_width(s))


def usage_of(root):
    try:
        du = shutil.disk_usage(root)
    except OSError:
        return {"total": None, "used": None, "free": None, "used_percent": None}
    pct = round(du.used / du.total * 100.0, 1) if du.total else 0.0
    return {"total": du.total, "used": du.used, "free": du.free, "used_percent": pct}


def list_windows():
    k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    k32.GetLogicalDrives.restype = ctypes.c_ulong
    k32.GetDriveTypeW.restype = ctypes.c_uint
    mask = k32.GetLogicalDrives()
    entries = []
    for i in range(26):
        if not (mask >> i) & 1:
            continue
        root = f"{chr(ord('A') + i)}:\\"
        dtype = k32.GetDriveTypeW(ctypes.c_wchar_p(root))
        if dtype in (0, 1):      # 0=未知 1=无根目录：视作不存在
            continue
        entry = {"root": root, "type_code": int(dtype),
                 "type": DRIVE_TYPE_NAMES.get(dtype, f"类型{dtype}")}
        entry.update(usage_of(root))
        entries.append(entry)
    return entries


def list_linux():
    entries = []
    if not os.path.exists("/proc/mounts"):
        return entries
    seen = set()
    with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 3:
                continue
            dev = parts[0]
            mnt = parts[1].replace("\\040", " ")
            fstype = parts[2]
            if fstype in _PSEUDO_FS or mnt in seen:
                continue
            seen.add(mnt)
            if fstype in _NETWORK_FS:
                dtype = "网络驱动器"
            elif fstype == "tmpfs":
                dtype = "内存盘"
            elif fstype in _REMOVABLE_FS and dev.startswith("/dev/"):
                dtype = "可移动"
            elif dev.startswith("/dev/"):
                dtype = "本地磁盘"
            else:
                continue
            entry = {"root": mnt, "type_code": None, "type": dtype}
            entry.update(usage_of(mnt))
            entries.append(entry)
    return entries


def list_macos():
    entries = []
    if not os.path.isdir("/Volumes"):
        return entries
    for name in [""] + sorted(os.listdir("/Volumes")):
        root = "/" if not name else "/Volumes/" + name
        entry = {"root": root, "type_code": None, "type": "本地磁盘"}
        entry.update(usage_of(root))
        entries.append(entry)
    return entries


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="drive-type-list",
        description="枚举系统盘符并区分本地/可移动/网络等类型，附各盘容量与使用率。")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    if os.name == "nt":
        entries = list_windows()
    else:
        entries = list_linux()
        if not entries:
            entries = list_macos()
    entries.sort(key=lambda e: e["root"])

    if args.json:
        print(json.dumps({"platform": sys.platform, "drives": entries},
                         ensure_ascii=False, indent=2))
        return 0

    if not entries:
        print("未找到可列出的磁盘或挂载点。")
        return 0

    header = ["盘符/挂载点", "类型", "总容量", "已用", "可用", "使用率"]
    rows = []
    for e in entries:
        pct = e["used_percent"]
        rows.append([e["root"], e["type"],
                     human(e["total"]), human(e["used"]), human(e["free"]),
                     f"{pct:.1f}%" if pct is not None else "-"])
    widths = [max(disp_width(c) for c in col) for col in zip(header, *rows)]
    print("  ".join(pad(c, widths[i]) for i, c in enumerate(header)))
    for row in rows:
        print("  ".join(pad(c, widths[i]) for i, c in enumerate(row)))
    print(f"\n共 {len(rows)} 个驱动器/挂载点。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
