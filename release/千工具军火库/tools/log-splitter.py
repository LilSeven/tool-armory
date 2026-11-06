#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""大日志切分 — 按行数或字节大小把大日志文件切成多个带编号的小文件。

用法:
  python log-splitter.py app.log -n 100000            # 每片最多 10 万行
  python log-splitter.py app.log -b 50M               # 每片最多 50 MB
  python log-splitter.py app.log -n 500 -o parts -p app --dry-run
  python log-splitter.py app.log -b 1G -o parts

说明:
  * -n / -b 二选一; -b 支持 K/M/G 后缀(1024 进制), 如 512K、50M、2G, 也可写纯字节数。
  * 字节模式尽量按行边界切, 不把一行切成两半; 单行超过限额时该行独立成片(可能超限)。
  * 输出文件为 <outdir>/<prefix><编号>, 编号从 1 起、至少 3 位, 宽度按实际片数精确确定,
    因此文件名字典序 = 编号顺序。
  * 默认 outdir 为输入文件所在目录, 默认 prefix 为 <输入文件名>. (如 app.log.001)。
  * --dry-run 只计算并打印切分计划, 不写任何文件。
  * 真正切分时按二进制读写, 内容逐字节保真(可用 cat 片段 | cmp - 原文件 验证)。
退出码: 0 成功; 2 参数或文件错误。
"""

import argparse
import os
import re
import sys


def _force_utf8():
    """Windows 控制台/管道下强制 UTF-8。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def parse_size(text):
    """'50M' -> 52428800; 支持 K/M/G(1024 进制)与纯字节数。"""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kKmMgG]?)[bB]?", text.strip())
    if not m:
        raise ValueError("无法识别的大小 %r, 示例: 100000 / 512K / 50M / 2G" % text)
    mult = {"": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}[m.group(2).lower()]
    n = int(float(m.group(1)) * mult)
    if n <= 0:
        raise ValueError("大小必须为正数: %r" % text)
    return n


def simulate_parts(path, lines_limit, bytes_limit):
    """与实际切分同一算法, 只统计片数(供 --dry-run 使用)。"""
    parts = 0
    cur = 0
    with open(path, "rb") as f:
        for line in f:
            if lines_limit is not None:
                if cur == 0:
                    parts += 1
                cur += 1
                if cur >= lines_limit:
                    cur = 0
            else:
                if cur and cur + len(line) > bytes_limit:
                    cur = 0
                if cur == 0:
                    parts += 1
                cur += len(line)
    return parts


def _open_part(outdir, prefix, part, tmp_files):
    tmp = os.path.join(outdir, "%s%06d.tmp~" % (prefix, part))
    tmp_files.append(tmp)
    return open(tmp, "wb")


def write_parts(path, outdir, prefix, lines_limit, bytes_limit):
    """真正切分: 先写临时片, 再按精确宽度重命名, 保证编号位数正确。"""
    os.makedirs(outdir, exist_ok=True)
    part = 0
    cur = 0
    out = None
    tmp_files = []
    try:
        with open(path, "rb") as f:
            for line in f:
                if lines_limit is not None:
                    if cur == 0:
                        part += 1
                        out = _open_part(outdir, prefix, part, tmp_files)
                    out.write(line)
                    cur += 1
                    if cur >= lines_limit:
                        out.close()
                        out = None
                        cur = 0
                else:
                    if out is not None and cur + len(line) > bytes_limit:
                        out.close()
                        out = None
                        cur = 0
                    if out is None:
                        part += 1
                        out = _open_part(outdir, prefix, part, tmp_files)
                    out.write(line)
                    cur += len(line)
        if out is not None:
            out.close()
    except BaseException:  # 出错时清理临时片
        if out is not None:
            out.close()
        for tmp in tmp_files:
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
    width = max(3, len(str(part)))
    finals = []
    for i, tmp in enumerate(tmp_files, 1):
        final = os.path.join(outdir, "%s%0*d" % (prefix, width, i))
        os.replace(tmp, final)
        finals.append((final, os.path.getsize(final)))
    return finals


def main(argv=None):
    _force_utf8()
    p = argparse.ArgumentParser(
        prog="log-splitter.py",
        description="按行数或字节大小把大日志文件切成多个带编号的小文件")
    p.add_argument("input", help="输入大日志文件")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("-n", "--lines", type=int, metavar="N", help="每个切片最多 N 行")
    g.add_argument("-b", "--bytes", dest="size", metavar="SIZE",
                   help="每个切片最多 SIZE 字节, 支持 K/M/G 后缀")
    p.add_argument("-o", "--outdir", help="输出目录, 缺省为输入文件所在目录")
    p.add_argument("-p", "--prefix", help="切片文件名前缀, 缺省为 <输入文件名>.")
    p.add_argument("--dry-run", action="store_true", help="只打印计划, 不写文件")
    args = p.parse_args(argv)

    if not os.path.isfile(args.input):
        print("[log-splitter] 文件不存在: %s" % args.input, file=sys.stderr)
        return 2
    lines_limit = bytes_limit = None
    try:
        if args.lines is not None:
            if args.lines < 1:
                raise ValueError("-n 必须为正整数")
            lines_limit = args.lines
        else:
            bytes_limit = parse_size(args.size)
    except ValueError as e:
        print("[log-splitter] %s" % e, file=sys.stderr)
        return 2

    outdir = args.outdir or os.path.dirname(os.path.abspath(args.input))
    prefix = args.prefix if args.prefix is not None else os.path.basename(args.input) + "."

    if args.dry_run:
        try:
            parts = simulate_parts(args.input, lines_limit, bytes_limit)
        except OSError as e:
            print("[log-splitter] 读取失败: %s" % e, file=sys.stderr)
            return 2
        if parts == 0:
            print("[log-splitter] 输入为空, 不会产生切片")
            return 0
        width = max(3, len(str(parts)))
        print("[log-splitter] 计划(dry-run): %s -> %d 片, 编号宽度 %d"
              % (args.input, parts, width))
        print("  %s" % os.path.join(outdir, "%s%0*d" % (prefix, width, 1)))
        print("  ...")
        print("  %s" % os.path.join(outdir, "%s%0*d" % (prefix, width, parts)))
        return 0

    try:
        finals = write_parts(args.input, outdir, prefix, lines_limit, bytes_limit)
    except OSError as e:
        print("[log-splitter] 写入失败: %s" % e, file=sys.stderr)
        return 2
    if not finals:
        print("[log-splitter] 输入为空, 未生成切片")
        return 0
    total = sum(sz for _, sz in finals)
    print("[log-splitter] 完成: %d 片, 共 %d 字节 -> %s" % (len(finals), total, outdir))
    show = finals if len(finals) <= 10 else finals[:9] + [None] + finals[-1:]
    for item in show:
        if item is None:
            print("  ...")
        else:
            print("  %s  %d 字节" % (os.path.basename(item[0]), item[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
