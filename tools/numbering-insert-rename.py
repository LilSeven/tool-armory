"""定位置插入序号 (numbering-insert-rename)

用途：在文件名的指定位置插入递增序号（如 report_01_draft.txt），
支持零填充位数与自定义分隔符。默认只预演，加 --apply 才实际重命名。

用法:
    python numbering-insert-rename.py DIR [--pos N] [--start N] [--pad N]
                                         [--sep S] [--apply] [--sort mtime|name]

示例:
    python numbering-insert-rename.py ./docs                          # 在文件名开头插入 1,2,3...
    python numbering-insert-rename.py ./docs --pos 6 --sep _ --pad 2  # report_ 前插 -> 插在第 6 字符处
    python numbering-insert-rename.py ./docs --pos 0 --pad 3 --sep "" # 001report.txt
    python numbering-insert-rename.py ./docs --apply                  # 实际执行

参数:
    --pos N    插入位置（文件名主干中的字符偏移，0=最前；负数=从末尾倒数，默认 0）
    --start N  起始序号（默认 1）
    --pad N    零填充位数（默认 2，0 表示不填充）
    --sep S    序号与两侧的分隔符（默认 "_"）
"""

import argparse
import sys
from pathlib import Path


def build_name(stem: str, pos: int, num: int, pad: int, sep: str) -> str:
    s = str(num).zfill(pad) if pad > 0 else str(num)
    if pos <= 0:
        right = stem[len(sep):] if sep and stem.startswith(sep) else stem
        return s + sep + right
    pos = min(pos, len(stem))
    left, right = stem[:pos], stem[pos:]
    lead = "" if (sep and left.endswith(sep)) else sep   # 避免连续分隔符
    trail = "" if (not right or (sep and right.startswith(sep))) else sep
    return left + lead + s + trail + right


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="在文件名指定位置插入递增序号（默认预演）")
    ap.add_argument("dir", help="目标目录")
    ap.add_argument("--pos", type=int, default=0, help="插入位置（0=最前，负数=从末尾倒数）")
    ap.add_argument("--start", type=int, default=1, help="起始序号（默认 1）")
    ap.add_argument("--pad", type=int, default=2, help="零填充位数（0=不填充）")
    ap.add_argument("--sep", default="_", help="分隔符（默认 _）")
    ap.add_argument("--sort", choices=["name", "mtime"], default="name", help="排序依据")
    ap.add_argument("--apply", action="store_true", help="实际执行重命名（默认只预演）")
    ns = ap.parse_args(argv)

    d = Path(ns.dir)
    if not d.is_dir():
        print(f"错误: {d} 不是目录", file=sys.stderr)
        return 2

    files = [p for p in d.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime if ns.sort == "mtime" else p.name.lower())

    n = 0
    for i, p in enumerate(files, start=ns.start):
        new_name = build_name(p.stem, ns.pos, i, ns.pad, ns.sep) + p.suffix
        new_path = d / new_name
        if new_path == p:
            continue
        if new_path.exists():
            print(f"[冲突] {p.name} -> {new_name}: 目标已存在，跳过", file=sys.stderr)
            continue
        if ns.apply:
            p.rename(new_path)
            print(f"[已改名] {p.name} -> {new_name}")
        else:
            print(f"[预演] {p.name} -> {new_name}")
        n += 1
    print(f"共处理 {n} 个文件" + ("" if ns.apply else "（预演模式，加 --apply 生效）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
