#!/usr/bin/env python3
"""文件系统参数信息（stat-fs-info）。

输出指定路径所在文件系统的块大小、总空间/已用/可用空间、文件数
（inode）限制等参数。POSIX 平台使用 os.statvfs；Windows 没有
statvfs，改用 ctypes 调用 Win32 API（GetDiskFreeSpaceExW /
GetDiskFreeSpaceW / GetVolumeInformationW），必要时回退到
shutil.disk_usage。

示例命令：
    python stat-fs-info.py                  # 当前目录所在文件系统
    python stat-fs-info.py "C:/"            # C 盘
    python stat-fs-info.py "/" --json       # JSON 输出
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys


def human(n) -> str:
    """把字节数格式化为人类可读字符串。"""
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if n < 1024 or unit == "PiB":
            return ("%d %s" % (int(n), unit)) if unit == "B" else ("%.2f %s" % (n, unit))
        n /= 1024.0


def _posix_info(path: str) -> dict:
    st = os.statvfs(path)
    fr = st.f_frsize or st.f_bsize or 1
    total = fr * st.f_blocks
    free = fr * st.f_bfree
    avail = fr * st.f_bavail
    used = total - free
    return {
        "method": "os.statvfs",
        "path": path,
        "filesystem": None,
        "block_size": st.f_bsize,
        "fragment_size": st.f_frsize,
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "available_bytes": avail,
        "usage_percent": round(used * 100.0 / total, 1) if total else None,
        "files_limit": st.f_files,
        "files_free": st.f_ffree,
        "files_available": st.f_favail,
        "files_note": "f_files 为 inode 总数限制",
        "max_component_length": None,
        "raw_statvfs": {
            "f_bsize": st.f_bsize, "f_frsize": st.f_frsize,
            "f_blocks": st.f_blocks, "f_bfree": st.f_bfree,
            "f_bavail": st.f_bavail, "f_files": st.f_files,
            "f_ffree": st.f_ffree, "f_favail": st.f_favail,
        },
    }


def _windows_info(path: str) -> dict:
    import ctypes

    class ULARGE_INTEGER(ctypes.Structure):
        _fields_ = [("QuadPart", ctypes.c_ulonglong)]

    free_user = ULARGE_INTEGER()
    total = ULARGE_INTEGER()
    free = ULARGE_INTEGER()
    ok = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
        ctypes.c_wchar_p(path),
        ctypes.byref(free_user), ctypes.byref(total), ctypes.byref(free))
    if not ok:
        raise OSError("GetDiskFreeSpaceExW 调用失败")
    used = total.QuadPart - free.QuadPart

    info = {
        "method": "Win32 API（ctypes: GetDiskFreeSpaceExW/GetDiskFreeSpaceW）",
        "path": path,
        "filesystem": None,
        "cluster_size": None,
        "cluster_note": "GetDiskFreeSpaceW 为旧式接口，大容量卷上簇大小为参考值",
        "total_bytes": total.QuadPart,
        "used_bytes": used,
        "free_bytes": free.QuadPart,
        "available_bytes": free_user.QuadPart,
        "usage_percent": round(used * 100.0 / total.QuadPart, 1) if total.QuadPart else None,
        "files_limit": None,
        "files_free": None,
        "files_available": None,
        "files_note": "Windows 公开 API 不提供 inode 式文件数上限查询（NTFS/exFAT 无固定上限）",
        "max_component_length": None,
    }
    try:
        root, _ = os.path.splitdrive(os.path.abspath(path))
        if root:
            root = root + "\\"
            spc = ctypes.c_ulong()
            bps = ctypes.c_ulong()
            fc = ctypes.c_ulong()
            tc = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetDiskFreeSpaceW(
                    ctypes.c_wchar_p(root), ctypes.byref(spc), ctypes.byref(bps),
                    ctypes.byref(fc), ctypes.byref(tc)):
                info["cluster_size"] = spc.value * bps.value
            name = ctypes.create_unicode_buffer(64)
            flags = ctypes.c_ulong()
            maxcomp = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetVolumeInformationW(
                    ctypes.c_wchar_p(root), None, 0, None,
                    ctypes.byref(maxcomp), ctypes.byref(flags),
                    name, len(name)):
                info["filesystem"] = name.value or None
                info["max_component_length"] = maxcomp.value or None
    except Exception:
        pass
    return info


def _shutil_info(path: str) -> dict:
    du = shutil.disk_usage(path)
    used = du.used if hasattr(du, "used") else (du.total - du.free)
    return {
        "method": "shutil.disk_usage",
        "path": path,
        "filesystem": None,
        "block_size": None,
        "fragment_size": None,
        "total_bytes": du.total,
        "used_bytes": used,
        "free_bytes": du.free,
        "available_bytes": du.free,
        "usage_percent": round(used * 100.0 / du.total, 1) if du.total else None,
        "files_limit": None,
        "files_free": None,
        "files_available": None,
        "files_note": "当前获取方式不提供文件数限制",
        "max_component_length": None,
    }


def collect(path: str) -> dict:
    if hasattr(os, "statvfs"):
        return _posix_info(path)
    if os.name == "nt":
        try:
            return _windows_info(path)
        except Exception:
            return _shutil_info(path)
    return _shutil_info(path)


def render(info: dict) -> str:
    def show(v, na="不适用"):
        return v if v not in (None, "") else na

    lines = [
        "文件系统参数信息",
        "-" * 44,
        "路径          : %s" % info["path"],
        "获取方式      : %s" % info["method"],
        "文件系统      : %s" % show(info.get("filesystem"), "未知"),
        "块/簇大小     : %s" % (human(blk) if (blk := (info.get("block_size")
                                                       or info.get("cluster_size")))
                                else "不适用"),
        "总空间        : %s" % human(info["total_bytes"]),
        "已用          : %s" % human(info["used_bytes"]),
        "剩余          : %s" % human(info["free_bytes"]),
        "对当前用户可用: %s" % human(info["available_bytes"]),
        "使用率        : %s" % (("%s%%" % info["usage_percent"])
                                if info.get("usage_percent") is not None else "不适用"),
        "文件数上限    : %s" % show(info.get("files_limit")),
        "文件数说明    : %s" % show(info.get("files_note"), "-"),
        "文件名最长    : %s" % (("%s 字符" % info["max_component_length"])
                                if info.get("max_component_length") else "不适用"),
    ]
    if info.get("cluster_note"):
        lines.append("备注          : %s" % info["cluster_note"])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="输出指定路径所在文件系统的块大小、可用空间与文件数限制等参数")
    parser.add_argument("path", nargs="?", default=".",
                        help="目标路径（默认当前目录）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not os.path.exists(args.path):
        print("错误：路径不存在：%s" % args.path, file=sys.stderr)
        return 2
    try:
        info = collect(args.path)
    except OSError as exc:
        print("错误：获取文件系统信息失败：%s" % exc, file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(render(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
