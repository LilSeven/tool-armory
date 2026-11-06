#!/usr/bin/env python3
"""把 JSON 数组按每 N 个元素拆分为多个独立 JSON 文件，并可合并还原。

拆分: 输出 <前缀>001.json…（每个是含至多 N 个元素的 JSON 数组），并生成
<输出目录>/manifest.json 记录原始元素数与哈希。
合并: --join <目录> -o <输出.json> 按序合并分片数组还原（缺省校验元素数）。

用法:
    python split-json-array.py <输入.json> -n 100 [-o 输出目录]
    python split-json-array.py --join <分片目录> -o 合并结果.json
示例:
    python split-json-array.py users.json -n 50 -o chunks/
    python split-json-array.py --join chunks/ -o users_restored.json
退出码: 0 成功；2 参数/文件/JSON 错误；3 合并后元素数校验失败。
"""
import argparse
import hashlib
import json
import os
import sys


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def do_split(args) -> int:
    src = args.input
    if not src or not os.path.isfile(src):
        print("错误: 拆分模式需要有效的输入 JSON 文件", file=sys.stderr)
        return 2
    try:
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"错误: 无法读取/解析 JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(data, list):
        print("错误: 输入的顶层 JSON 必须是数组", file=sys.stderr)
        return 2
    if args.n <= 0:
        print("错误: -n 必须为正整数", file=sys.stderr)
        return 2

    out_dir = args.output or src + ".chunks"
    os.makedirs(out_dir, exist_ok=True)
    prefix = os.path.splitext(os.path.basename(src))[0]

    raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
    parts = []
    idx = 0
    for i in range(0, len(data), args.n):
        idx += 1
        name = f"{prefix}{idx:03d}.json"
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data[i:i + args.n], f, ensure_ascii=False, indent=2)
        parts.append({"file": name, "elements": len(data[i:i + args.n]),
                      "sha256": file_sha256(path)})
        print(f"写出 {name}  {len(data[i:i + args.n])} 个元素")

    manifest = {
        "tool": "split-json-array",
        "original_name": os.path.basename(src),
        "element_count": len(data),
        "chunk_size": args.n,
        "part_count": len(parts),
        "parts": parts,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"完成: {len(data)} 个元素 -> {len(parts)} 个分片, 目录 {out_dir}")
    return 0


def do_join(args) -> int:
    d = args.join
    if not os.path.isdir(d):
        print(f"错误: 分片目录不存在: {d}", file=sys.stderr)
        return 2
    mpath = os.path.join(d, "manifest.json")
    if os.path.isfile(mpath):
        with open(mpath, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        names = [p["file"] for p in manifest["parts"]]
        expected = manifest.get("element_count")
    else:
        names = sorted(
            n for n in os.listdir(d)
            if n.endswith(".json") and n != "manifest.json" and n[:3].isdigit()
        )
        if not names:
            print(f"错误: 目录中没有分片 JSON: {d}", file=sys.stderr)
            return 2
        expected = None

    merged = []
    for n in names:
        path = os.path.join(d, n)
        try:
            with open(path, "r", encoding="utf-8") as f:
                chunk = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"错误: 无法解析分片 {n}: {e}", file=sys.stderr)
            return 2
        if not isinstance(chunk, list):
            print(f"错误: 分片 {n} 不是 JSON 数组", file=sys.stderr)
            return 2
        merged.extend(chunk)
        print(f"已合并 {n}  {len(chunk)} 个元素")

    if expected is not None and len(merged) != expected:
        print(f"校验失败: 期望 {expected} 个元素, 实际 {len(merged)}", file=sys.stderr)
        return 3
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"合并完成: {args.output}  共 {len(merged)} 个元素"
          + ("  (元素数校验通过)" if expected is not None else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="按元素数拆分/合并 JSON 数组")
    ap.add_argument("input", nargs="?", help="输入 JSON 文件（拆分模式）")
    ap.add_argument("-n", type=int, default=100, help="每片元素数（默认 100）")
    ap.add_argument("-o", "--output", help="输出目录（拆分）或输出文件（--join）")
    ap.add_argument("--join", metavar="DIR", help="合并模式：分片所在目录")
    args = ap.parse_args()

    if args.join:
        if not args.output:
            print("错误: --join 模式必须用 -o 指定输出文件", file=sys.stderr)
            return 2
        return do_join(args)
    return do_split(args)


if __name__ == "__main__":
    sys.exit(main())
