#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""系统信息速览（sysinfo-summary）。

用途：
    用标准库 platform / os / sys / shutil / locale 输出操作系统、Python
    版本、CPU 逻辑核数、架构、编码、磁盘余量等速览信息，便于排查环境问题。

用法：
    python -I sysinfo-summary.py [--json]

示例（Git Bash / Windows）：
    python -I sysinfo-summary.py
    python -I sysinfo-summary.py --json

说明：
    * 每个信息项都单独容错，某项取不到时显示 ?，不影响其余输出；
    * 退出码：0=成功；2=参数错误（argparse）。
"""

from __future__ import annotations

import argparse
import json
import locale
import os
import platform
import shutil
import sys
from datetime import datetime


def _stdout_utf8() -> None:
    """在 Windows 控制台上尽量用 UTF-8 输出，避免中文乱码或编码报错。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def human_size(n: int) -> str:
    v = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(v)} B"
            return f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} TB"


def _safe(fn, default="?"):
    try:
        v = fn()
        return default if v is None or v == "" else v
    except Exception:
        return default


def collect() -> dict:
    bits, linkage = _safe(lambda: platform.architecture(), ("?", "?"))
    try:
        affinity = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        affinity = None
    cpu_total = _safe(os.cpu_count)
    try:
        du = shutil.disk_usage(os.getcwd())
        disk = f"总 {human_size(du.total)} / 可用 {human_size(du.free)}"
    except Exception:
        disk = "?"
    return {
        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "操作系统": _safe(platform.platform),
        "系统/版本": f"{_safe(platform.system)} {_safe(platform.release)}",
        "系统完整版本": _safe(platform.version),
        "主机名": _safe(platform.node),
        "os.name": os.name,
        "架构": f"{_safe(platform.machine)}（{bits} 位，linkage={linkage}）",
        "处理器": _safe(platform.processor),
        "CPU 逻辑核数": cpu_total,
        "CPU 可用核数(亲和性)": affinity if affinity is not None else f"不支持（逻辑核 {cpu_total}）",
        "Python 版本": _safe(platform.python_version),
        "Python 实现": _safe(platform.python_implementation),
        "Python 可执行文件": sys.executable or "?",
        "默认编码": sys.getdefaultencoding(),
        "标准输出编码": _safe(lambda: sys.stdout.encoding),
        "本地编码": _safe(lambda: locale.getpreferredencoding(False)),
        "路径分隔符": os.pathsep,
        "当前目录": os.getcwd(),
        "磁盘(当前目录)": disk,
        "环境变量个数": len(os.environ),
    }


def main(argv=None) -> int:
    _stdout_utf8()
    p = argparse.ArgumentParser(
        prog="sysinfo-summary", description="输出操作系统与 Python 环境速览信息"
    )
    p.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = p.parse_args(argv)

    info = collect()
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        for k, v in info.items():
            print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
