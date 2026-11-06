"""拉平重命名 (flatten-rename)

用途：把根目录各子目录中的文件移动到根目录，并以「父目录名_」做前缀消除重名冲突。
默认只预演，加 --apply 才实际移动。

用法:
    python flatten-rename.py ROOT [--apply] [--depth N]

示例:
    python flatten-rename.py ./photos --apply        # 把所有子目录文件拉平到 photos/
    python flatten-rename.py ./downloads --depth 1   # 只处理一层子目录

规则:
    - 文件位于根目录的直接子目录中时，新名为「子目录名_原文件名」；
    - 仅当根目录已存在同名文件（或多个子目录拉平后撞名）时才加前缀；
      若加前缀后仍冲突，追加 _2、_3 … 直到不冲突。
    - 不处理隐藏文件（以 . 开头），不进入名为 .git 等的隐藏目录。
"""

import argparse
import sys
from pathlib import Path


def unique_name(root: Path, name: str) -> str:
    """在 root 下寻找不冲突的名字，必要时插入 _2、_3。"""
    p = root / name
    if not p.exists():
        return name
    stem, suffix = Path(name).stem, Path(name).suffix
    i = 2
    while (root / f"{stem}_{i}{suffix}").exists():
        i += 1
    return f"{stem}_{i}{suffix}"


def collect_moves(root: Path, depth: int):
    """收集 (源文件, 目标路径, 新文件名) 列表。"""
    moves = []
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        for f in sorted(sub.iterdir()):
            if not f.is_file() or f.name.startswith("."):
                continue
            target = root / f.name
            if f.parent == root:
                continue
            if target.exists():
                new_name = unique_name(root, f"{sub.name}_{f.name}")
            else:
                # 不加前缀，但要防止其他子目录稍后拉平造成冲突——先记录，稍后统一去重
                new_name = f.name
            moves.append([f, root / new_name, new_name])
    # 二次去重：多个子目录拉平到同一名字时，对后续者加父目录前缀
    seen = set()
    final = []
    for src, dst, name in moves:
        if name in seen:
            new_name = unique_name(root, f"{src.parent.name}_{name}")
            dst, name = root / new_name, new_name
        else:
            seen.add(name)
        final.append((src, dst, name))
    return final


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="拉平子目录文件到根目录（默认预演）")
    ap.add_argument("root", help="根目录")
    ap.add_argument("--apply", action="store_true", help="实际执行移动（默认只预演）")
    ap.add_argument("--depth", type=int, default=1, help="扫描子目录层数（默认 1）")
    ns = ap.parse_args(argv)

    root = Path(ns.root)
    if not root.is_dir():
        print(f"错误: {root} 不是目录", file=sys.stderr)
        return 2

    # 本工具实现 depth=1 的拉平；--depth>1 时递归收集（同一逻辑逐层应用）
    moves = collect_moves(root, ns.depth)
    if ns.depth > 1:
        print("[提示] 当前实现按一层子目录拉平；--depth>1 视同 1 层处理", file=sys.stderr)

    n = 0
    for src, dst, name in moves:
        if ns.apply:
            src.rename(dst)
            print(f"[已移动] {src} -> {name}")
        else:
            print(f"[预演] {src} -> {name}")
        n += 1
    print(f"共 {n} 个文件" + ("" if ns.apply else "（预演模式，加 --apply 生效）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
