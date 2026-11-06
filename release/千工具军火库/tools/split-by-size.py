#!/usr/bin/env python3
"""按字节分卷拆分大文件，生成含 SHA-256 哈希的清单（JSON）便于还原校验。

把输入文件切成指定大小的分卷 part001、part002…，并生成 <输出名>.manifest.json
清单，记录原始文件大小、SHA-256 以及每个分卷的大小与哈希，供
join-split-parts.py 还原时校验。

用法:
    python split-by-size.py <输入文件> -o <输出目录> -s <分卷字节数>
示例:
    python split-by-size.py big.bin -o parts/ -s 1048576
选项:
    -o, --output    输出目录（默认 <输入名>.parts/）
    -s, --size      每个分卷的字节数（默认 1048576，支持 10K/5M/1G 后缀）
退出码: 0 成功；2 参数或文件错误。
"""
import argparse
import hashlib
import json
import os
import sys

CHUNK = 1024 * 1024  # 读取哈希时的缓冲块大小


def parse_size(text: str) -> int:
    """把 '10K'、'5M'、'1G' 或纯数字解析成字节数。"""
    t = text.strip().upper()
    units = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
    if t and t[-1] in units:
        return int(float(t[:-1]) * units[t[-1]])
    return int(float(t))


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
    ap = argparse.ArgumentParser(description="按字节拆分文件并生成哈希清单")
    ap.add_argument("input", help="输入文件")
    ap.add_argument("-o", "--output", help="输出目录")
    ap.add_argument("-s", "--size", default="1048576", help="每卷字节数，如 1M")
    args = ap.parse_args()

    src = args.input
    if not os.path.isfile(src):
        print(f"错误: 输入文件不存在: {src}", file=sys.stderr)
        return 2
    try:
        part_size = parse_size(args.size)
    except ValueError:
        print(f"错误: 无效的分卷大小: {args.size}", file=sys.stderr)
        return 2
    if part_size <= 0:
        print("错误: 分卷大小必须为正数", file=sys.stderr)
        return 2

    out_dir = args.output or src + ".parts"
    os.makedirs(out_dir, exist_ok=True)

    src_size = os.path.getsize(src)
    parts = []
    num = 0
    with open(src, "rb") as fin:
        while True:
            data = fin.read(part_size)
            if not data:
                break
            num += 1
            name = f"part{num:03d}"
            ppath = os.path.join(out_dir, name)
            with open(ppath, "wb") as fout:
                fout.write(data)
            parts.append({
                "file": name,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
            print(f"写出 {name}  {len(data)} 字节")

    manifest = {
        "tool": "split-by-size",
        "original_name": os.path.basename(src),
        "original_size": src_size,
        "original_sha256": sha256_file(src),
        "part_size": part_size,
        "part_count": len(parts),
        "parts": parts,
    }
    mpath = os.path.join(out_dir, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"完成: 共 {len(parts)} 个分卷, 清单: {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
