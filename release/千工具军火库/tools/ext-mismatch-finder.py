#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""扩展名伪装检测（ext-mismatch-finder）

对比文件头部魔数反映出的真实格式与其扩展名，找出"扩展名改错"或"把 A 格式
伪装成 B 格式"的文件，并输出汇总统计。

判定规则:
  * 扩展名在已知格式族表中（png/zip/pdf/gz/...）且与魔数识别结果一致  -> 匹配
  * 扩展名是常见文本扩展名（txt/md/py/json/...）且内容看起来是文本    -> 匹配
  * 其余: 魔数与扩展名不符 / 文本扩展名下是二进制 / 内容无法识别      -> 可疑

用法:
    python ext-mismatch-finder.py <目录或文件> [选项]

选项:
    --all     额外列出判定为"匹配"的文件
    --json    以 JSON 格式输出
    --hidden  包含以 . 开头的隐藏文件/目录

示例:
    python ext-mismatch-finder.py ./downloads
    python ext-mismatch-finder.py ./downloads --all --json

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

WHITESPACE = frozenset(b"\t\n\v\f\r")

# 扩展名 -> 期望的格式族
EXT_FAMILIES = {
    "png": "png", "jpg": "jpeg", "jpeg": "jpeg", "jpe": "jpeg",
    "gif": "gif", "bmp": "bmp", "webp": "webp", "ico": "ico",
    "tif": "tiff", "tiff": "tiff", "pdf": "pdf",
    "zip": "zip", "jar": "zip", "docx": "zip", "xlsx": "zip", "pptx": "zip",
    "apk": "zip", "epub": "zip",
    "gz": "gzip", "tgz": "gzip", "bz2": "bzip2", "xz": "xz", "zst": "zstd",
    "7z": "7z", "rar": "rar", "tar": "tar",
    "exe": "pe", "dll": "pe",
    "wav": "wav", "mp3": "mp3", "mp4": "mp4", "m4v": "mp4", "mov": "mp4",
    "avi": "avi", "ogg": "ogg", "flac": "flac",
    "sqlite": "sqlite", "db": "sqlite",
    "class": "java-class", "wasm": "wasm", "cab": "cab",
    "doc": "ole", "xls": "ole", "ppt": "ole", "msi": "ole",
    "so": "elf", "elf": "elf",
    "rtf": "rtf", "ps": "postscript",
}

# 常见"纯文本"扩展名
TEXT_EXTS = frozenset("""
    txt md rst log csv tsv json xml html htm css js ts jsx tsx py pyw rb php
    java c h cpp hpp cc cs go rs swift kt scala sh bash zsh bat cmd ps1
    ini cfg conf properties env yml yaml toml sql tex srt nfo
""".split())

# 识别标签 -> 格式族（用于与 EXT_FAMILIES 对齐比较）
LABEL_FAMILY = {
    "png": "png", "jpeg": "jpeg", "gif": "gif", "bmp": "bmp", "webp": "webp",
    "ico": "ico", "tiff-le": "tiff", "tiff-be": "tiff", "pdf": "pdf",
    "zip": "zip", "gzip": "gzip", "bzip2": "bzip2", "xz": "xz", "zstd": "zstd",
    "7z": "7z", "rar4": "rar", "rar5": "rar", "tar": "tar", "pe-exe": "pe",
    "elf": "elf", "wav": "wav", "avi": "avi", "mp4-like": "mp4",
    "mp3-id3": "mp3", "mp3-frame": "mp3", "ogg": "ogg", "flac": "flac",
    "sqlite3": "sqlite", "java-class": "java-class", "wasm": "wasm",
    "cab": "cab", "ole-cfb": "ole", "rtf": "rtf", "postscript": "postscript",
    "text": "text", "utf8-bom-text": "text", "utf16-text": "text",
    "utf16-be-text": "text", "utf32-le-text": "text", "utf32-be-text": "text",
    "riff-container": "riff-container", "zlib-stream": "zlib-stream",
    "empty": "empty", "unknown": "unknown",
}


def is_mostly_text(head, ctrl_threshold=0.05):
    if not head or 0 in head:
        return False
    ctrl = sum(1 for b in head if (b < 0x20 and b not in WHITESPACE) or b == 0x7F)
    return ctrl / len(head) <= ctrl_threshold


def detect_label(head):
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
    if head[0] == 0x78 and len(head) > 1 and ((head[0] << 8) | head[1]) % 31 == 0 \
            and not is_mostly_text(head):
        return "zlib-stream"
    if is_mostly_text(head):
        return "text"
    return "unknown"


def judge(ext, label):
    """返回 (verdict, detail)；verdict ∈ match/mismatch/unknown-content/no-ext/empty。"""
    family = LABEL_FAMILY.get(label, label)
    if family == "empty":
        return "empty", "空文件，无从比较"
    expected = EXT_FAMILIES.get(ext)
    if expected is not None:
        if family == expected:
            return "match", "扩展名与魔数一致（%s）" % expected
        if family in ("text", "unknown"):
            return "mismatch", "扩展名声称 %s(%s)，实际内容=%s" % (ext, expected, label)
        return "mismatch", "扩展名声称 %s(%s)，实际是 %s" % (ext, expected, label)
    if ext in TEXT_EXTS:
        if family == "text":
            return "match", "文本扩展名，内容为文本"
        if family == "unknown":
            return "unknown-content", "文本扩展名 %s，但内容无法识别" % ext
        return "mismatch", "文本扩展名 %s，实际是 %s（非文本）" % (ext, label)
    if ext == "":
        return "no-ext", "文件没有扩展名，不做比对"
    if family == "text":
        return "match", "内容为文本（扩展名 %s 未登记，视为可接受）" % ext
    if family == "unknown":
        return "unknown-content", "内容无法识别（扩展名 %s 未登记）" % ext
    return "mismatch", "内容是 %s，扩展名 %s 未登记，疑似伪装" % (label, ext)


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


def scan(root, head_size, include_hidden):
    rows = []
    errors = []
    for path in iter_files(root, include_hidden):
        try:
            with open(path, "rb") as fh:
                head = fh.read(head_size)
        except OSError as exc:
            errors.append({"path": path, "error": str(exc)})
            continue
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        label = detect_label(head)
        verdict, detail = judge(ext, label)
        rows.append({
            "path": path, "ext": ext, "detected": label,
            "verdict": verdict, "detail": detail,
        })
    return rows, errors


VERDICT_TITLE = {
    "mismatch": "可疑文件（魔数与扩展名不符 / 疑似伪装）",
    "unknown-content": "内容无法识别的文件",
    "no-ext": "无扩展名文件（跳过比对）",
    "empty": "空文件",
    "match": "匹配文件",
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ext-mismatch-finder",
        description="对比文件魔数与扩展名，找出扩展名改错或伪装成其他格式的文件。",
    )
    parser.add_argument("path", help="要扫描的目录（或单个文件）")
    parser.add_argument("--all", action="store_true", help="额外列出判定为匹配的文件")
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

    rows, errors = scan(args.path, max(264, 512), args.hidden)
    counts = Counter(r["verdict"] for r in rows)
    order = ["mismatch", "unknown-content", "no-ext", "empty", "match"]

    if args.json:
        payload = {
            "root": args.path,
            "total": len(rows),
            "summary": {k: counts.get(k, 0) for k in order},
            "issues": [r for r in rows if r["verdict"] in ("mismatch", "unknown-content")],
        }
        if args.all:
            payload["files"] = rows
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("扫描目标: %s   文件总数: %d（读取失败 %d）" % (args.path, len(rows), len(errors)))
    for v in order:
        subset = [r for r in rows if r["verdict"] == v]
        if not subset or (v == "match" and not args.all):
            continue
        print()
        print("%s（%d）:" % (VERDICT_TITLE[v], len(subset)))
        for r in subset:
            print("  %-28s ext=%-6s 实际=%-12s %s" % (
                trunc(r["path"], 28), r["ext"] or "-", r["detected"], r["detail"]))
    print()
    print("汇总: 匹配 %d | 可疑 %d | 未识别 %d | 无扩展名 %d | 空文件 %d" % (
        counts.get("match", 0), counts.get("mismatch", 0),
        counts.get("unknown-content", 0), counts.get("no-ext", 0),
        counts.get("empty", 0)))
    for err in errors:
        print("  [读取失败] %s: %s" % (err["path"], err["error"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
