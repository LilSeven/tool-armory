#!/usr/bin/env python3
"""encoding-scan 编码扫描报告：递归扫描目录，生成每个文件的编码清单（CSV），
并标出与主流编码不一致的文件。

用法:
  python encoding-scan.py <目录或文件...> [-o report.csv] [--mainstream utf-8,gbk] [--ext .txt,.md]

示例:
  python encoding-scan.py ./data -o encodings.csv
  python encoding-scan.py ./data --mainstream utf-8,gbk,big5 --ext .txt,.csv

说明:
  - 检测顺序：BOM（UTF-8/UTF-16LE/BE/UTF-32，UTF-16/32 文件常含 NUL 字节，
    故必须先查 BOM）→ 无 BOM 且含 NUL 字节视为二进制 → utf-8 严格解码 →
    gbk → big5 → latin-1 兜底。
  - 未指定 -o 时默认输出 encoding-report.csv（写到当前目录）。
  - CSV 列：path,encoding,bom,bytes,status,note。status=ok 表示检测到的编码在
    --mainstream 列表中（默认 utf-8,gbk）；否则 status=warn，即在 note 里标出
    “非主流编码”。
  - 本工具不修改被扫描的文件；输出 CSV 以 utf-8-sig 编码写入，方便 Excel 直接打开。
"""

import argparse
import csv
import sys
from pathlib import Path

BOMS = [
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
]


def detect(data: bytes):
    """返回 (encoding, bom 有无, 置信度说明)。"""
    # BOM 必须最先检查：UTF-16/32 内容通常含 NUL 字节，先查 NUL 会让 BOM 分支不可达
    for bom, name in BOMS:
        if data.startswith(bom):
            return name, True, f"检测到 {name} BOM"
    if b"\x00" in data:
        return "binary", False, "含 NUL 字节，疑似二进制文件"
    for name in ("utf-8", "gbk", "big5"):
        try:
            data.decode(name)
            return name, False, f"可按 {name} 严格解码"
        except (UnicodeDecodeError, ValueError):
            continue
    return "latin-1", False, "常见编码均失败，按 latin-1 兜底（可能是未知编码）"


def iter_files(paths, exts):
    for p in paths:
        path = Path(p)
        if path.is_file():
            yield path
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and (not exts or f.suffix.lower() in exts):
                    yield f
        else:
            print(f"跳过（不存在）: {path}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="递归扫描目录，生成文件编码清单 CSV")
    ap.add_argument("paths", nargs="+", help="文件或目录（目录会递归）")
    ap.add_argument("-o", "--output", default="encoding-report.csv",
                    help="输出 CSV 路径（默认 encoding-report.csv）")
    ap.add_argument("--mainstream", default="utf-8,gbk",
                    help="主流编码列表，逗号分隔（默认 utf-8,gbk）")
    ap.add_argument("--ext", default="", help="只扫描这些扩展名，逗号分隔")
    args = ap.parse_args(argv)

    mainstream = {e.strip().lower() for e in args.mainstream.split(",") if e.strip()}
    exts = {e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower()
            for e in args.ext.split(",") if e.strip()}

    rows = []
    warned = 0
    for f in iter_files(args.paths, exts):
        try:
            data = f.read_bytes()
        except OSError as e:
            rows.append([str(f), "unreadable", "", "", "warn", f"读取失败: {e}"])
            warned += 1
            continue
        enc, has_bom, note = detect(data)
        status = "ok" if enc.lower() in mainstream else "warn"
        if status == "warn":
            note = f"非主流编码（主流={args.mainstream}）: {note}"
            warned += 1
        rows.append([str(f), enc, "yes" if has_bom else "no", len(data), status, note])

    out_path = Path(args.output)
    with out_path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "encoding", "bom", "bytes", "status", "note"])
        w.writerows(rows)

    print(f"扫描 {len(rows)} 个文件，输出 {out_path}；其中 {warned} 个标记为 warn。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
