#!/usr/bin/env python3
"""编码与 BOM 检查 / encoding & BOM check.

按字节特征猜测各文本文件的编码, 标记非 UTF-8 及带 BOM 的文件:
  * BOM 识别: UTF-8 / UTF-16 LE·BE / UTF-32 LE·BE, 并校验余下字节能否正常解码;
  * 无 BOM 时按 us-ascii → utf-8 → gbk → big5 → shift_jis → latin-1 顺序
    尝试解码, 取第一个成功者; 带 “(?)” 的结果是不完全可靠的猜测
    (latin-1 几乎不会失败, 仅作兜底);
  * 无 BOM 且前 8KB 含 NUL 的文件视为二进制, 跳过。

判定: us-ascii / utf-8 且无 BOM → OK; 其余(UTF-8 BOM、UTF-16/32、
gbk、big5 等) → 标记。

用法:
  python bom-encoding-check.py PATH... [-r] [--ext .py,.txt] [--exclude NAME]... [-q]

示例:
  python bom-encoding-check.py src -r            # 递归检查目录
  python bom-encoding-check.py src -r -q         # 只显示被标记的文件
  python bom-encoding-check.py a.py b.txt        # 检查指定文件

退出码: 0 = 全部 OK; 1 = 存在被标记的文件; 2 = 路径/IO 错误。
"""

import argparse
import os
import sys
from pathlib import Path

DEFAULT_EXCLUDES = {".git"}
UTF8_OK = {"us-ascii", "utf-8", "空文件"}

BOM_LIST = (
    (b"\xff\xfe\x00\x00", "UTF-32 LE", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "UTF-32 BE", "utf-32-be"),
    (b"\xef\xbb\xbf", "UTF-8", "utf-8-sig"),
    (b"\xff\xfe", "UTF-16 LE", "utf-16-le"),
    (b"\xfe\xff", "UTF-16 BE", "utf-16-be"),
)

CODECS = ("gbk", "big5", "shift_jis")


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


def looks_binary(data):
    return b"\x00" in data[:8192]


def detect_bom(data):
    """返回 (BOM 名称, BOM 字节) 或 (None, b"")。"""
    for sig, name, _codec in BOM_LIST:
        if data.startswith(sig):
            return name, sig
    return None, b""


def guess_encoding(data):
    """返回 (编码名, 是否可靠, 是否 UTF-8 兼容, 首个非 UTF-8 字节偏移或 None)。"""
    if not data:
        return "空文件", True, True, None
    try:
        data.decode("ascii")
        return "us-ascii", True, True, None
    except UnicodeDecodeError:
        pass
    bad_off = None
    try:
        data.decode("utf-8")
        return "utf-8", True, True, None
    except UnicodeDecodeError as exc:
        bad_off = exc.start
    for enc in CODECS:
        try:
            data.decode(enc)
            return f"{enc}(?)", False, False, bad_off
        except (UnicodeDecodeError, ValueError):
            continue
    return "latin-1(?)", False, False, bad_off


def hsize(num):
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def analyze(path):
    """返回 (状态, 编码名, BOM 名, 字节数, 备注); 状态: ok/flagged/binary。"""
    data = path.read_bytes()
    bom_name, bom_sig = detect_bom(data)
    if bom_name is None and looks_binary(data):
        return "binary", "二进制", None, len(data), "前 8KB 含 NUL"
    size = len(data)
    if bom_name:
        codec = next(c for s, n, c in BOM_LIST if n == bom_name)
        try:
            data[len(bom_sig):].decode(codec)
            note = "BOM 有效: 余下字节解码正常"
        except UnicodeDecodeError as exc:
            note = f"BOM 可疑: 余下字节解码异常(偏移 {exc.start})"
        return "flagged", codec, bom_name, size, note
    enc, sure, utf8_ok, bad_off = guess_encoding(data)
    note = ""
    if bad_off is not None:
        note = f"首个非 UTF-8 字节偏移 {bad_off}"
    if not sure:
        note = (note + "; " if note else "") + "推测结果, 不完全可靠"
    return ("ok" if utf8_ok else "flagged"), enc, None, size, note


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="按字节特征猜测文本文件编码, 标记非 UTF-8 及带 BOM 的文件")
    ap.add_argument("paths", nargs="+", metavar="PATH", help="文件或目录(可多个)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="递归遍历目录(默认只看一层)")
    ap.add_argument("--ext", default="", metavar="EXTS",
                    help="只检查这些扩展名(逗号分隔, 如 .py,.txt); 显式给出的文件不受限")
    ap.add_argument("--exclude", action="append", default=[], metavar="NAME",
                    help="按名字跳过的目录或文件(可多次); 默认已跳过 .git")
    ap.add_argument("-q", "--quiet", action="store_true", help="只显示被标记的文件与汇总")
    args = ap.parse_args(argv)

    excludes = DEFAULT_EXCLUDES | set(args.exclude)
    files, errors = collect(args.paths, args.recursive, parse_exts(args.ext), excludes)

    n_ok = n_bad = n_skip = 0
    for f in files:
        try:
            status, enc, bom, size, note = analyze(f)
        except OSError as exc:
            errors.append(f"{f}: {exc}")
            continue
        if status == "binary":
            n_skip += 1
            if not args.quiet:
                print(f"[跳过] {f}  编码=二进制  {hsize(size)}  ({note})")
            continue
        if status == "ok":
            n_ok += 1
            if not args.quiet:
                extra = f"  ({note})" if note else ""
                print(f"[OK  ] {f}  编码={enc}  BOM=无  {hsize(size)}{extra}")
        else:
            n_bad += 1
            print(f"[标记] {f}  编码={enc}  BOM={bom or '无'}  {hsize(size)}  ({note})")

    print(f"检查完成: 文本文件 {n_ok + n_bad} 个, OK {n_ok} 个, 标记 {n_bad} 个, "
          f"跳过二进制 {n_skip} 个")
    if errors:
        print(f"发生 {len(errors)} 个错误:", file=sys.stderr)
        for msg in errors:
            print(f"  {msg}", file=sys.stderr)
        return 2
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
