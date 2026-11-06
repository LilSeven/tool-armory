#!/usr/bin/env python3
"""file-merge-planner —— 目录合并预演（dry-run，不改动任何文件）。

比较源目录与目标目录，预演"把源目录合并进目标目录"时每个源文件的命运:

    add           目标不存在同名相对路径文件     -> 将新增复制
    skip          双方文件大小与 SHA-1 均相同    -> 内容重复，跳过
    overwrite     双方都存在但内容不同          -> 按当前策略将覆盖目标
    coexist       策略 keep-both 时内容不同     -> 源文件改名为 <名>__from_src<扩展> 共存
    skip-existing 策略 skip-existing 时内容不同 -> 保留目标版本，源文件不复制

只检查源目录中的文件；目标目录中多出的文件不受影响。

用法:
    python file-merge-planner.py <源目录> <目标目录> [选项]

选项:
    --strategy {overwrite,keep-both,skip-existing}   内容冲突时的策略，默认 overwrite
    -q, --quiet        只输出各类计数，不逐个列文件
    --json             以 JSON 输出完整计划

示例:
    python file-merge-planner.py D:/new D:/old
    python file-merge-planner.py D:/new D:/old --strategy keep-both
    python file-merge-planner.py D:/new D:/old --json

退出码: 0 = 成功；2 = 目录不存在 / 源目标重叠等用法错误。
仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

ACTIONS = ("add", "skip", "overwrite", "coexist", "skip-existing")
DESCRIPTIONS = {
    "add": "目标缺失，将新增复制",
    "skip": "内容相同，将跳过",
    "overwrite": "内容不同，将覆盖目标",
    "coexist": "内容不同，源文件将改名共存",
    "skip-existing": "内容不同，将保留目标版本",
}


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def sha1_of(path: str, bufsize: int = 1 << 20) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(bufsize)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def iter_rel_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            yield os.path.relpath(full, root).replace("\\", "/"), full


def plan_merge(src: str, dst: str, strategy: str):
    plan = {action: [] for action in ACTIONS}
    errors = []
    for rel, sfull in iter_rel_files(src):
        try:
            dfull = os.path.join(dst, rel.replace("/", os.sep))
            if not os.path.exists(dfull):
                plan["add"].append({"file": rel, "size": os.path.getsize(sfull)})
            elif (os.path.getsize(sfull) == os.path.getsize(dfull)
                  and sha1_of(sfull) == sha1_of(dfull)):
                plan["skip"].append({"file": rel, "size": os.path.getsize(sfull)})
            elif strategy == "keep-both":
                base, ext = os.path.splitext(rel)
                plan["coexist"].append({"file": rel, "as": f"{base}__from_src{ext}"})
            elif strategy == "skip-existing":
                plan["skip-existing"].append({"file": rel})
            else:
                plan["overwrite"].append({
                    "file": rel,
                    "src_size": os.path.getsize(sfull),
                    "dst_size": os.path.getsize(dfull),
                })
        except OSError as exc:
            errors.append({"file": rel, "error": str(exc)})
    return plan, errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="file-merge-planner",
        description="预演两个目录合并：哪些文件会新增、跳过、覆盖或共存（不改动任何文件）。",
    )
    parser.add_argument("src", help="源目录")
    parser.add_argument("dst", help="目标目录")
    parser.add_argument("--strategy", choices=("overwrite", "keep-both", "skip-existing"),
                        default="overwrite", help="内容冲突时的策略，默认 overwrite")
    parser.add_argument("-q", "--quiet", action="store_true", help="只输出计数")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出计划")
    args = parser.parse_args(argv)

    src, dst = args.src, args.dst
    for label, path in (("源目录", src), ("目标目录", dst)):
        if not os.path.isdir(path):
            print(f"错误: {label}不是目录或不存在: {path}", file=sys.stderr)
            return 2
    src_abs = os.path.normcase(os.path.abspath(src))
    dst_abs = os.path.normcase(os.path.abspath(dst))
    if src_abs == dst_abs:
        print("错误: 源目录与目标目录是同一个目录。", file=sys.stderr)
        return 2
    if os.path.commonpath([src_abs, dst_abs]) == src_abs:
        print("错误: 目标目录在源目录内部，合并会自我复制，已中止。", file=sys.stderr)
        return 2

    plan, errors = plan_merge(src, dst, args.strategy)

    if args.json:
        payload = {
            "src": src,
            "dst": dst,
            "strategy": args.strategy,
            "summary": {action: len(items) for action, items in plan.items()},
            "plan": plan,
            "errors": errors,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"合并预演: {src}  ->  {dst}   (策略: {args.strategy}；dry-run，未做任何改动)")
    for action in ACTIONS:
        items = plan[action]
        if not items:
            continue
        print(f"  [{action:>13}] {len(items)} 个: {DESCRIPTIONS[action]}")
        if args.quiet:
            continue
        for item in items:
            if action == "overwrite":
                print(f"      {item['file']}  (源 {item['src_size']} B / 目标 {item['dst_size']} B)")
            elif action == "coexist":
                print(f"      {item['file']}  ->  共存为 {item['as']}")
            elif action in ("add", "skip"):
                print(f"      {item['file']}  ({item['size']} B)")
            else:
                print(f"      {item['file']}")
    if errors:
        print(f"  [        error] {len(errors)} 个文件无法读取:")
        for item in errors:
            print(f"      {item['file']}: {item['error']}")
    if sum(len(v) for v in plan.values()) == 0:
        print("  （源目录为空，无事可做）")
    return 0


if __name__ == "__main__":
    _force_utf8_stdio()
    sys.exit(main())
