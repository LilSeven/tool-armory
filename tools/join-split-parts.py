#!/usr/bin/env python3
"""按序合并分卷文件还原原始文件，可选校验清单中的 SHA-256。

配合 split-by-size.py 使用：把 part001、part002… 按序拼接还原。若目录中存在
manifest.json 且未指定 --manifest no，则校验整体 SHA-256（以及 --strict 时
逐分卷校验），不匹配则报错返回码 3。也可不带清单只按通配合并任意分卷。

用法:
    python join-split-parts.py <分卷目录或第一个分卷> -o <还原输出>
示例:
    python join-split-parts.py parts/ -o restored.bin
    python join-split-parts.py big.bin.parts -o restored.bin --strict
选项:
    -o, --output    还原后的输出文件
    --manifest      yes(默认)/no：是否查找并使用 manifest.json 校验
    --strict        逐分卷也校验 SHA-256，任何不匹配即失败
退出码: 0 成功；2 参数/文件错误；3 哈希校验失败。
"""
import argparse
import hashlib
import json
import os
import re
import sys

CHUNK = 1024 * 1024


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="按序合并分卷还原原始文件")
    ap.add_argument("src", help="分卷目录，或第一个分卷文件路径")
    ap.add_argument("-o", "--output", required=True, help="输出文件路径")
    ap.add_argument("--manifest", choices=["yes", "no"], default="yes",
                    help="是否使用 manifest.json 校验")
    ap.add_argument("--strict", action="store_true", help="逐分卷校验哈希")
    args = ap.parse_args()

    src = args.src
    manifest = None
    if os.path.isdir(src):
        mpath = os.path.join(src, "manifest.json")
        if args.manifest == "yes" and os.path.isfile(mpath):
            with open(mpath, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            names = [p["file"] for p in manifest["parts"]]
            part_paths = [os.path.join(src, n) for n in names]
        else:
            pat = re.compile(r"^part\d+$")
            names = sorted(
                n for n in os.listdir(src)
                if pat.match(n) and os.path.isfile(os.path.join(src, n))
            )
            if not names:
                print(f"错误: 目录中没有 partNNN 分卷: {src}", file=sys.stderr)
                return 2
            part_paths = [os.path.join(src, n) for n in names]
    elif os.path.isfile(src):
        d = os.path.dirname(os.path.abspath(src))
        m = re.match(r"^(.*?)(\d+)$", os.path.basename(src))
        prefix, start = (m.group(1), int(m.group(2))) if m else (os.path.basename(src), 1)
        part_paths = []
        idx = start
        while True:
            p = os.path.join(d, f"{prefix}{idx:03d}")
            if not os.path.isfile(p):
                break
            part_paths.append(p)
            idx += 1
    else:
        print(f"错误: 输入不存在: {src}", file=sys.stderr)
        return 2

    # 逐分卷校验（--strict 且有清单时）
    if manifest and args.strict:
        info = {p["file"]: p for p in manifest["parts"]}
        for p in part_paths:
            name = os.path.basename(p)
            want = info.get(name, {}).get("sha256")
            if want and sha256_file(p) != want:
                print(f"校验失败: 分卷 {name} 的 SHA-256 不匹配", file=sys.stderr)
                return 3

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    total = 0
    with open(args.output, "wb") as fout:
        for p in part_paths:
            with open(p, "rb") as fin:
                while True:
                    b = fin.read(CHUNK)
                    if not b:
                        break
                    fout.write(b)
                    total += len(b)
            print(f"已合并 {os.path.basename(p)}")

    print(f"合并完成: {args.output}  共 {total} 字节")

    # 整体校验
    if manifest:
        if manifest.get("original_size") not in (None, total):
            print(f"校验失败: 期望大小 {manifest['original_size']} != 实际 {total}",
                  file=sys.stderr)
            return 3
        got = sha256_file(args.output)
        want = manifest.get("original_sha256")
        if want and got != want:
            print(f"校验失败: 整体 SHA-256 不匹配 (期望 {want[:12]}..., 实际 {got[:12]}...)",
                  file=sys.stderr)
            return 3
        print("SHA-256 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
