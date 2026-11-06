#!/usr/bin/env python3
"""Python 环境报告（python-env-report）。

输出当前 Python 解释器的环境概况：解释器路径、版本、实现与构建
信息、各类默认编码、平台信息、虚拟环境/隔离模式状态等。

示例命令：
    python python-env-report.py             # 人读格式
    python python-env-report.py --json      # JSON 输出
"""

from __future__ import annotations

import argparse
import json
import locale
import os
import platform
import sys


def collect() -> dict:
    try:
        build = " ".join(platform.python_build())
    except Exception:
        build = ""
    try:
        compiler = platform.python_compiler()
    except Exception:
        compiler = ""
    try:
        preferred = locale.getpreferredencoding(False)
    except Exception:
        preferred = None
    try:
        arch = platform.architecture()[0]
    except Exception:
        arch = None
    uname = platform.uname()

    return {
        "executable": sys.executable,
        "version": sys.version.split()[0],
        "version_full": sys.version.replace("\n", " "),
        "version_info": {
            "major": sys.version_info.major,
            "minor": sys.version_info.minor,
            "micro": sys.version_info.micro,
            "releaselevel": sys.version_info.releaselevel,
            "serial": sys.version_info.serial,
        },
        "implementation": platform.python_implementation(),
        "build": build,
        "compiler": compiler,
        "encoding_default": sys.getdefaultencoding(),
        "encoding_filesystem": sys.getfilesystemencoding(),
        "encoding_filesystem_errors": sys.getfilesystemencodeerrors(),
        "encoding_stdout": getattr(sys.stdout, "encoding", None),
        "encoding_stderr": getattr(sys.stderr, "encoding", None),
        "encoding_preferred_locale": preferred,
        "utf8_mode": bool(sys.flags.utf8_mode),
        "os_name": os.name,
        "platform": sys.platform,
        "system": uname.system,
        "system_release": uname.release,
        "system_version": uname.version,
        "machine": uname.machine,
        "processor": uname.processor,
        "architecture": arch,
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "in_venv": sys.prefix != sys.base_prefix,
        "isolated_mode": bool(sys.flags.isolated),
        "maxsize": sys.maxsize,
        "byteorder": sys.byteorder,
        "cwd": os.getcwd(),
        "argv0": sys.argv[0],
        "pythonhome_set": bool(os.environ.get("PYTHONHOME")),
        "pythonpath_set": bool(os.environ.get("PYTHONPATH")),
    }


def render(info: dict) -> str:
    vi = info["version_info"]
    pairs = [
        ("可执行文件", info["executable"]),
        ("Python 版本", info["version"]),
        ("完整版本串", info["version_full"]),
        ("版本元组", "major=%d, minor=%d, micro=%d, releaselevel=%s, serial=%d"
         % (vi["major"], vi["minor"], vi["micro"], vi["releaselevel"], vi["serial"])),
        ("实现", info["implementation"]),
        ("构建信息", info["build"] or "-"),
        ("编译器", info["compiler"] or "-"),
        ("默认编码 (getdefaultencoding)", info["encoding_default"]),
        ("文件系统编码", "%s (%s)" % (info["encoding_filesystem"],
                                     info["encoding_filesystem_errors"])),
        ("stdout 编码", info["encoding_stdout"]),
        ("stderr 编码", info["encoding_stderr"]),
        ("locale 首选编码", info["encoding_preferred_locale"]),
        ("UTF-8 模式", "开" if info["utf8_mode"] else "关"),
        ("os.name", info["os_name"]),
        ("sys.platform", info["platform"]),
        ("系统", "%s %s" % (info["system"], info["system_release"])),
        ("机器类型", info["machine"]),
        ("处理器", info["processor"] or "-"),
        ("位数", info["architecture"] or "-"),
        ("sys.prefix", info["prefix"]),
        ("sys.base_prefix", info["base_prefix"]),
        ("虚拟环境", "是" if info["in_venv"] else "否"),
        ("隔离模式 (-I)", "是" if info["isolated_mode"] else "否"),
        ("sys.maxsize", str(info["maxsize"])),
        ("字节序", info["byteorder"]),
        ("当前目录", info["cwd"]),
        ("PYTHONHOME 已设置", "是" if info["pythonhome_set"] else "否"),
        ("PYTHONPATH 已设置", "是" if info["pythonpath_set"] else "否"),
    ]
    lines = ["Python 环境报告", "-" * 48]
    for key, val in pairs:
        lines.append("%s : %s" % (key, val))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="输出 Python 解释器路径、版本、默认编码与实现信息等环境概况")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    info = collect()
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(render(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
