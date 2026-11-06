#!/usr/bin/env python3
"""内存信息报告 (memory-report) —— 查询物理内存总量与可用量，跨平台输出。

用途:
    报告物理内存总量、可用量、已用量与使用率。
      * Linux  : 读取 /proc/meminfo（MemTotal / MemAvailable，kB 换算为字节）；
      * Windows: 通过 ctypes 调用 kernel32.GlobalMemoryStatusEx；
      * 其他平台: 打印说明并以退出码 1 结束。

示例命令:
    python memory-report.py            # 人类可读输出
    python memory-report.py --json     # JSON 输出

只依赖 Python 标准库；只读查询，不修改系统任何状态。
"""

import argparse
import ctypes
import json
import sys


def _force_utf8_stdout():
    """管道/重定向场景下尽量以 UTF-8 输出，避免 Windows 默认码页导致乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (stream.encoding or "").lower().replace("-", "")
            if enc and enc != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def linux_memory():
    """解析 /proc/meminfo，返回以字节为单位的内存信息。"""
    info = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as fh:
        for line in fh:
            key, sep, rest = line.partition(":")
            fields = rest.split()
            if sep and fields:
                try:
                    info[key] = int(fields[0]) * 1024  # /proc/meminfo 的数值单位是 kB
                except ValueError:
                    pass
    if "MemTotal" not in info:
        raise OSError("无法从 /proc/meminfo 解析出 MemTotal")
    total = info["MemTotal"]
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    return {"total": total, "available": avail, "source": "/proc/meminfo"}


def windows_memory():
    """通过 ctypes 调用 kernel32.GlobalMemoryStatusEx 获取物理内存信息。"""
    from ctypes import wintypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        raise OSError("GlobalMemoryStatusEx 调用失败")
    return {
        "total": stat.ullTotalPhys,
        "available": stat.ullAvailPhys,
        "load_percent": stat.dwMemoryLoad,
        "source": "kernel32.GlobalMemoryStatusEx",
    }


def query_memory():
    """按平台选择实现，返回统一结构的内存信息字典。"""
    if sys.platform.startswith("linux"):
        data = linux_memory()
    elif sys.platform == "win32":
        data = windows_memory()
    else:
        raise RuntimeError(
            "不支持的平台 %r：仅实现了 Linux(/proc/meminfo) 与 Windows(ctypes)" % sys.platform
        )
    used = data["total"] - data["available"]
    data["used"] = used
    data["used_percent"] = round(used * 100.0 / data["total"], 1) if data["total"] else 0.0
    data.setdefault("load_percent", data["used_percent"])
    data["platform"] = sys.platform
    return data


def human(nbytes):
    """字节数 -> 人类可读字符串（KiB/MiB/GiB/TiB）。"""
    size = float(nbytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%.1f TiB" % size


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="memory-report",
        description="内存信息报告：查询物理内存总量与可用量（Linux /proc 或 Windows ctypes）",
    )
    parser.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)
    _force_utf8_stdout()

    try:
        data = query_memory()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print("查询内存信息失败: %s" % exc, file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print("平台      : %s  (数据来源: %s)" % (data["platform"], data["source"]))
        print("物理内存  : %s" % human(data["total"]))
        print("可用内存  : %s" % human(data["available"]))
        print("已用内存  : %s (%.1f%%, 系统报告负载 %.0f%%)"
              % (human(data["used"]), data["used_percent"], data["load_percent"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
