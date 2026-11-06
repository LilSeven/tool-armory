#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mount-table — 挂载点信息表。

列出系统各挂载点的设备、卷标、驱动器类型、文件系统类型与空间使用情况一览表。

- Windows: 用 ctypes 调 GetLogicalDrives / GetDriveTypeW / GetVolumeInformationW
  枚举盘符并读取卷信息, 容量用 shutil.disk_usage 统计。
- Linux: 解析 /proc/mounts (默认过滤常见伪文件系统, --all 显示全部)。
- 其他 POSIX: 解析 `mount` 命令输出。

示例:
    python -I mount-table.py            # 挂载点一览表
    python -I mount-table.py --all      # Linux 下包含伪文件系统
    python -I mount-table.py --json     # JSON 输出, 便于脚本处理

退出码: 0 成功; 1 未发现可用挂载点。
"""

import argparse
import ctypes
import json
import re
import shutil
import subprocess
import sys
import unicodedata

DRIVE_TYPES = {
    0: "UNKNOWN", 1: "NO_ROOT", 2: "REMOVABLE", 3: "FIXED",
    4: "NETWORK", 5: "CDROM", 6: "RAMDISK",
}

LINUX_PSEUDO_FS = {
    "proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "securityfs", "cgroup",
    "cgroup2", "pstore", "bpf", "debugfs", "tracefs", "configfs", "fusectl",
    "hugetlbfs", "mqueue", "nsfs", "autofs", "binfmt_misc", "overlay",
    "squashfs", "ramfs", "cramfs", "efivarfs",
}

MOUNT_LINE_RE = re.compile(r"^(.+?)\son\s(.+?)\s\((.*)\)$")


def dwidth(text):
    """字符串的终端显示宽度, CJK 全角字符按 2 计。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
               for ch in text)


def pad(text, width, align="left"):
    gap = max(width - dwidth(text), 0)
    if align == "right":
        return " " * gap + text
    return text + " " * gap


def human(num):
    """字节数转人类可读字符串。"""
    if num is None:
        return "-"
    sign = "-" if num < 0 else ""
    val = float(abs(num))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if val < 1024 or unit == "PiB":
            if unit == "B":
                return "%s%d B" % (sign, int(val))
            return "%s%.1f %s" % (sign, val, unit)
        val /= 1024.0


def usage_tuple(path):
    try:
        du = shutil.disk_usage(path)
        return du.total, du.used, du.free
    except OSError:
        return None, None, None


def list_windows():
    kernel32 = ctypes.windll.kernel32
    mask = int(kernel32.GetLogicalDrives())
    rows = []
    for i in range(26):
        if not (mask >> i) & 1:
            continue
        root = chr(ord("A") + i) + ":\\"
        dtype = DRIVE_TYPES.get(
            int(kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))), "?")
        label, fs = "", ""
        try:
            name = ctypes.create_unicode_buffer(261)
            fsbuf = ctypes.create_unicode_buffer(64)
            serial = ctypes.c_ulong(0)
            maxlen = ctypes.c_ulong(0)
            flags = ctypes.c_ulong(0)
            ok = kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(root), name, len(name),
                ctypes.byref(serial), ctypes.byref(maxlen), ctypes.byref(flags),
                fsbuf, len(fsbuf))
            if ok:
                label, fs = name.value, fsbuf.value
        except Exception:
            pass
        total, used, free = usage_tuple(root)
        rows.append({
            "mount": root, "device": root[:2], "label": label or "-",
            "type": dtype, "fs": fs or "?",
            "total": total, "used": used, "free": free,
        })
    return rows


def list_linux(show_all):
    rows, seen = [], set()
    with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 3:
                continue
            dev = parts[0]
            mnt = parts[1].replace("\\040", " ").replace("\\011", "\t")
            fstype = parts[2]
            if mnt in seen:
                continue
            seen.add(mnt)
            if not show_all and fstype in LINUX_PSEUDO_FS:
                continue
            total, used, free = usage_tuple(mnt)
            rows.append({"mount": mnt, "device": dev, "label": "-",
                         "type": "mount", "fs": fstype,
                         "total": total, "used": used, "free": free})
    return rows


def list_posix_mount():
    rows = []
    try:
        proc = subprocess.run(["mount"], capture_output=True, text=True,
                              timeout=15)
        out = proc.stdout or ""
    except Exception as exc:
        print("failed to run `mount`: %s" % exc, file=sys.stderr)
        return rows
    for line in out.splitlines():
        match = MOUNT_LINE_RE.match(line.strip())
        if not match:
            continue
        dev, mnt, rest = match.group(1), match.group(2), match.group(3)
        fstype = rest.split(",")[0].strip()
        total, used, free = usage_tuple(mnt)
        rows.append({"mount": mnt, "device": dev, "label": "-",
                     "type": "mount", "fs": fstype,
                     "total": total, "used": used, "free": free})
    return rows


def render_table(rows):
    headers = ("MOUNT", "DEVICE", "LABEL", "TYPE", "FS",
               "TOTAL", "USED", "FREE", "USE%")
    aligns = ("left", "left", "left", "left", "left",
              "right", "right", "right", "right")
    table = [list(headers)]
    for r in rows:
        if r["total"] and r["used"] is not None:
            pct = "%.1f%%" % (100.0 * r["used"] / r["total"])
        else:
            pct = "-"
        table.append([r["mount"], r["device"], r["label"], r["type"], r["fs"],
                      human(r["total"]), human(r["used"]), human(r["free"]), pct])
    widths = [max(dwidth(row[c]) for row in table) for c in range(len(headers))]
    lines = [" ".join(pad(table[0][c], widths[c], aligns[c])
                      for c in range(len(headers))).rstrip()]
    lines.append(" ".join("-" * widths[c] for c in range(len(headers))))
    for row in table[1:]:
        lines.append(" ".join(pad(row[c], widths[c], aligns[c])
                              for c in range(len(headers))).rstrip())
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mount-table",
        description="列出系统各挂载点的设备、文件系统类型与空间使用情况一览表。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python -I mount-table.py\n  python -I mount-table.py --json")
    parser.add_argument("--all", action="store_true",
                        help="Linux 下不过滤伪文件系统")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    if sys.platform.startswith("win"):
        rows = list_windows()
    elif sys.platform.startswith("linux"):
        rows = list_linux(args.all)
    else:
        rows = list_posix_mount()

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("no mount points found", file=sys.stderr)
        return 1
    print(render_table(rows))
    print("")
    print("%d mount point(s)" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
