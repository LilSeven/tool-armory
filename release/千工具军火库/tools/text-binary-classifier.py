#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""文本/二进制分类器（text-binary-classifier）

按"空字节（NUL）与控制字符占比"把文件分为 text / binary 两类，并输出目录级
分布统计（可加 --list 查看逐文件明细）。

判定规则（对每个文件的前 --sample 字节）:
  * 空文件                                    -> empty
  * 含任意 NUL(0x00) 字节                     -> binary（NUL 是二进制最强信号）
  * 控制字符占比 > --threshold（默认 0.05）   -> binary
  * 其余                                      -> text
控制字符指 0x00-0x1F 与 0x7F 中，除制表符/换行/垂直制表/换页/回车以外的字节
（NUL 单独统计，不计入控制字符占比）。

用法:
    python text-binary-classifier.py <目录或文件> [选项]

选项:
    --sample N      每个文件最多读取前 N 字节（默认 8192）
    --threshold R   控制字符占比阈值，超过判为 binary（默认 0.05）
    --list          输出逐文件明细（含 NUL / 控制字符占比）
    --json          以 JSON 格式输出
    --hidden        包含以 . 开头的隐藏文件/目录

示例:
    python text-binary-classifier.py ./data
    python text-binary-classifier.py ./data --list --threshold 0.02 --json

仅使用 Python 标准库。
退出码: 0=扫描完成; 1=路径不存在; 2=参数错误。
"""

import argparse
import json
import os
import sys
from collections import Counter

WHITESPACE = frozenset(b"\t\n\v\f\r")


def classify_sample(data, threshold):
    """返回 (verdict, nul_ratio, ctrl_ratio, reason)。"""
    if not data:
        return "empty", 0.0, 0.0, "空文件"
    n = len(data)
    nul = data.count(0)
    ctrl = sum(1 for b in data if (b < 0x20 and b not in WHITESPACE) or b == 0x7F)
    nul_ratio = nul / n
    ctrl_ratio = ctrl / n
    if nul:
        return ("binary", nul_ratio, ctrl_ratio,
                "含 %d 个 NUL 字节（占 %.2f%%）" % (nul, nul_ratio * 100))
    if ctrl_ratio > threshold:
        return ("binary", nul_ratio, ctrl_ratio,
                "控制字符占比 %.2f%% 超过阈值 %.2f%%" % (ctrl_ratio * 100, threshold * 100))
    return ("text", nul_ratio, ctrl_ratio,
            "无 NUL，控制字符占比 %.2f%% 未超阈值" % (ctrl_ratio * 100))


def iter_files(root, include_hidden):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        if include_hidden:
            dirnames[:] = sorted(dirnames)
            names = sorted(filenames)
        else:
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            names = sorted(f for f in filenames if not f.startswith("."))
        for name in names:
            yield os.path.join(dirpath, name)


def trunc(s, n):
    return s if len(s) <= n else "..." + s[-(n - 3):]


def scan(root, sample_size, threshold, include_hidden):
    rows = []
    errors = []
    for path in iter_files(root, include_hidden):
        try:
            with open(path, "rb") as fh:
                data = fh.read(sample_size)
        except OSError as exc:
            errors.append({"path": path, "error": str(exc)})
            continue
        verdict, nul_ratio, ctrl_ratio, reason = classify_sample(data, threshold)
        rows.append({
            "path": path, "verdict": verdict,
            "nul_ratio": nul_ratio, "ctrl_ratio": ctrl_ratio,
            "reason": reason, "sampled_bytes": len(data),
        })
    return rows, errors


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="text-binary-classifier",
        description="按空字节与控制字符比例把文件分为文本与二进制并分别统计分布。",
    )
    parser.add_argument("path", help="要扫描的目录（或单个文件）")
    parser.add_argument("--sample", type=int, default=8192, help="每个文件最多读取前 N 字节（默认 8192）")
    parser.add_argument("--threshold", type=float, default=0.05,
                        help="控制字符占比阈值，超过判为 binary（默认 0.05）")
    parser.add_argument("--list", action="store_true", help="输出逐文件明细")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--hidden", action="store_true", help="包含隐藏文件/目录")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not os.path.exists(args.path):
        print("错误: 路径不存在: %s" % args.path, file=sys.stderr)
        return 1

    rows, errors = scan(args.path, max(1, args.sample), args.threshold, args.hidden)
    dist = Counter(r["verdict"] for r in rows)
    total = len(rows)

    if args.json:
        payload = {
            "root": args.path,
            "total_files": total,
            "distribution": {k: dist.get(k, 0) for k in ("text", "binary", "empty")},
            "threshold": args.threshold,
            "sample_bytes": max(1, args.sample),
            "read_errors": errors,
        }
        if args.list:
            payload["files"] = rows
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("扫描目标: %s   文件总数: %d（读取失败 %d）" % (args.path, total, len(errors)))
    print("判定阈值: NUL 出现即 binary；控制字符占比 > %.2f%% 判为 binary；采样前 %d 字节"
          % (args.threshold * 100, max(1, args.sample)))
    print()
    print("分类分布:")
    for key in ("text", "binary", "empty"):
        count = dist.get(key, 0)
        pct = (count * 100.0 / total) if total else 0.0
        bar = "#" * max(1, int(round(pct / 4))) if count else ""
        print("  %-6s %4d %6.1f%%  %s" % (key, count, pct, bar))
    if args.list:
        print()
        print("逐文件明细:")
        for r in rows:
            print("  %-6s nul=%5.2f%% ctrl=%5.2f%%  %-28s %s" % (
                r["verdict"], r["nul_ratio"] * 100, r["ctrl_ratio"] * 100,
                trunc(r["path"], 28), r["reason"]))
    for err in errors:
        print("  [读取失败] %s: %s" % (err["path"], err["error"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
