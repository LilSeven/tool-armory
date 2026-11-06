#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""压缩包内容重复检测 (dup-archive-content) —— 不解压读取 zip/tar 成员清单找重复包。

用途:
    扫描目录(或给定的压缩包文件)中的 zip/tar 系压缩包, 只读取成员清单
    (成员名+大小), 完全不解压任何数据。以成员名集合的 Jaccard 重叠度衡量
    两个压缩包的清单相似程度: 成员名与大小完全一致即"内容清单相同";
    重叠度 >= 阈值(--min-overlap)视为"高度重叠", 便于清理重复下载的安装包。

示例命令:
    python -I dup-archive-content.py D:/downloads
    python -I dup-archive-content.py ./packs --min-overlap 0.5
    python -I dup-archive-content.py a.zip b.tar.gz --json

退出码: 0 正常(无论是否发现重复); 2 参数错误。
仅用 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
import zipfile

TAR_SUFFIXES = (".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar")
ZIP_SUFFIXES = (".zip", ".jar", ".war", ".whl", ".egg", ".apk", ".xpi")


def force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def archive_kind(path: str):
    name = os.path.basename(path).lower()
    for suf in TAR_SUFFIXES:
        if name.endswith(suf):
            return "tar"
    for suf in ZIP_SUFFIXES:
        if name.endswith(suf):
            return "zip"
    return None


def norm_name(name: str) -> str:
    """归一化成员名: 统一分隔符, 去掉 ./ 前缀与结尾的目录斜杠。"""
    name = name.replace("\\", "/").strip()
    while name.startswith("./"):
        name = name[2:]
    return name.rstrip("/")


def read_zip(path: str):
    out = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            nm = norm_name(info.filename)
            if nm:
                out.append((nm, int(info.file_size)))
    return out


def read_tar(path: str):
    out = []
    with tarfile.open(path, "r:*") as tf:
        for member in tf:
            if member.isdir():
                continue
            nm = norm_name(member.name)
            if nm:
                out.append((nm, int(member.size)))
    return out


def collect_targets(paths):
    targets = []
    for p in paths:
        if os.path.isdir(p):
            for dirpath, _dirs, files in os.walk(p):
                for name in files:
                    full = os.path.join(dirpath, name)
                    if archive_kind(full):
                        targets.append(full)
        elif os.path.isfile(p):
            targets.append(p)  # 显式指定的文件不做扩展名过滤
        else:
            print(f"警告: 路径不存在, 已跳过: {p}", file=sys.stderr)
    return sorted(set(os.path.abspath(t) for t in targets))


def read_one(path: str) -> dict:
    rec = {"path": path, "members": [], "error": None, "kind": None}
    kind = archive_kind(path)
    if kind is None:  # 显式指定的文件按内容嗅探
        try:
            if zipfile.is_zipfile(path):
                kind = "zip"
            elif tarfile.is_tarfile(path):
                kind = "tar"
        except OSError:
            kind = None
    rec["kind"] = kind
    if kind is None:
        rec["error"] = "不是可识别的 zip/tar 压缩包"
        return rec
    try:
        rec["members"] = read_zip(path) if kind == "zip" else read_tar(path)
    except Exception as exc:  # 损坏的压缩包等
        rec["error"] = f"{type(exc).__name__}: {exc}"
    return rec


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="dup-archive-content",
        description="不解压读取 zip/tar 成员清单, 找出内容清单相同或高度重叠的压缩包。",
    )
    ap.add_argument("paths", nargs="+", help="要扫描的目录或压缩包文件(可多个)")
    ap.add_argument("--min-overlap", type=float, default=0.8, metavar="RATIO",
                    help="判定高度重叠的 Jaccard 阈值 0~1 (默认 0.8)")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    return ap


def main(argv=None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    if not 0.0 <= args.min_overlap <= 1.0:
        print("错误: --min-overlap 必须在 0~1 之间", file=sys.stderr)
        return 2

    targets = collect_targets(args.paths)
    if not targets:
        print("未找到任何 zip/tar 压缩包")
        return 0

    records = [read_one(p) for p in targets]
    for r in records:
        if r["error"] is None:
            r["names"] = frozenset(n for n, _s in r["members"])
            r["sig"] = tuple(sorted(r["members"]))

    usable = [r for r in records if r["error"] is None and r["members"]]
    empty_ok = [r for r in records if r["error"] is None and not r["members"]]
    failed = [r for r in records if r["error"] is not None]

    # 完全相同组: 成员 (名, 大小) 有序序列完全一致
    by_sig: dict = {}
    for r in usable:
        by_sig.setdefault(r["sig"], []).append(r["path"])
    groups = sorted((sorted(v) for v in by_sig.values() if len(v) > 1),
                    key=lambda g: (-len(g), g[0]))
    shown_pairs = set()
    for g in groups:
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                shown_pairs.add(frozenset((g[i], g[j])))

    # 高度重叠对: 成员名集合的 Jaccard 重叠度
    pairs = []
    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            a, b = usable[i], usable[j]
            if frozenset((a["path"], b["path"])) in shown_pairs:
                continue
            union = len(a["names"] | b["names"])
            if union == 0:
                continue
            jac = len(a["names"] & b["names"]) / union
            if jac < args.min_overlap:
                continue
            pairs.append({
                "a": a["path"],
                "b": b["path"],
                "jaccard": round(jac, 4),
                "names_equal_sizes_differ": a["names"] == b["names"],
            })
    pairs.sort(key=lambda p: (-p["jaccard"], p["a"], p["b"]))

    if args.json:
        print(json.dumps({
            "archive_count": len(records),
            "min_overlap": args.min_overlap,
            "archives": [{"path": r["path"], "kind": r["kind"],
                          "member_count": len(r["members"]), "error": r["error"]}
                         for r in records],
            "identical_groups": groups,
            "overlap_pairs": pairs,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"压缩包总数: {len(records)} "
          f"(读取成功 {len(usable)}, 空包 {len(empty_ok)}, 读取失败 {len(failed)})")
    if groups:
        print()
        print("== 成员清单完全相同的组 (成员名+大小一致) ==")
        for gi, g in enumerate(groups, 1):
            first = next(r for r in usable if r["path"] == g[0])
            print(f"组 {gi}: {len(g)} 个包, 各 {len(first['members'])} 个成员")
            for p in g:
                print(f"  - {p}")
    if pairs:
        print()
        print(f"== 高度重叠的压缩包对 (Jaccard >= {args.min_overlap:.0%}) ==")
        for p in pairs:
            tag = "  [成员名相同但大小不同]" if p["names_equal_sizes_differ"] else ""
            print(f"  {p['jaccard'] * 100:6.1f}%  {p['a']}  <->  {p['b']}{tag}")
    if not groups and not pairs:
        print("未发现内容清单相同或高度重叠的压缩包。")
    if failed:
        print()
        print("== 读取失败 ==")
        for r in failed:
            print(f"  - {r['path']}: {r['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
