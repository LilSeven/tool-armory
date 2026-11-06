"""文件名截断 (truncate-rename)

用途：把过长的文件名截断到指定字节数以符合文件系统限制（如 FAT 的 255 字节、
跨平台传输的更小上限），保留扩展名。默认只预演，加 --apply 才实际重命名。

用法:
    python truncate-rename.py DIR --max-bytes N [--apply] [--ext EXT]

示例:
    python truncate-rename.py ./files --max-bytes 100            # 预演
    python truncate-rename.py ./files --max-bytes 100 --apply    # 实际执行

规则:
    - 以 UTF-8 编码计算文件名字节数（Windows 下 NTFS 按 UTF-16 计数，
      此工具按 UTF-8 提供保守的跨平台估计）；
    - 超过 --max-bytes 时截断文件名主干，末尾追加 ~1 防歧义，保留扩展名；
    - 若截断后仍冲突，追加 _2、_3 … 直到不冲突。
"""

import argparse
import sys
from pathlib import Path


def utf8_len(s: str) -> int:
    return len(s.encode("utf-8"))


def truncate_stem(stem: str, max_bytes: int, suffix: str) -> str:
    """把 stem 截断到 max_bytes - len(suffix) - len('~1') 字节，不切碎多字节字符。"""
    budget = max_bytes - utf8_len(suffix) - 2  # 预留 ~1
    raw = stem.encode("utf-8")
    if len(raw) <= budget:
        return stem
    cut = raw[:budget]
    # 回退到完整字符边界
    while cut and (cut[-1] & 0xC0) == 0x80:
        cut = cut[:-1]
    return cut.decode("utf-8", errors="ignore") + "~1"


def plan(path: Path, max_bytes: int) -> Path | None:
    name = path.name
    if utf8_len(name) <= max_bytes:
        return None
    suffix = path.suffix
    stem = path.stem
    new_stem = truncate_stem(stem, max_bytes, suffix)
    new_path = path.with_name(new_stem + suffix)
    i = 2
    while new_path.exists() and new_path != path:
        s = truncate_stem(stem, max_bytes, suffix) + f"_{i}"
        new_path = path.with_name(s + suffix)
        i += 1
    return new_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把过长文件名截断到指定字节数（默认预演）")
    ap.add_argument("dir", help="目标目录")
    ap.add_argument("--max-bytes", type=int, default=255, help="文件名最大字节数（默认 255）")
    ap.add_argument("--apply", action="store_true", help="实际执行重命名（默认只预演）")
    ns = ap.parse_args(argv)

    d = Path(ns.dir)
    if not d.is_dir():
        print(f"错误: {d} 不是目录", file=sys.stderr)
        return 2
    if ns.max_bytes < 8:
        print("错误: --max-bytes 太小", file=sys.stderr)
        return 2

    n = 0
    for p in sorted(d.iterdir()):
        if not p.is_file():
            continue
        new = plan(p, ns.max_bytes)
        if new is None or new == p:
            continue
        if ns.apply:
            p.rename(new)
            print(f"[已改名] {p.name} -> {new.name}")
        else:
            print(f"[预演] {p.name} -> {new.name}")
        n += 1
    print(f"共处理 {n} 个文件" + ("" if ns.apply else "（预演模式，加 --apply 生效）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
