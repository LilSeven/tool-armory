#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图标尺寸集审计 (icon-size-audit) —— 检查一组图标是否包含 16/32/48/64/256 等标准尺寸，列出缺失与多余。

扫描目录（含子目录）或指定文件，读取每个图标的像素尺寸:
  - PNG/JPEG/GIF/BMP: 按文件头解析出唯一尺寸;
  - .ico: 解析目录项，列出内嵌的全部尺寸。
与标准尺寸集（默认 16,32,48,64,256，可用 --standard 修改）对照:
  缺失 = 标准集中没有任何文件（或 .ico 内嵌项）覆盖的尺寸（导致退出码 1）;
  多余 = 存在但不属于标准集的尺寸（仅提示，不影响结论）。
非正方形图标按长边计入尺寸集并标注。

示例命令:
    python icon-size-audit.py ./icons                            # 审计目录
    python icon-size-audit.py app.ico                            # 检查单个 .ico 内嵌尺寸
    python icon-size-audit.py ./icons --standard 16,24,32,48,64,128,256

退出码: 0 标准尺寸全部覆盖; 1 有标准尺寸缺失; 2 输入错误（路径不存在、未找到图标文件）。
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".ico"}


def _setup_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


# ---------- 像素尺寸读取（按文件头解析，仅标准库） ----------

def _size_png(data: bytes):
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", data[16:24])
    return (w, h)


def _size_gif(data: bytes):
    if len(data) < 10 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    w, h = struct.unpack("<HH", data[6:10])
    return (w, h)


def _size_bmp(data: bytes):
    if len(data) < 26 or data[:2] != b"BM":
        return None
    dib = struct.unpack("<I", data[14:18])[0]
    if dib == 12:  # BITMAPCOREHEADER
        w, h = struct.unpack("<HH", data[18:22])
    else:
        w, h = struct.unpack("<ii", data[18:26])
    return (abs(w), abs(h))


def _size_jpeg(data: bytes):
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    i, n = 2, len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            return None
        m = data[i + 1]
        if m == 0xFF:                                        # 填充字节
            i += 1
            continue
        if m == 0x01 or m == 0xD8 or 0xD0 <= m <= 0xD7:      # 无长度字段的段
            i += 2
            continue
        if m in (0xD9, 0xDA):                                # EOI / SOS
            return None
        seglen = int.from_bytes(data[i + 2:i + 4], "big")
        if seglen < 2:
            return None
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):  # SOF 段
            if i + 9 > n:
                return None
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return (w, h)
        i += 2 + seglen
    return None


def read_image_size(path):
    """读取 PNG/JPEG/GIF/BMP 的像素尺寸 (宽, 高)，失败返回 None。"""
    try:
        with open(path, "rb") as fh:
            data = fh.read(32 * 1024 * 1024)
    except OSError:
        return None
    for fn in (_size_png, _size_gif, _size_bmp, _size_jpeg):
        try:
            size = fn(data)
        except Exception:
            size = None
        if size and size[0] > 0 and size[1] > 0:
            return size
    return None


def read_ico_sizes(path):
    """解析 .ico 目录项，返回内嵌尺寸列表 [(宽, 高), ...]，失败返回 None。"""
    try:
        with open(path, "rb") as fh:
            data = fh.read(32 * 1024 * 1024)
    except OSError:
        return None
    if len(data) < 6 or data[:4] != b"\x00\x00\x01\x00":  # 保留字 0 + 类型 1(icon)
        return None
    count = int.from_bytes(data[4:6], "little")
    sizes = []
    for k in range(count):
        off = 6 + 16 * k
        if off + 16 > len(data):
            break
        wb, hb = data[off], data[off + 1]  # 0 表示 256
        w = 256 if wb == 0 else wb
        h = 256 if hb == 0 else hb
        sizes.append((w, h))
    return sizes or None


# ---------- 扫描与报告 ----------

def collect_files(paths):
    files, missing = [], []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(
                f for f in sorted(p.rglob("*"))
                if f.is_file() and f.suffix.lower() in IMG_EXTS
            )
        elif p.is_file():
            files.append(p)
        else:
            missing.append(str(p))
    if missing:
        raise FileNotFoundError(", ".join(missing))
    return files


def parse_standard(text: str):
    try:
        sizes = sorted({int(x) for x in text.replace("，", ",").split(",") if x.strip()})
    except ValueError:
        raise ValueError(f"--standard 格式应为逗号分隔的整数，如 16,32,48,64,256，收到: {text!r}") from None
    if not sizes or any(s <= 0 for s in sizes):
        raise ValueError("--standard 中的尺寸必须为正整数")
    return sizes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="icon-size-audit",
        description="检查一组图标是否包含 16/32/48/64/256 等标准尺寸，列出缺失与多余。",
    )
    parser.add_argument("paths", nargs="+", help="图标目录、图标文件或 .ico 文件，可给多个")
    parser.add_argument("--standard", default="16,32,48,64,256",
                        help="标准尺寸集，逗号分隔，默认 16,32,48,64,256")
    args = parser.parse_args(argv)

    try:
        standard = parse_standard(args.standard)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    try:
        files = collect_files(args.paths)
    except FileNotFoundError as exc:
        print(f"错误: 路径不存在: {exc}", file=sys.stderr)
        return 2
    if not files:
        print("错误: 未找到图标文件（支持 " + "/".join(sorted(IMG_EXTS)) + "）", file=sys.stderr)
        return 2

    print(f"扫描 {len(files)} 个文件:")
    covered, unknown, nonsquare = set(), [], []
    for f in files:
        if f.suffix.lower() == ".ico":
            sizes = read_ico_sizes(f)
            if sizes:
                print(f"  {f.name:<28} .ico 内嵌 {len(sizes)} 个尺寸: "
                      + ", ".join(f"{w}x{h}" for w, h in sizes))
                for w, h in sizes:
                    if w != h:
                        nonsquare.append((f.name, w, h))
                    covered.add(max(w, h))
                continue
        dim = read_image_size(f)
        if dim is None:
            print(f"  {f.name:<28} 尺寸未知 [无法解析]")
            unknown.append(f.name)
        else:
            tag = "  [非正方形]" if dim[0] != dim[1] else ""
            print(f"  {f.name:<28} {dim[0]}x{dim[1]}{tag}")
            if dim[0] != dim[1]:
                nonsquare.append((f.name, dim[0], dim[1]))
            covered.add(max(dim))

    missing = [s for s in standard if s not in covered]
    extra = sorted(covered - set(standard))

    print()
    print(f"标准尺寸集: {', '.join(map(str, standard))}")
    print(f"已覆盖: {', '.join(str(s) for s in standard if s in covered) or '无'}")
    print(f"缺失: {', '.join(map(str, missing)) or '无'}")
    print(f"多余(不在标准集): {', '.join(map(str, extra)) or '无'}")
    if unknown:
        print(f"尺寸未知(未计入覆盖): {', '.join(unknown)}")
    if nonsquare:
        print("非正方形: " + ", ".join(f"{n}({w}x{h})" for n, w, h in nonsquare))
    print()
    if missing:
        print(f"结论: 不通过 —— 缺少标准尺寸: {', '.join(map(str, missing))}")
        return 1
    tail = "（另有非标准尺寸，见上）" if extra else ""
    print(f"结论: 通过 —— 标准尺寸全部覆盖。{tail}")
    return 0


if __name__ == "__main__":
    _setup_stdout()
    sys.exit(main())
