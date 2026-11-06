#!/usr/bin/env python3
r"""重复文件清理脚本生成器 (dup-delete-script)。

用途:
    扫描一个或多个目录, 按内容哈希找出完全相同的重复文件; 工具本身绝不删除,
    而是生成一份供人工审阅的删除 (rm/del) 或移动 (mv/move) 命令脚本。
    默认脚本中每条命令都带 “# ” 前缀 (bash) 或 “REM ” 前缀 (bat),
    人工审阅后去掉前缀即可执行; 也可用 --active 直接生成未注释的可执行脚本。

示例:
    python dup-delete-script.py "K:\data" -o cleanup.sh
    python dup-delete-script.py "K:\data" --mode move --move-to "K:\trash" -o move.sh
    python dup-delete-script.py "K:\a" "K:\b" --keep newest --format bat -o cleanup.bat

退出码:
    0 = 正常 (含未发现重复); 2 = 参数或目录错误。
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime

BAT_COMMENT = "REM "


def _setup_stdio():
    """Windows 下把输出流固定为 UTF-8, 避免中文输出在管道中触发编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def human_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def collect_files(roots):
    """递归收集所有普通文件的绝对路径, 跨根去重, 路径排序保证结果稳定。"""
    seen = set()
    out = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in sorted(filenames):
                p = os.path.join(dirpath, name)
                try:
                    key = os.path.realpath(p)
                except OSError:
                    key = p
                if key in seen:
                    continue
                seen.add(key)
                out.append(p)
    return out


def hash_file(path, alg="sha256", chunk=1 << 20):
    h = hashlib.new(alg)
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def find_dup_groups(files, hash_alg, include_empty):
    """按 大小分桶 -> 内容哈希 分组, 返回 [(路径列表, 大小, 摘要), ...]。"""
    by_size = {}
    for p in files:
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_size == 0 and not include_empty:
            continue
        by_size.setdefault(st.st_size, []).append(p)
    groups = []
    for size, paths in sorted(by_size.items()):
        if len(paths) < 2:
            continue
        by_hash = {}
        for p in paths:
            try:
                digest = hash_file(p, hash_alg)
            except OSError:
                continue
            by_hash.setdefault(digest, []).append(p)
        for digest, ps in sorted(by_hash.items()):
            if len(ps) >= 2:
                groups.append((sorted(ps), size, digest))
    groups.sort(key=lambda g: (-(g[1] * (len(g[0]) - 1)), g[0][0]))
    return groups


def pick_keeper(paths, keep):
    """按策略选出每组保留的文件 (paths 已排序)。"""
    if keep == "first":
        return paths[0]

    def mtime(p):
        try:
            return os.stat(p).st_mtime
        except OSError:
            return 0.0

    if keep == "oldest":
        return min(paths, key=lambda p: (mtime(p), p))
    return max(paths, key=lambda p: (mtime(p), p))


def sh_quote(path):
    """bash 单引号转义, 并统一成正斜杠 (Git Bash/Windows API 都接受)。"""
    p = path.replace("\\", "/").replace("'", "'\\''")
    return "'" + p + "'"


def build_bash(groups, mode, move_to, keep, active, now_str):
    redundant = sum(len(ps) - 1 for ps, _, _ in groups)
    freed = sum(size * (len(ps) - 1) for ps, size, _ in groups)
    lines = [
        "#!/usr/bin/env bash",
        f"# 由 dup-delete-script.py 生成于 {now_str}",
        f"# 重复组: {len(groups)}  冗余文件: {redundant}  预计可释放: {human_size(freed)}",
        f"# 模式: {mode}  保留策略: keep {keep}",
        "# 警告: 请人工审阅后再执行!"
        + ("" if active else "  (所有命令已注释, 去掉行首 '# ' 后执行; 或用 --active 重新生成)"),
        "set -euo pipefail",
    ]
    used_names = set()
    if mode == "move" and groups:
        stmt = f"mkdir -p {sh_quote(os.path.abspath(move_to))}"
        lines += ["", stmt if active else "# " + stmt]
    for idx, (paths, size, digest) in enumerate(groups, 1):
        keeper = pick_keeper(paths, keep)
        lines += ["", f"# ---- 组 {idx}: sha256={digest[:16]}  大小 {human_size(size)}  保留: {keeper}"]
        for p in paths:
            if p == keeper:
                continue
            if mode == "delete":
                cmd = f"rm -v -- {sh_quote(p)}"
            else:
                base = os.path.basename(p)
                cand = base
                stem, ext = os.path.splitext(base)
                k = 1
                while cand.lower() in used_names:
                    k += 1
                    cand = f"{stem}_{k}{ext}"
                used_names.add(cand.lower())
                dst = os.path.join(os.path.abspath(move_to), cand)
                cmd = f"mv -v -- {sh_quote(p)} {sh_quote(dst)}"
            lines.append(cmd if active else "# " + cmd)
    lines.append("")
    return "\n".join(lines)


def build_bat(groups, mode, move_to, keep, active, now_str):
    redundant = sum(len(ps) - 1 for ps, _, _ in groups)
    freed = sum(size * (len(ps) - 1) for ps, size, _ in groups)

    def com(line):
        return line if active else BAT_COMMENT + line

    lines = [
        "@echo off",
        "chcp 65001 >nul",
        f"REM generated by dup-delete-script.py at {now_str}",
        f"REM groups: {len(groups)}  redundant files: {redundant}  space to free: {human_size(freed)}",
        f"REM mode: {mode}  keep: {keep}",
        "REM WARNING: review before running!"
        + ("" if active else "  (every command is commented with 'REM ', remove the prefix to enable)"),
    ]
    used_names = set()
    if mode == "move" and groups:
        lines += ["", com(f'mkdir "{os.path.abspath(move_to)}"')]
    for idx, (paths, size, digest) in enumerate(groups, 1):
        keeper = pick_keeper(paths, keep)
        lines += ["", f"REM ---- group {idx}: sha256={digest[:16]}  size {human_size(size)}  keep: {keeper}"]
        for p in paths:
            if p == keeper:
                continue
            if mode == "delete":
                lines.append(com(f'del /f "{p}"'))
            else:
                base = os.path.basename(p)
                cand = base
                stem, ext = os.path.splitext(base)
                k = 1
                while cand.lower() in used_names:
                    k += 1
                    cand = f"{stem}_{k}{ext}"
                used_names.add(cand.lower())
                dst = os.path.join(os.path.abspath(move_to), cand)
                lines.append(com(f'move /y "{p}" "{dst}"'))
    lines.append("")
    return "\r\n".join(lines)


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog="dup-delete-script",
        description="找出重复文件, 生成供人工审阅的删除/移动命令脚本 (不直接删除)。",
    )
    ap.add_argument("dirs", nargs="+", metavar="目录")
    ap.add_argument("-o", "--output", help="脚本输出路径 (缺省打印到 stdout)")
    ap.add_argument("--mode", choices=("delete", "move"), default="delete",
                    help="delete=生成 rm/del 命令, move=生成 mv/move 命令 (默认 delete)")
    ap.add_argument("--move-to", help="mode=move 时的目标目录")
    ap.add_argument("--keep", choices=("first", "oldest", "newest"), default="first",
                    help="每组保留哪个文件 (默认 first=路径排序第一个)")
    ap.add_argument("--format", choices=("bash", "bat"), default="bash",
                    help="脚本格式 (默认 bash, 适配 Git Bash)")
    ap.add_argument("--active", action="store_true",
                    help="生成未注释的可执行命令 (默认全部注释, 强制人工审阅)")
    ap.add_argument("--include-empty", action="store_true", help="包含 0 字节文件的重复组")
    ap.add_argument("--hash-alg", default="sha256", help="哈希算法 (默认 sha256)")
    args = ap.parse_args(argv)

    if args.mode == "move" and not args.move_to:
        ap.error("--mode move 需要同时指定 --move-to")
    try:
        hashlib.new(args.hash_alg)
    except Exception:
        ap.error(f"未知哈希算法: {args.hash_alg}")

    roots = []
    for d in args.dirs:
        r = os.path.abspath(d)
        if not os.path.isdir(r):
            print(f"错误: 目录不存在: {r}", file=sys.stderr)
            return 2
        roots.append(r)

    files = collect_files(roots)
    groups = find_dup_groups(files, args.hash_alg, args.include_empty)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    redundant = sum(len(ps) - 1 for ps, _, _ in groups)
    freed = sum(size * (len(ps) - 1) for ps, size, _ in groups)

    if args.format == "bash":
        script = build_bash(groups, args.mode, args.move_to, args.keep, args.active, now_str)
        enc, newline = "utf-8", "\n"
    else:
        script = build_bat(groups, args.mode, args.move_to, args.keep, args.active, now_str)
        enc, newline = "utf-8", "\r\n"

    if args.output:
        out_path = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding=enc, newline=newline) as f:
            f.write(script)
        print(f"已生成脚本: {out_path}")
    else:
        sys.stdout.write(script)

    print(f"重复组: {len(groups)}  冗余文件: {redundant}  预计可释放: {human_size(freed)}")
    print(f"模式: {args.mode}  保留策略: keep {args.keep}  格式: {args.format}")
    if not groups:
        print("未发现重复文件, 脚本中没有任何删除/移动命令。")
    elif args.active:
        print("注意: 已按 --active 生成可执行命令, 执行前请务必审阅。")
    else:
        print("提醒: 命令已注释, 请人工审阅后去掉行首注释符再执行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
