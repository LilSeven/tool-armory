#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""魔数类型识别器（magic-type-classifier）

读取文件头部的魔数字节判断文件的真实类型，并输出一个目录下所有文件的
真实文件类型分布汇总。适合盘点来路不明的文件堆（扩展名被改坏、内容不明等）。

用法:
    python magic-type-classifier.py <目录或文件> [选项]

选项:
    --list      逐个列出每个文件的识别结果（默认只输出分布汇总）
    --top N     分布汇总最多显示前 N 类，0=全部（默认 15）
    --head N    读取文件头的字节数，默认 512（至少 264，否则无法识别 tar）
    --json      以 JSON 格式输出
    --hidden    包含以 . 开头的隐藏文件/目录

示例:
    python magic-type-classifier.py ./downloads
    python magic-type-classifier.py ./downloads --list --top 20
    python magic-type-classifier.py ./downloads --json

仅使用 Python 标准库。
退出码: 0=扫描完成; 1=路径不存在; 2=参数错误。
"""

import argparse
import json
import os
import sys
from collections import Counter

# (类型标签, 偏移, 魔数字节)；按声明顺序匹配，先命中先得
SIGNATURES = [
    ("png",           0, b"\x89PNG\r\n\x1a\n"),
    ("jpeg",          0, b"\xff\xd8\xff"),
    ("gif",           0, b"GIF87a"),
    ("gif",           0, b"GIF89a"),
    ("sqlite3",       0, b"SQLite format 3\x00"),
    ("pdf",           0, b"%PDF-"),
    ("zip",           0, b"PK\x03\x04"),
    ("zip",           0, b"PK\x05\x06"),
    ("zip",           0, b"PK\x07\x08"),
    ("7z",            0, b"7z\xbc\xaf\x27\x1c"),
    ("rar4",          0, b"Rar!\x1a\x07\x00"),
    ("rar5",          0, b"Rar!\x1a\x07\x01"),
    ("gzip",          0, b"\x1f\x8b"),
    ("bzip2",         0, b"BZh"),
    ("xz",            0, b"\xfd7zXZ\x00"),
    ("zstd",          0, b"\x28\xb5\x2f\xfd"),
    ("elf",           0, b"\x7fELF"),
    ("java-class",    0, b"\xca\xfe\xba\xbe"),
    ("wasm",          0, b"\x00asm"),
    ("cab",           0, b"MSCF"),
    ("ole-cfb",       0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    ("rtf",           0, b"{\\rtf"),
    ("postscript",    0, b"%!PS"),
    ("ogg",           0, b"OggS"),
    ("flac",          0, b"fLaC"),
    ("mp3-id3",       0, b"ID3"),
    ("tiff-le",       0, b"II*\x00"),
    ("tiff-be",       0, b"MM\x00*"),
    ("ico",           0, b"\x00\x00\x01\x00"),
    ("utf32-le-text", 0, b"\xff\xfe\x00\x00"),
    ("utf32-be-text", 0, b"\x00\x00\xfe\xff"),
    ("utf16-text",    0, b"\xff\xfe"),
    ("utf16-be-text", 0, b"\xfe\xff"),
    ("utf8-bom-text", 0, b"\xef\xbb\xbf"),
]

# 文本中常见的空白类控制字节，不算"可疑控制字符"
WHITESPACE = frozenset(b"\t\n\v\f\r")


def is_mostly_text(head, ctrl_threshold=0.05):
    """粗判一段字节是否像文本：非空、无 NUL 且控制字符占比不超过阈值。"""
    if not head or 0 in head:
        return False
    ctrl = sum(1 for b in head if (b < 0x20 and b not in WHITESPACE) or b == 0x7F)
    return ctrl / len(head) <= ctrl_threshold


def detect_label(head):
    """根据文件头字节返回类型标签。"""
    if not head:
        return "empty"
    for label, off, sig in SIGNATURES:
        if head[off:off + len(sig)] == sig:
            return label
    if head[:4] == b"RIFF":
        sub = head[8:12]
        if sub == b"WAVE":
            return "wav"
        if sub == b"AVI ":
            return "avi"
        if sub == b"WEBP":
            return "webp"
        return "riff-container"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "mp4-like"
    if len(head) >= 262 and head[257:262] == b"ustar":
        return "tar"
    if head[:2] == b"MZ" and 0 in head[:64]:
        return "pe-exe"
    if head[0] == 0xFF and len(head) > 1 and head[1] != 0xFF and (head[1] & 0xE0) == 0xE0:
        return "mp3-frame"
    # zlib 流: CMF=0x78 且 (CMF*256+FLG) % 31 == 0；同时排除纯文本误报
    if head[0] == 0x78 and len(head) > 1 and ((head[0] << 8) | head[1]) % 31 == 0 \
            and not is_mostly_text(head):
        return "zlib-stream"
    if is_mostly_text(head):
        return "text"
    return "unknown"


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


def scan(root, head_size, include_hidden):
    dist = Counter()
    rows = []
    errors = []
    for path in iter_files(root, include_hidden):
        try:
            with open(path, "rb") as fh:
                head = fh.read(head_size)
        except OSError as exc:
            errors.append({"path": path, "error": str(exc)})
            continue
        label = detect_label(head)
        dist[label] += 1
        rows.append({"path": path, "type": label, "head_bytes": len(head)})
    return dist, rows, errors


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="magic-type-classifier",
        description="读取文件头魔数字节判断真实类型，输出目录的真实文件类型分布。",
    )
    parser.add_argument("path", help="要扫描的目录（或单个文件）")
    parser.add_argument("--list", action="store_true", help="逐个列出每个文件的识别结果")
    parser.add_argument("--top", type=int, default=15, help="分布最多显示前 N 类，0=全部（默认 15）")
    parser.add_argument("--head", type=int, default=512, help="读取文件头的字节数（默认 512）")
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

    head_size = max(args.head, 264)  # 保证 tar（魔数在 257 偏移）可识别
    dist, rows, errors = scan(args.path, head_size, args.hidden)
    total = sum(dist.values())

    if args.json:
        payload = {
            "root": args.path,
            "total_files": total,
            "distribution": dict(dist.most_common()),
            "read_errors": errors,
        }
        if args.list:
            payload["files"] = rows
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("扫描目标: %s" % args.path)
    print("文件总数: %d（读取失败 %d）" % (total, len(errors)))
    if total == 0:
        print("没有可识别的文件。")
        return 0
    print()
    print("真实类型分布:")
    width = max(len(k) for k in dist)
    shown = dist.most_common() if args.top == 0 else dist.most_common(args.top)
    for label, count in shown:
        pct = count * 100.0 / total
        bar = "#" * max(1, int(round(pct / 4)))
        print("  %-*s %5d %6.1f%%  %s" % (width, label, count, pct, bar))
    if args.top != 0 and len(shown) < len(dist):
        rest = total - sum(c for _, c in shown)
        print("  %-*s %5d （其余类别）" % (width, "(其他)", rest))
    if args.list:
        print()
        print("逐文件结果:")
        for row in rows:
            print("  %-14s %s" % (row["type"], row["path"]))
    for err in errors:
        print("  [读取失败] %s: %s" % (err["path"], err["error"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
