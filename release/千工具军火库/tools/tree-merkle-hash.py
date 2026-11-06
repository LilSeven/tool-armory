#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tree-merkle-hash.py —— 对文件分块构建 Merkle 树，输出各层哈希与树根，并可验证某个数据块的归属。

规则:
  * 叶哈希 = SHA256(块内容)；父哈希 = SHA256(左子哈希 || 右子哈希)。
  * 某层节点数为奇数时复制最后一个节点补齐（Bitcoin 风格）；文件末块可短于 --chunk-size。
  * 空文件视为单个空块，根 = SHA256(b"")。

子命令:
  build  <file> [--chunk-size N] [--max-hashes M] [--json]   构建整棵树，打印各层哈希与树根
  proof  <file> --index I [--chunk-size N] [--json]          生成第 I 块的包含证明
  verify (--leaf HEX | --file F [--chunk-size N]) --index I --proof SPEC --root HEX
      SPEC 自叶至根形如 "R:<hex>,L:<hex>"，前缀 L/R 表示兄弟哈希位于当前节点的右/左侧。

示例 (Git Bash):
  python -I tree-merkle-hash.py build data.bin --chunk-size 4096
  python -I tree-merkle-hash.py proof data.bin --index 1
  python -I tree-merkle-hash.py verify --index 1 --leaf <leaf_hex> --proof "R:<hex>,L:<hex>" --root <root_hex>

退出码: 0 成功（verify 即校验通过）；1 校验不通过；2 参数/文件/解析错误。
仅使用 Python 标准库。
"""

import argparse
import hashlib
import hmac
import json
import sys


def sha256(data):
    return hashlib.sha256(data).digest()


def read_chunk_hashes(path, chunk_size):
    hashes = []
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            hashes.append(sha256(chunk))
    if not hashes:  # 空文件按单个空块处理
        hashes = [sha256(b"")]
    return hashes


def build_levels(leaves):
    """自叶至根构建各层节点，最后一层仅含根。"""
    levels = [list(leaves)]
    cur = list(leaves)
    while len(cur) > 1:
        if len(cur) % 2 == 1:
            # 注意用新列表而非 cur.append()，避免原地修改已存入 levels 的上一层列表
            cur = cur + [cur[-1]]
        cur = [sha256(cur[i] + cur[i + 1]) for i in range(0, len(cur), 2)]
        levels.append(cur)
    return levels


def proof_for(levels, index):
    """返回第 index 块的包含证明 ["R:hex" | "L:hex", ...]，自叶至根。"""
    steps = []
    i = index
    for level in levels[:-1]:
        j = i ^ 1
        if j >= len(level):  # 奇数层末节点：兄弟即自身（复制补位）
            j = i
        side = "R" if i % 2 == 0 else "L"
        steps.append("%s:%s" % (side, level[j].hex()))
        i //= 2
    return steps


def parse_proof(spec):
    steps = [s.strip() for s in spec.split(",") if s.strip()]
    for step in steps:
        side, sep, _ = step.partition(":")
        if not sep or side not in ("L", "R"):
            raise ValueError("非法证明步骤 %r" % step)
    return steps


def fold(leaf, steps):
    cur = leaf
    for step in steps:
        side, _, hx = step.partition(":")
        sib = bytes.fromhex(hx)
        cur = sha256(sib + cur) if side == "L" else sha256(cur + sib)
    return cur


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv=None):
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        prog="tree-merkle-hash.py",
        description="对文件分块构建 Merkle 树并支持块归属证明")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="构建整棵树，打印各层哈希与树根")
    p_build.add_argument("file")
    p_build.add_argument("--chunk-size", type=int, default=4096)
    p_build.add_argument("--max-hashes", type=int, default=8,
                         help="每层最多打印多少个哈希，0 表示全部（默认 8）")
    p_build.add_argument("--json", action="store_true")

    p_proof = sub.add_parser("proof", help="生成某块的包含证明")
    p_proof.add_argument("file")
    p_proof.add_argument("--index", type=int, required=True)
    p_proof.add_argument("--chunk-size", type=int, default=4096)
    p_proof.add_argument("--json", action="store_true")

    p_verify = sub.add_parser("verify", help="校验包含证明是否归属给定树根")
    p_verify.add_argument("--index", type=int, required=True)
    p_verify.add_argument("--leaf", help="叶子哈希（十六进制），与 --file 二选一")
    p_verify.add_argument("--file", help="由文件与 --index/--chunk-size 推出叶子哈希")
    p_verify.add_argument("--chunk-size", type=int, default=4096)
    p_verify.add_argument("--proof", required=True)
    p_verify.add_argument("--root", required=True)

    args = ap.parse_args(argv)

    def die(msg):
        ap.error(msg)  # 以退出码 2 终止

    if args.cmd == "build":
        if args.chunk_size < 1:
            die("--chunk-size 必须 >= 1")
        try:
            leaves = read_chunk_hashes(args.file, args.chunk_size)
        except OSError as exc:
            die("读取文件失败: %s" % exc)
        levels = build_levels(leaves)
        if args.json:
            print(json.dumps({
                "file": args.file, "chunk_size": args.chunk_size,
                "chunks": len(leaves),
                "levels": [[h.hex() for h in lv] for lv in levels],
                "root": levels[-1][0].hex(),
            }, indent=2))
        else:
            print("file: %s" % args.file)
            print("chunk_size: %d" % args.chunk_size)
            print("chunks: %d" % len(leaves))
            for depth, level in enumerate(levels):
                print("level %d (%d nodes):" % (depth, len(level)))
                limit = len(level) if args.max_hashes == 0 else args.max_hashes
                shown = level[:limit]
                for idx, node in enumerate(shown):
                    print("  [%d] %s" % (idx, node.hex()))
                if len(shown) < len(level):
                    print("  ... (%d more)" % (len(level) - len(shown)))
            print("root: %s" % levels[-1][0].hex())
        return 0

    if args.cmd == "proof":
        if args.chunk_size < 1:
            die("--chunk-size 必须 >= 1")
        try:
            leaves = read_chunk_hashes(args.file, args.chunk_size)
        except OSError as exc:
            die("读取文件失败: %s" % exc)
        if not 0 <= args.index < len(leaves):
            die("--index 超出范围: 共 %d 块" % len(leaves))
        levels = build_levels(leaves)
        steps = proof_for(levels, args.index)
        if args.json:
            print(json.dumps({
                "file": args.file, "index": args.index,
                "leaf": leaves[args.index].hex(),
                "proof": steps, "root": levels[-1][0].hex(),
            }, indent=2))
        else:
            print("file: %s" % args.file)
            print("index: %d" % args.index)
            print("leaf: %s" % leaves[args.index].hex())
            print("proof: %s" % ",".join(steps))
            print("root: %s" % levels[-1][0].hex())
        return 0

    # verify
    if args.leaf and args.file:
        die("--leaf 与 --file 只能二选一")
    if not args.leaf and not args.file:
        die("必须提供 --leaf 或 --file")
    if args.chunk_size < 1:
        die("--chunk-size 必须 >= 1")
    if args.file:
        try:
            leaves = read_chunk_hashes(args.file, args.chunk_size)
        except OSError as exc:
            die("读取文件失败: %s" % exc)
        if not 0 <= args.index < len(leaves):
            die("--index 超出范围: 共 %d 块" % len(leaves))
        leaf = leaves[args.index]
    else:
        try:
            leaf = bytes.fromhex(args.leaf)
        except ValueError:
            die("--leaf 不是合法的十六进制")
    try:
        steps = parse_proof(args.proof)
        got = fold(leaf, steps)
        root = bytes.fromhex(args.root)
    except ValueError as exc:
        die("解析失败: %s" % exc)
    if hmac.compare_digest(got, root):
        print("VERIFY: OK —— 第 %d 块属于根 %s" % (args.index, root.hex()))
        return 0
    print("VERIFY: FAIL —— 第 %d 块不属于根 %s" % (args.index, root.hex()))
    return 1


if __name__ == "__main__":
    sys.exit(main())
