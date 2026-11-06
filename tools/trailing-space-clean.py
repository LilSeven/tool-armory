#!/usr/bin/env python3
"""trailing-space-clean.py — 行尾空白清理工具。

删除每行行尾的半角空格、全角空格（U+3000）、NBSP 及各类 Unicode 空白与 Tab，
可选保留 Markdown 强制换行所需的双半角空格（--keep-md-br）。
完整保留原文件换行风格（\r\n / \n / \r）：CRLF 文件清理后仍是 CRLF。

用法：
  - 不给路径：读 stdin，清理结果写 stdout，统计写 stderr
  - 给文件/目录路径：默认原地写回并统计；--dry-run 只统计不写入；
    目录需配合 --ext 过滤扩展名

示例命令：
  python trailing-space-clean.py -i input.txt -o clean.txt
  cat input.txt | python trailing-space-clean.py --keep-md-br
  python trailing-space-clean.py --dry-run notes.md
  python trailing-space-clean.py --ext .txt,.md somedir/

退出码：0 成功；1 有文件处理失败；2 参数错误。
"""
import argparse
import os
import re
import sys

# 视觉上空白、应从行尾清除的字符（半角空格、Tab、全角空格、NBSP、
# en/em 空格、窄空格等常见 Unicode 空白）
WS = (" \t\u3000\u00a0\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
      "\u202f\u205f")

_LINE_RE = re.compile(r"([^\r\n]*)(\r\n|\r|\n)?")


def iter_lines(text: str):
    """按 \\r\\n、\\r、\\n 切行，逐行 yield (行体, 行尾符)。

    行尾符原样保留（不把 U+2028 等其它字符当换行），因此处理行体时
    不会碰到残留的 \\r——这正是 newline="" 读入下 CRLF 文件的坑。
    """
    pos, n = 0, len(text)
    while pos < n:
        m = _LINE_RE.match(text, pos)
        yield m.group(1), m.group(2) or ""
        pos = m.end()


def iter_target_files(paths, exts):
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for name in sorted(files):
                    if exts and not name.lower().endswith(exts):
                        continue
                    yield os.path.join(root, name)
        else:
            raise FileNotFoundError(p)


def clean_line(body: str, keep_md: bool) -> str:
    stripped = body.rstrip(WS)
    if keep_md and len(body) - len(stripped) == 2 and stripped \
            and body.endswith("  "):
        return body                     # 保留 Markdown 硬换行的双半角空格
    return stripped


def clean_text(text: str, keep_md: bool) -> tuple[str, int]:
    out = []
    changed = 0
    for body, eol in iter_lines(text):
        new = clean_line(body, keep_md)
        if new != body:
            changed += 1
        out.append(new + eol)
    return "".join(out), changed


def clean_file(path: str, keep_md: bool, in_place: bool, dry_run: bool,
               encoding: str = "utf-8") -> int:
    with open(path, "r", encoding=encoding, errors="replace", newline="") as f:
        text = f.read()
    new_text, changed = clean_text(text, keep_md)
    if changed and in_place and not dry_run:
        with open(path, "w", encoding=encoding, newline="") as f:
            f.write(new_text)
    return changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="删除行尾半角/全角空格与 Tab，可选保留 Markdown 双空格硬换行")
    ap.add_argument("-i", "--input", help="输入文件（与 paths 二选一，缺省读 stdin）")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout，仅 stdin/-i 模式）")
    ap.add_argument("paths", nargs="*", help="文件或目录（给定时默认原地写回）")
    ap.add_argument("--ext", default="", help="目录批处理时的扩展名过滤，如 .txt,.md")
    ap.add_argument("--keep-md-br", action="store_true",
                    help="保留行尾恰好两个半角空格（Markdown 强制换行）")
    ap.add_argument("--in-place", action="store_true", help="原地写回（给 paths 时默认）")
    ap.add_argument("--dry-run", action="store_true", help="只统计改动，不写回")
    ap.add_argument("--encoding", default="utf-8", help="输入/输出编码（缺省 utf-8）")
    args = ap.parse_args(argv)

    exts = tuple(e.strip().lower() for e in args.ext.split(",") if e.strip()) or None

    if not args.paths:
        # stdin / -i 模式
        try:
            if args.input:
                with open(args.input, "r", encoding=args.encoding, errors="replace",
                          newline="") as f:
                    text = f.read()
            else:
                try:
                    sys.stdin.reconfigure(encoding=args.encoding, errors="replace",
                                          newline="")
                except Exception:
                    pass
                text = sys.stdin.read()
        except OSError as e:
            print(f"错误: 读取失败: {e}", file=sys.stderr)
            return 1
        new_text, changed = clean_text(text, args.keep_md_br)
        print(f"[trailing-space-clean] 清理了 {changed} 行的行尾空白。",
              file=sys.stderr)
        try:
            if args.output:
                with open(args.output, "w", encoding=args.encoding, newline="") as f:
                    f.write(new_text)
            else:
                sys.stdout.write(new_text)
        except OSError as e:
            print(f"错误: 写出失败: {e}", file=sys.stderr)
            return 1
        return 0

    # paths 批处理模式：默认原地写回
    in_place = args.in_place or not args.dry_run
    total = files = errors = 0
    try:
        targets = list(iter_target_files(args.paths, exts))
    except FileNotFoundError as e:
        print(f"错误: 路径不存在: {e}", file=sys.stderr)
        return 1
    for path in targets:
        try:
            changed = clean_file(path, args.keep_md_br, in_place, args.dry_run,
                                 args.encoding)
        except OSError as e:
            print(f"错误: {path}: {e}", file=sys.stderr)
            errors += 1
            continue
        files += 1
        total += changed
        tag = "（dry-run 未写入）" if args.dry_run else ""
        print(f"{path}: 清理 {changed} 行{tag}")
    print(f"合计: {files} 个文件，清理 {total} 行")
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
