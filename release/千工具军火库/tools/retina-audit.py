#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Retina 配对审计 (retina-audit) —— 检查一组图标文件是否满足 @1x/@2x/@3x 尺寸配对关系并指出缺失项。

分组规则（iOS 约定）: icon.png 与 icon@1x.png 记为 1x，icon@2x.png 记为 2x，icon@3x.png 记为 3x；
同一目录下基础名相同的文件归为一组。逐组报告:
  - 各倍率的像素尺寸（PNG/JPEG/GIF/BMP 自动读出，其余格式记为“?”）;
  - 缺失的倍率;
  - 尺寸比例是否正确（2x 应为 1x 的 2 倍、3x 为 3 倍，容差 ±1 像素）;
  - 同一倍率重复提供的情况。

示例命令:
    python retina-audit.py ./icons                       # 审计目录（含子目录）
    python retina-audit.py a.png a@2x.png a@3x.png       # 审计指定文件
    python retina-audit.py ./icons --scales 1x,2x        # 只要求配齐 1x/2x
    python retina-audit.py ./icons --no-ratio-check      # 仅检查配对存在性，不做比例校验

退出码: 0 全部配齐且比例一致; 1 存在缺失/比例不符/重复; 2 输入错误（路径不存在、未找到图标文件）。
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}
SCALE_RE = re.compile(r"^(?P<base>.+)@(?P<n>\d+)x$", re.IGNORECASE)
RATIO_TOL = 1  # 比例校验允许的像素误差


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


# ---------- 分组与检查 ----------

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


def build_groups(files):
    """返回 {(目录, 基础名小写): {"dir", "base", "entries": {倍率int: [(path, dim或None), ...]}}}"""
    groups = {}
    for f in files:
        m = SCALE_RE.match(f.stem)
        scale = int(m.group("n")) if m else 1
        base = m.group("base") if m else f.stem
        key = (str(f.parent), base.lower())
        g = groups.setdefault(key, {"dir": str(f.parent), "base": base, "entries": {}})
        g["entries"].setdefault(scale, []).append((f, read_image_size(f)))
    return groups


def ratio_problems(entries):
    """以最小已知尺寸的倍率为基准，检查其余文件尺寸是否符合倍率比例。"""
    problems = []
    ref = None
    for scale in sorted(entries):
        for path, dim in entries[scale]:
            if dim:
                ref = (scale, dim[0], dim[1])
                break
        if ref:
            break
    if ref is None:  # 全部尺寸未知，无法校验
        return problems
    ref_scale, rw, rh = ref
    for scale in sorted(entries):
        ew, eh = rw * scale / ref_scale, rh * scale / ref_scale
        for path, dim in entries[scale]:
            if not dim:
                continue
            if abs(dim[0] - ew) > RATIO_TOL or abs(dim[1] - eh) > RATIO_TOL:
                problems.append(
                    f"{path.name} 实际 {dim[0]}x{dim[1]}，按 {ref_scale}x={rw}x{rh} 推算 "
                    f"{scale}x 应为 {round(ew)}x{round(eh)}"
                )
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="retina-audit",
        description="检查一组图标文件是否满足 @1x/@2x/@3x 尺寸配对关系并指出缺失项。",
    )
    parser.add_argument("paths", nargs="+", help="图标目录或图标文件，可给多个")
    parser.add_argument("--scales", default="1x,2x,3x",
                        help="需要配齐的倍率，逗号分隔，默认 1x,2x,3x")
    parser.add_argument("--no-ratio-check", action="store_true",
                        help="跳过像素尺寸比例校验（只查配对存在性）")
    args = parser.parse_args(argv)

    wanted = sorted({int(x) for x in re.findall(r"(\d+)x", args.scales.lower())})
    if not wanted:
        print(f"错误: --scales 未解析出倍率: {args.scales!r}", file=sys.stderr)
        return 2

    try:
        files = collect_files(args.paths)
    except FileNotFoundError as exc:
        print(f"错误: 路径不存在: {exc}", file=sys.stderr)
        return 2
    if not files:
        print("错误: 未找到图标文件（支持 " + "/".join(sorted(IMG_EXTS)) + "）", file=sys.stderr)
        return 2

    groups = build_groups(files)
    bad = 0
    req = "/".join(f"{n}x" for n in wanted)
    print(f"扫描 {len(files)} 个文件，共 {len(groups)} 组（要求配齐: {req}）")

    for key in sorted(groups):
        g = groups[key]
        entries = g["entries"]
        present = sorted(entries)
        missing = [n for n in wanted if n not in entries]
        extra = [n for n in present if n not in wanted]
        dup = {n: ps for n, ps in entries.items() if len(ps) > 1}
        rprobs = [] if args.no_ratio_check else ratio_problems(entries)

        parts = []
        for n in present:
            dim = entries[n][0][1]
            parts.append(f"{n}x={dim[0]}x{dim[1]}" if dim else f"{n}x=?")
        detail = "  ".join(parts)

        problems = []
        if missing:
            problems.append("缺少: " + ", ".join(f"{n}x" for n in missing))
        if extra:
            problems.append("多余倍率: " + ", ".join(f"{n}x" for n in extra))
        for n, ps in sorted(dup.items()):
            problems.append(f"重复提供 {n}x（{len(ps)} 个: {', '.join(p.name for p, _ in ps)}）")
        problems.extend(rprobs)

        if problems:
            bad += 1
            print(f"[问题] {g['base']:<24} {detail}")
            for pr in problems:
                print(f"       - {pr}")
        else:
            print(f"[齐全] {g['base']:<24} {detail}")

    print()
    print(f"结论: {len(groups)} 组图标，{len(groups) - bad} 组齐全，{bad} 组存在问题。")
    return 1 if bad else 0


if __name__ == "__main__":
    _setup_stdout()
    sys.exit(main())
