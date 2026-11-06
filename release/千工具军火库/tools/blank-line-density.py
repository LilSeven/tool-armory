#!/usr/bin/env python3
"""空行密度分析 / blank line density.

统计各文本文件的空行与代码行(非空行)数量及比值, 识别两类极端文件:
  * 过度稀疏: 空行占比 > --sparse-th   (默认 0.50);
  * 过度紧凑: 空行占比 < --compact-th  (默认 0.05)
              且 非空行数 ≥ --min-code (默认 50, 避免误报小文件)。

空行 = 整行为空或只含空白字符。默认只分析常见代码/配置扩展名
(--ext 可覆盖), 并跳过 *.min.* 压缩文件与二进制文件。

用法:
  python blank-line-density.py PATH... [-r] [--ext .py,.js] [--exclude NAME]...
      [--sparse-th 0.5] [--compact-th 0.05] [--min-code 50] [-q]

示例:
  python blank-line-density.py src -r            # 全部文件按空行率排序
  python blank-line-density.py src -r -q         # 只显示被标记的文件
  python blank-line-density.py src -r --min-code 30 --sparse-th 0.4

退出码: 0 = 没有被标记的文件; 1 = 存在被标记的文件; 2 = 路径/IO 错误。
"""

import argparse
import fnmatch
import os
import sys
from pathlib import Path

DEFAULT_EXCLUDES = {".git"}
DEFAULT_EXTS = {
    ".py", ".pyw", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".c", ".h", ".cpp", ".cc", ".hpp", ".go", ".rs", ".cs",
    ".rb", ".php", ".kt", ".kts", ".swift", ".scala", ".dart", ".lua",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".sql", ".html", ".htm",
    ".css", ".scss", ".less", ".vue", ".xml", ".yml", ".yaml", ".toml",
    ".ini", ".cfg", ".conf",
}


def parse_exts(text):
    if not text:
        return None
    exts = set()
    for token in text.replace(",", " ").split():
        token = token.strip().lower()
        if token:
            exts.add("." + token.lstrip("."))
    return exts or None


def match_ext(path, exts):
    return True if exts is None else path.suffix.lower() in exts


def collect(roots, recursive, exts, excludes):
    """返回 (文件列表, 错误消息列表); 显式给出的文件不做扩展名过滤。"""
    files, errors = [], []
    for root in roots:
        p = Path(root)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            if recursive:
                for dirpath, dirnames, filenames in os.walk(p):
                    dirnames[:] = sorted(d for d in dirnames if d not in excludes)
                    for name in sorted(filenames):
                        if name in excludes:
                            continue
                        f = Path(dirpath, name)
                        if match_ext(f, exts):
                            files.append(f)
            else:
                try:
                    names = sorted(os.listdir(p))
                except OSError as exc:
                    errors.append(f"{p}: {exc}")
                    continue
                for name in names:
                    if name in excludes:
                        continue
                    f = p / name
                    if f.is_file() and match_ext(f, exts):
                        files.append(f)
        else:
            errors.append(f"路径不存在: {p}")
    return files, errors


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="统计各文件空行/代码行比值, 识别过度稀疏或过度紧凑的文件")
    ap.add_argument("paths", nargs="+", metavar="PATH", help="文件或目录(可多个)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="递归遍历目录(默认只看一层)")
    ap.add_argument("--ext", default="", metavar="EXTS",
                    help="只分析这些扩展名(逗号分隔, 覆盖默认代码扩展名集合); 显式给出的文件不受限")
    ap.add_argument("--exclude", action="append", default=[], metavar="NAME",
                    help="按名字跳过的目录或文件(可多次); 默认已跳过 .git")
    ap.add_argument("--sparse-th", type=float, default=0.5,
                    help="空行占比超过该值判为过度稀疏(默认 0.5)")
    ap.add_argument("--compact-th", type=float, default=0.05,
                    help="空行占比低于该值判为过度紧凑(默认 0.05)")
    ap.add_argument("--min-code", type=int, default=50,
                    help="过度紧凑判定要求的最小代码行数(默认 50)")
    ap.add_argument("-q", "--quiet", action="store_true", help="只显示被标记的文件与汇总")
    args = ap.parse_args(argv)

    excludes = DEFAULT_EXCLUDES | set(args.exclude)
    exts = parse_exts(args.ext) if args.ext else DEFAULT_EXTS
    files, errors = collect(args.paths, args.recursive, exts, excludes)

    rows = []
    n_skip_min = n_skip_bin = n_empty = 0
    for f in files:
        if fnmatch.fnmatch(f.name.lower(), "*.min.*"):
            n_skip_min += 1
            continue
        try:
            data = f.read_bytes()
        except OSError as exc:
            errors.append(f"{f}: {exc}")
            continue
        if b"\x00" in data[:8192]:
            n_skip_bin += 1
            continue
        text = data.decode("utf-8-sig", errors="replace")
        lines = text.splitlines()
        total = len(lines)
        blank = sum(1 for ln in lines if not ln.strip())
        code = total - blank
        ratio = (blank / total) if total else 0.0
        flag = ""
        if total:
            if ratio > args.sparse_th:
                flag = "过度稀疏"
            elif ratio < args.compact_th and code >= args.min_code:
                flag = "过度紧凑"
        else:
            n_empty += 1
        rows.append((f, total, blank, code, ratio, flag))

    rows.sort(key=lambda r: str(r[0]))
    rows.sort(key=lambda r: r[4], reverse=True)
    for f, total, blank, code, ratio, flag in rows:
        if args.quiet and not flag:
            continue
        print(f"[{flag or '正常'}] {f}: 总 {total} 行, 空行 {blank} "
              f"({ratio * 100:.1f}%), 代码 {code}")

    flagged = [r for r in rows if r[5]]
    n_sparse = sum(1 for r in flagged if r[5] == "过度稀疏")
    n_compact = len(flagged) - n_sparse
    avg = (sum(r[4] for r in rows) / len(rows)) if rows else 0.0
    print(f"分析完成: 文本文件 {len(rows)} 个, 平均空行率 {avg * 100:.1f}%; "
          f"标记 过度稀疏 {n_sparse} 个 / 过度紧凑 {n_compact} 个; "
          f"空文件 {n_empty} 个; 跳过 压缩文件 {n_skip_min} / 二进制 {n_skip_bin}")
    if errors:
        print(f"发生 {len(errors)} 个错误:", file=sys.stderr)
        for msg in errors:
            print(f"  {msg}", file=sys.stderr)
        return 2
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
