#!/usr/bin/env python3
"""文件系统大小写敏感性测试（fs-case-sensitivity）。

对指定路径实测其所在文件系统是否区分文件名大小写，并输出报告。
原理：在目标目录下创建唯一命名的探针目录，先创建全小写文件名的
探针文件，再尝试创建仅大小写不同的第二个文件：
  - 第二个文件创建成功且目录中确有 2 个条目  => 大小写敏感；
  - 抛出 FileExistsError 且目录中只有 1 个条目 => 大小写不敏感。
探针目录在测试结束后自动清理，不残留任何文件。

示例命令：
    python fs-case-sensitivity.py                    # 测试当前目录
    python fs-case-sensitivity.py "D:/data"          # 测试 D:/data
    python fs-case-sensitivity.py "C:/" --json       # JSON 输出
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid


def _win_fs_name(path: str):
    """Windows 下用 GetVolumeInformationW 尽力探测文件系统类型名。"""
    try:
        import ctypes

        root, _ = os.path.splitdrive(os.path.abspath(path))
        if not root:
            return None
        root = root + "\\"  # 'C:' -> 'C:\\'
        name = ctypes.create_unicode_buffer(64)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root), None, 0, None, None, None,
            name, len(name))
        return name.value if ok else None
    except Exception:
        return None


def _linux_fs_name(path: str):
    """Linux 下解析 /proc/mounts 尽力探测文件系统类型名。"""
    try:
        target = os.path.realpath(path)
        best, best_type = "", None
        with open("/proc/mounts", "r", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mnt = parts[1].replace("\\040", " ")
                fstype = parts[2]
                if target == mnt or target.startswith(mnt.rstrip("/") + "/"):
                    if len(mnt) >= len(best):
                        best, best_type = mnt, fstype
        return best_type
    except Exception:
        return None


def filesystem_name(path: str):
    """尽力返回文件系统类型名（如 NTFS/ext4），失败返回 None。"""
    if sys.platform.startswith("win"):
        return _win_fs_name(path)
    if sys.platform.startswith("linux"):
        return _linux_fs_name(path)
    return None


def probe_case_sensitivity(base: str) -> dict:
    """在 base 目录下实测大小写敏感性，返回结果字典（探针自动清理）。"""
    result = {
        "path": os.path.abspath(base),
        "platform": sys.platform,
        "filesystem": None,
        "case_sensitive": None,  # True=敏感, False=不敏感, None=无法判定
        "verdict": "",
        "evidence": [],
    }
    result["filesystem"] = filesystem_name(result["path"])

    probe_dir = os.path.join(
        result["path"], "case_probe_" + uuid.uuid4().hex[:12])
    os.makedirs(probe_dir)
    lower = os.path.join(probe_dir, "probe.txt")
    upper = os.path.join(probe_dir, "PROBE.txt")
    try:
        with open(lower, "x", encoding="utf-8") as fh:
            fh.write("case sensitivity probe\n")

        second_created = True
        try:
            with open(upper, "x", encoding="utf-8") as fh:
                fh.write("second probe\n")
        except FileExistsError:
            second_created = False

        entries = sorted(os.listdir(probe_dir))
        if second_created and len(entries) == 2:
            result["case_sensitive"] = True
            result["evidence"].append(
                "成功同时创建 probe.txt 与 PROBE.txt，目录实际存在 2 个条目")
        elif (not second_created) and len(entries) == 1:
            result["case_sensitive"] = False
            result["evidence"].append(
                "以不同大小写创建 PROBE.txt 抛出 FileExistsError，目录中只有 1 个条目")
            if os.path.exists(upper):
                result["evidence"].append(
                    "os.path.exists('PROBE.txt') 命中已有小写文件（大小写不敏感的路径解析）")
        else:
            result["case_sensitive"] = len(entries) == 2
            result["evidence"].append(
                "行为异常，按目录条目数推断：entries=%r" % (entries,))
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)

    if result["case_sensitive"] is True:
        result["verdict"] = "case-sensitive（区分大小写）"
    elif result["case_sensitive"] is False:
        result["verdict"] = "case-insensitive（不区分大小写）"
    else:
        result["verdict"] = "inconclusive（无法判定）"
    return result


def render(result: dict) -> str:
    lines = [
        "文件系统大小写敏感性测试报告",
        "-" * 44,
        "测试路径  : %s" % result["path"],
        "平台      : %s" % result["platform"],
        "文件系统  : %s" % (result["filesystem"] or "未知"),
        "结论      : %s" % result["verdict"],
        "证据      :",
    ]
    for ev in result["evidence"]:
        lines.append("  - %s" % ev)
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="实测指定路径所在文件系统是否区分大小写")
    parser.add_argument("path", nargs="?", default=".",
                        help="要测试的目录路径（默认当前目录）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not os.path.isdir(args.path):
        print("错误：路径不存在或不是目录：%s" % args.path, file=sys.stderr)
        return 2
    try:
        result = probe_case_sensitivity(args.path)
    except OSError as exc:
        print("错误：探针测试失败：%s" % exc, file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
