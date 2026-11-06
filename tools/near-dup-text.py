#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""近似重复文本检测 (near-dup-text) —— 提取文本特征并用 difflib 找高度相似文档。

用途:
    扫描目录(或给定文件列表)中的文本文件, 对内容做规范化(统一小写、压缩
    空白、忽略空行与 BOM)作为特征; 先按规范化文本的哈希直接识别"完全相同",
    其余候选对用 difflib.SequenceMatcher 计算相似度, 输出相似度 >= 阈值的
    文件对, 用于找出内容高度相似的文档副本。

说明:
    - 超过 --max-bytes 的文件只读前缀参与比对。
    - 相似度基于规范化文本; 哈希值相同的文件对不再做 SequenceMatcher (结果即 100%)。

示例命令:
    python -I near-dup-text.py D:/docs
    python -I near-dup-text.py ./notes --threshold 0.7 --ext .txt,.md
    python -I near-dup-text.py a.txt b.txt --json

退出码: 0 正常; 2 参数/路径错误。
仅用 Python 标准库。
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys

DEFAULT_EXTS = ".txt,.md,.rst,.log,.csv"


def force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def normalize(data: bytes) -> str:
    """提取文本特征: 去 BOM, 逐行去首尾空白、转小写、压缩连续空白, 丢弃空行。"""
    text = data.decode("utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line.strip().lower())
        if line:
            lines.append(line)
    return "\n".join(lines)


def parse_exts(spec: str) -> set:
    exts = set()
    for part in spec.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if not part.startswith("."):
            part = "." + part
        exts.add(part)
    return exts


def collect_targets(paths, exts):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for dirpath, _dirs, filenames in os.walk(p):
                for name in filenames:
                    if os.path.splitext(name)[1].lower() in exts:
                        files.append(os.path.join(dirpath, name))
        elif os.path.isfile(p):
            files.append(p)  # 显式指定的文件不做扩展名过滤
        else:
            print(f"警告: 路径不存在, 已跳过: {p}", file=sys.stderr)
    return sorted(set(os.path.abspath(f) for f in files))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="near-dup-text",
        description="提取文本特征并用 difflib 比对相似度, 找出内容高度相似的文档。",
    )
    ap.add_argument("paths", nargs="+", help="要扫描的目录或文本文件(可多个)")
    ap.add_argument("--threshold", type=float, default=0.85, metavar="RATIO",
                    help="判定高度相似的阈值 0~1 (默认 0.85)")
    ap.add_argument("--ext", default=DEFAULT_EXTS, metavar="LIST",
                    help=f"目录扫描时的文本扩展名 (默认 {DEFAULT_EXTS})")
    ap.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024, metavar="N",
                    help="单文件最多参与比对的字节数 (默认 2097152)")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    return ap


def main(argv=None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    if not 0.0 < args.threshold <= 1.0:
        print("错误: --threshold 必须在 (0, 1] 之间", file=sys.stderr)
        return 2
    exts = parse_exts(args.ext)
    if not exts:
        print("错误: --ext 未解析出任何扩展名", file=sys.stderr)
        return 2

    targets = collect_targets(args.paths, exts)
    metas = []
    for path in targets:
        meta = {"path": path, "error": None, "norm": "", "norm_sha": "", "raw_sha": ""}
        try:
            with open(path, "rb") as f:
                data = f.read(max(1, args.max_bytes))
        except OSError as exc:
            meta["error"] = str(exc)
            metas.append(meta)
            continue
        norm = normalize(data)
        meta["norm"] = norm
        meta["norm_sha"] = hashlib.sha256(norm.encode("utf-8")).hexdigest() if norm else ""
        meta["raw_sha"] = hashlib.sha256(data).hexdigest()
        metas.append(meta)

    usable = [m for m in metas if m["error"] is None and m["norm"]]
    skipped = ([m["path"] for m in metas if m["error"] is not None]
               + [m["path"] for m in metas if m["error"] is None and not m["norm"]])

    pairs = []
    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            a, b = usable[i], usable[j]
            if a["norm_sha"] == b["norm_sha"]:
                sim = 1.0
            else:
                la, lb = len(a["norm"]), len(b["norm"])
                # SequenceMatcher.ratio() 上界 2*min/(la+lb), 先用长度快速排除
                upper = 2.0 * min(la, lb) / (la + lb)
                if upper < args.threshold:
                    continue
                sm = difflib.SequenceMatcher(None, a["norm"], b["norm"], autojunk=False)
                if sm.quick_ratio() < args.threshold:
                    continue
                sim = sm.ratio()
            if sim >= args.threshold:
                pairs.append({
                    "a": a["path"],
                    "b": b["path"],
                    "similarity": round(sim, 4),
                    "identical_normalized": a["norm_sha"] == b["norm_sha"],
                    "identical_bytes": a["raw_sha"] == b["raw_sha"],
                })
    pairs.sort(key=lambda p: (-p["similarity"], p["a"], p["b"]))

    if args.json:
        print(json.dumps({
            "file_count": len(metas),
            "threshold": args.threshold,
            "files": [{"path": m["path"], "lines": m["norm"].count("\n") + 1 if m["norm"] else 0,
                       "error": m["error"]} for m in metas],
            "pairs": pairs,
            "skipped": skipped,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"文本文件总数: {len(metas)} (可比对 {len(usable)}, 跳过 {len(skipped)})")
    if pairs:
        print(f"相似文件对 (相似度 >= {args.threshold:.0%}):")
        for p in pairs:
            if p["identical_normalized"]:
                tag = "  [内容完全相同]"
            elif p["identical_bytes"]:
                tag = "  [字节级相同]"
            else:
                tag = ""
            print(f"  {p['similarity'] * 100:6.1f}%  {p['a']}  <->  {p['b']}{tag}")
        print(f"共发现 {len(pairs)} 对")
    else:
        print(f"未发现相似度 >= {args.threshold:.0%} 的文件对。")
    if skipped:
        print(f"(跳过 {len(skipped)} 个无法读取或无有效内容的文件)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
