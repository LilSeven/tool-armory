#!/usr/bin/env python3
r"""超长路径查找器（long-path-finder）

用途:
    递归扫描目录，统计每个文件完整路径的字符长度，找出接近或超过
    Windows MAX_PATH（260 字符）限制的文件，预防复制、移动、同步与
    解压失败。长度按 Unicode 字符数计算，不含 \\?\ 前缀，以绝对路径
    为基准。

示例命令:
    python long-path-finder.py K:\data
    python long-path-finder.py K:\data --warn 200 --threshold 240
    python long-path-finder.py K:\data --json --max-show 100

退出码:
    0 = 正常完成（含未发现超长路径的情况）
    2 = 参数错误或目录不存在
"""

import argparse
import json
import os
import sys


def _safe_stdout():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass


def scan(root, walk_errors):
    """返回 [(length, path), ...]，按长度降序排列。"""
    found = []
    for dirpath, _dirnames, filenames in os.walk(root, onerror=walk_errors.append):
        for name in filenames:
            path = os.path.join(dirpath, name)
            found.append((len(path), path))
    found.sort(key=lambda item: (-item[0], item[1]))
    return found


def main(argv=None):
    _safe_stdout()
    parser = argparse.ArgumentParser(
        description="找出路径长度接近或超过 260 字符的文件，预防复制与同步失败。")
    parser.add_argument("directory", help="要扫描的目录")
    parser.add_argument("-t", "--threshold", type=int, default=260,
                        help="路径达到该字符数视为超限，默认 260（Windows MAX_PATH）")
    parser.add_argument("-w", "--warn", type=int, default=240,
                        help="路径达到该字符数且未超限时提示接近，默认 240")
    parser.add_argument("--max-show", type=int, default=100,
                        help="每组最多显示条数，默认 100")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    root = args.directory
    if not os.path.isdir(root):
        print("错误: 目录不存在或不是目录: %s" % root, file=sys.stderr)
        return 2
    root = os.path.abspath(root)

    errors = []
    found = scan(root, errors)
    over = [item for item in found if item[0] >= args.threshold]
    near = [item for item in found if args.warn <= item[0] < args.threshold]
    show = max(0, args.max_show)

    if args.json:
        payload = {
            "root": root,
            "threshold": args.threshold,
            "warn": args.warn,
            "total_files": len(found),
            "over_total": len(over),
            "near_total": len(near),
            "over": [{"length": n, "path": p} for n, p in over[:show]],
            "near": [{"length": n, "path": p} for n, p in near[:show]],
            "walk_errors": errors[:20],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("根目录: %s" % root)
    print("扫描文件总数: %d（阈值: 超限 >= %d，接近 >= %d）"
          % (len(found), args.threshold, args.warn))
    if over:
        note = "" if len(over) <= show else "（仅显示前 %d 条）" % show
        print("超过 %d 字符的文件: %d 个%s" % (args.threshold, len(over), note))
        for n, p in over[:show]:
            print("  [%d] %s" % (n, p))
    else:
        print("超过 %d 字符的文件: 无" % args.threshold)
    if near:
        note = "" if len(near) <= show else "（仅显示前 %d 条）" % show
        print("接近限制（%d~%d 字符）的文件: %d 个%s"
              % (args.warn, args.threshold - 1, len(near), note))
        for n, p in near[:show]:
            print("  [%d] %s" % (n, p))
    else:
        print("接近限制（%d~%d 字符）的文件: 无" % (args.warn, args.threshold - 1))
    print("无法访问的目录: %d 个" % len(errors))
    print("提示: Windows 传统 API 路径上限 260 字符；超限时可改用 \\\\?\\ 前缀访问，"
          "或缩短目录/文件名。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
