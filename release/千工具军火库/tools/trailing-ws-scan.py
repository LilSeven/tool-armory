#!/usr/bin/env python3
"""行尾空白扫描 / trailing whitespace scan.

找出文本文件中的行尾空白和文件末尾多余空行, 支持 --fix 直接清理:
  * 行尾空白    : 换行符之前还有空格或制表符;
  * 末尾多余空行: 最后一个非空行之后的空白行, 清理后文件以单个换行收尾。

文件按字节处理, 保留原有换行风格(LF/CRLF/CR)与编码/BOM;
UTF-16/32 文件与二进制文件(前 8KB 含 NUL)自动跳过、不做修改。

用法:
  python trailing-ws-scan.py PATH... [-r] [--fix] [--ext .py,.md] [--exclude NAME]... [-q]

示例:
  python trailing-ws-scan.py src -r              # 递归扫描目录
  python trailing-ws-scan.py src -r --fix        # 扫描并原地清理
  python trailing-ws-scan.py a.py b.md           # 只扫描指定文件

退出码: 0 = 无问题(或 --fix 全部完成); 1 = 发现问题; 2 = 路径/IO 错误。
"""

import argparse
import os
import sys
from pathlib import Path

WS_CHARS = b" \t"
DEFAULT_EXCLUDES = {".git"}
MAX_SHOW = 20  # 每个文件最多列出的行号数


def parse_exts(text):
    if not text:
        return None
    exts = set()
    for token in text.replace(",", " ").split():
        token = token.strip().lower()
        if token:
            exts.add("." + token.lstrip("."))
    return exts or None


def match_ext(path, exts):
    return True if exts is None else path.suffix.lower() in exts


def collect(roots, recursive, exts, excludes):
    """返回 (文件列表, 错误消息列表); 显式给出的文件不做扩展名过滤。"""
    files, errors = [], []
    for root in roots:
        p = Path(root)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            if recursive:
                for dirpath, dirnames, filenames in os.walk(p):
                    dirnames[:] = sorted(d for d in dirnames if d not in excludes)
                    for name in sorted(filenames):
                        if name in excludes:
                            continue
                        f = Path(dirpath, name)
                        if match_ext(f, exts):
                            files.append(f)
            else:
                try:
                    names = sorted(os.listdir(p))
                except OSError as exc:
                    errors.append(f"{p}: {exc}")
                    continue
                for name in names:
                    if name in excludes:
                        continue
                    f = p / name
                    if f.is_file() and match_ext(f, exts):
                        files.append(f)
        else:
            errors.append(f"路径不存在: {p}")
    return files, errors


def is_wide_unicode(data):
    """是否带 UTF-16/32 BOM(先查 32 位, 避免与 16 位前缀混淆)。"""
    if data[:4] in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"):
        return True
    return data[:2] in (b"\xff\xfe", b"\xfe\xff")


def looks_binary(data):
    return b"\x00" in data[:8192]


def split_term(line):
    """把一行字节拆成 (内容, 换行符)。"""
    for t in (b"\r\n", b"\n", b"\r"):
        if line.endswith(t):
            return line[:-len(t)], t
    return line, b""


def clean(data):
    """返回 (清理后的字节, 行尾空白行号列表, 删除的末尾空行数)。"""
    pieces, ws_lines = [], []
    for idx, raw in enumerate(data.splitlines(keepends=True), 1):
        content, term = split_term(raw)
        stripped = content.rstrip(WS_CHARS)
        if stripped != content:
            ws_lines.append(idx)
        pieces.append(stripped + term)
    removed = 0
    while pieces and split_term(pieces[-1])[0] == b"":
        pieces.pop()
        removed += 1
    return b"".join(pieces), ws_lines, removed


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="扫描(并可用 --fix 清理)文本文件中的行尾空白与末尾多余空行")
    ap.add_argument("paths", nargs="+", metavar="PATH", help="文件或目录(可多个)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="递归遍历目录(默认只看一层)")
    ap.add_argument("--fix", action="store_true",
                    help="原地清理: 去掉行尾空白与末尾多余空行")
    ap.add_argument("--ext", default="", metavar="EXTS",
                    help="只处理这些扩展名(逗号分隔, 如 .py,.md); 显式给出的文件不受限")
    ap.add_argument("--exclude", action="append", default=[], metavar="NAME",
                    help="按名字跳过的目录或文件(可多次); 默认已跳过 .git")
    ap.add_argument("-q", "--quiet", action="store_true", help="只输出汇总")
    args = ap.parse_args(argv)

    excludes = DEFAULT_EXCLUDES | set(args.exclude)
    files, errors = collect(args.paths, args.recursive, parse_exts(args.ext), excludes)

    n_seen = n_bad = n_fixed = n_skip = 0
    for f in files:
        try:
            data = f.read_bytes()
        except OSError as exc:
            errors.append(f"{f}: {exc}")
            continue
        if is_wide_unicode(data):
            n_skip += 1
            if not args.quiet:
                print(f"[跳过] {f}: UTF-16/32 文件")
            continue
        if looks_binary(data):
            n_skip += 1
            continue
        n_seen += 1
        fixed, ws_lines, removed = clean(data)
        if not ws_lines and not removed:
            continue
        n_bad += 1
        if args.fix:
            try:
                f.write_bytes(fixed)
            except OSError as exc:
                errors.append(f"{f}: 写入失败: {exc}")
                continue
            n_fixed += 1
        if not args.quiet:
            print(f"[{'已修复' if args.fix else '问题'}] {f}")
            if ws_lines:
                shown = ", ".join(map(str, ws_lines[:MAX_SHOW]))
                more = "" if len(ws_lines) <= MAX_SHOW else f" …(共 {len(ws_lines)} 处)"
                print(f"    行尾空白: 第 {shown}{more} 行")
            if removed:
                print(f"    末尾多余空行: {removed} 行")

    if args.fix:
        print(f"修复完成: 检查文本文件 {n_seen} 个, 清理 {n_fixed} 个, "
              f"跳过 {n_skip} 个(二进制/UTF-16/32)")
    else:
        print(f"扫描完成: 检查文本文件 {n_seen} 个, 有问题 {n_bad} 个, "
              f"跳过 {n_skip} 个(二进制/UTF-16/32)")
    if errors:
        print(f"发生 {len(errors)} 个错误:", file=sys.stderr)
        for msg in errors:
            print(f"  {msg}", file=sys.stderr)
        return 2
    return 0 if (args.fix or n_bad == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
