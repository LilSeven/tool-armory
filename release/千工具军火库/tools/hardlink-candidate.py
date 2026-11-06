#!/usr/bin/env python3
r"""硬链接合并候选建议 (hardlink-candidate)。

用途:
    找出 “内容完全相同、但没有互为硬链接” 的文件 (各自独立占用磁盘),
    输出硬链接化建议报告: 每组给出建议保留的文件、可合并的文件、
    预计可节约的空间, 以及参考命令 ln -f (仅建议, 本工具绝不执行)。
    跨磁盘卷 (st_dev 不同) 的组不会给出建议。

示例:
    python hardlink-candidate.py "K:\data"
    python hardlink-candidate.py "K:\data" --min-size 1048576
    python hardlink-candidate.py "K:\data" -o report.txt --script hl.sh

退出码:
    0 = 正常; 2 = 参数或目录错误。
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime


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


def sh_quote(path):
    """bash 单引号转义, 并统一成正斜杠 (Git Bash/Windows API 都接受)。"""
    p = path.replace("\\", "/").replace("'", "'\\''")
    return "'" + p + "'"


def collect_files(roots):
    """递归收集所有普通文件的绝对路径, 跨根去重, 排序保证结果稳定。"""
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


def pick_keeper(paths, keep, stats):
    if keep == "first":
        return min(paths)

    def mtime(p):
        st = stats.get(p)
        return st.st_mtime if st else 0.0

    if keep == "oldest":
        return min(paths, key=lambda p: (mtime(p), p))
    return max(paths, key=lambda p: (mtime(p), p))


def analyze(files, args, stats):
    """返回 (候选组列表, 已互为硬链接的组数)。

    候选组 = (大小, 摘要, dev, inode簇列表, keeper路径, 可节约字节)。
    """
    by_size = {}
    for p in files:
        try:
            st = os.stat(p)
        except OSError:
            continue
        stats[p] = st
        if st.st_size < args.min_size:
            continue
        if st.st_size > 0:
            by_size.setdefault(st.st_size, []).append(p)

    candidates = []
    already_groups = 0
    for size, paths in sorted(by_size.items()):
        if len(paths) < 2:
            continue
        by_hash = {}
        for p in paths:
            try:
                digest = hash_file(p, args.hash_alg)
            except OSError:
                continue
            by_hash.setdefault(digest, []).append(p)
        for digest, ps in sorted(by_hash.items()):
            if len(ps) < 2:
                continue
            by_dev = {}
            for p in ps:
                by_dev.setdefault(stats[p].st_dev, []).append(p)
            for dev, dps in sorted(by_dev.items()):
                clusters = {}
                for p in dps:
                    clusters.setdefault(stats[p].st_ino, []).append(p)
                clist = sorted(sorted(v) for v in clusters.values())
                if len(clist) <= 1:
                    already_groups += 1
                    continue
                keeper = pick_keeper(dps, args.keep, stats)
                candidates.append((size, digest, dev, clist, keeper, size * (len(clist) - 1)))
    candidates.sort(key=lambda c: (-c[5], c[4]))
    return candidates, already_groups


def build_report(roots, files_n, candidates, already_groups, stats, args):
    lines = []
    say = lines.append
    say("== 硬链接合并候选报告 ==")
    say("扫描根: " + "  ".join(roots))
    say(f"扫描文件数: {files_n}  (最小字节: {args.min_size}, 哈希: {args.hash_alg})")
    total_save = sum(c[5] for c in candidates)
    total_files = sum(sum(len(c) for c in clist) for _s, _d, _dev, clist, _k, _sv in candidates)
    say("")
    say(f"发现 {len(candidates)} 组可合并候选 (共 {total_files} 个文件), 预计共可节约 {human_size(total_save)};"
        f" 另有 {already_groups} 组内容相同但已互为硬链接 (跳过)。")
    for i, (size, digest, dev, clist, keeper, savings) in enumerate(candidates, 1):
        keeper_ino = stats[keeper].st_ino
        say("")
        say(f"组 {i}: 大小 {human_size(size)}  sha256={digest[:16]}  "
            f"dev={dev}  可节约 {human_size(savings)}")
        say(f"  [保留] {keeper}  (inode={keeper_ino})")
        for c in clist:
            if stats[c[0]].st_ino == keeper_ino:
                continue
            say(f"  [合并] inode {stats[c[0]].st_ino} ({len(c)} 个路径):")
            for p in c:
                say(f"      - {p}")
            say(f"      建议: ln -f {sh_quote(keeper)} {sh_quote(c[0])}")
    if candidates:
        say("")
        say("说明: 建议命令仅供参考, 本工具不会执行; 执行前请自行确认/备份。")
        say("提示: Git Bash/WSL 用 ln; CMD 用 mklink /H (NTFS, 无需管理员权限)。")
    else:
        say("")
        say("结果: 未发现可合并的硬链接候选"
            + (" (内容相同的文件都已是硬链接)。" if already_groups else "。"))
    return "\n".join(lines)


def build_script(candidates, stats, now_str, keep):
    lines = [
        "#!/usr/bin/env bash",
        f"# 由 hardlink-candidate.py 生成于 {now_str}  保留策略: keep {keep}",
        "# 请人工审阅! 所有命令默认已注释, 去掉行首 '# ' 后执行。",
        "set -euo pipefail",
    ]
    total = 0
    for size, digest, _dev, clist, keeper, savings in candidates:
        lines.append("")
        lines.append(f"# ---- sha256={digest[:16]}  大小 {human_size(size)}  "
                     f"保留: {keeper}  可节约 {human_size(savings)}")
        keeper_ino = stats[keeper].st_ino
        for c in clist:
            if stats[c[0]].st_ino == keeper_ino:
                continue
            lines.append(f"# ln -f {sh_quote(keeper)} {sh_quote(c[0])}")
        total += savings
    lines.append("")
    lines.append(f"# 预计共可节约: {human_size(total)}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog="hardlink-candidate",
        description="找出内容相同但未硬链接的文件, 输出可节约空间的硬链接建议报告。",
    )
    ap.add_argument("dirs", nargs="+", metavar="目录")
    ap.add_argument("--min-size", type=int, default=1,
                    help="只考虑大于该字节数的文件 (默认 1, 跳过空文件)")
    ap.add_argument("--keep", choices=("first", "oldest", "newest"), default="first",
                    help="每组建议保留哪个文件 (默认 first)")
    ap.add_argument("--hash-alg", default="sha256", help="哈希算法 (默认 sha256)")
    ap.add_argument("-o", "--output", help="报告写入文件 (缺省打印到 stdout)")
    ap.add_argument("--script", help="同时把建议 ln 命令写成 bash 脚本 (默认注释)")
    args = ap.parse_args(argv)

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
    stats = {}
    candidates, already_groups = analyze(files, args, stats)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if args.script:
        script = build_script(candidates, stats, now_str, args.keep)
        sp = os.path.abspath(args.script)
        os.makedirs(os.path.dirname(sp) or ".", exist_ok=True)
        with open(sp, "w", encoding="utf-8", newline="\n") as f:
            f.write(script)
        print(f"建议命令脚本已写入: {sp} (默认已注释, 请审阅后执行)")

    report = build_report(roots, len(files), candidates, already_groups, stats, args)
    if args.output:
        op = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(op) or ".", exist_ok=True)
        with open(op, "w", encoding="utf-8", newline="\n") as f:
            f.write(report + "\n")
        print(f"报告已写入: {op}")
        print(f"摘要: 候选组 {len(candidates)}, 预计共可节约 {human_size(sum(c[5] for c in candidates))};"
              f" 已是硬链接组 {already_groups}。")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
