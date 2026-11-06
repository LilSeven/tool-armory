#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""带备份的就地清洗编辑 (backup-inplace)。

用途:
    就地应用一条清洗规则前, 先把每个原文件复制为带时间戳的 .bak 备份;
    提供 rules / list / rollback 子命令: 查看规则、查看备份、按备份回滚。

备份命名: 与原文件同目录, 原文件名 + ".bak-YYYYmmdd-HHMMSS" (同一秒重复备份时追加 -N)。
回滚默认取该文件最近一次备份; --stamp 可按时间戳子串指定; 回滚后默认保留备份文件。

内置规则 (参数用 --param key=value 传入, 可重复; 布尔值 true/false):
    trim-trailing        去除每行行尾空白
    remove-tabs          Tab 转空格            width=4
    remove-bom           去除 UTF-8 BOM
    normalize-eol        统一换行符            eol=lf|crlf
    squeeze-blank-lines  压缩连续空行          max=1
    remove-empty-lines   删除所有空行
    dedupe-lines         去除相邻重复行
    sort-lines           行排序                reverse=false
    strip-comments       粗略剥离注释          style=hash|slash|sql|html|css
    regex-sub            正则替换              pattern=..., replacement="", ignorecase=false
    delete-lines-match   删除匹配行            pattern=..., invert=false
    keep-lines-match     仅保留匹配行          pattern=...

示例命令:
    python backup-inplace.py rules
    python backup-inplace.py apply trim-trailing a.txt b.md
    python backup-inplace.py apply regex-sub --param pattern=TODO --param replacement=DONE -d ./data --ext .txt
    python backup-inplace.py list a.txt
    python backup-inplace.py list -d ./data
    python backup-inplace.py rollback a.txt
    python backup-inplace.py rollback a.txt --stamp 20261103
    python backup-inplace.py rollback -d ./data --ext .txt --all
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_EXCLUDES = [".git", ".hg", ".svn", "__pycache__", "node_modules", ".idea", ".vscode"]
_BAK_RE = re.compile(r"^(?P<orig>.+)\.bak-(?P<stamp>\d{8}-\d{6})(?:-\d+)?$")


# ---------- 规则引擎 (与 clean-pipeline 同一套核心语义) ----------

def _as_lines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _line_rule(text, fn):
    had_nl = text.endswith("\n")
    lines = _as_lines(text)
    if had_nl and lines and lines[-1] == "":
        lines.pop()
    lines = fn(lines)
    out = "\n".join(lines)
    if had_nl:
        out += "\n"
    return out


_COMMENT_STYLES = {
    "hash": ("#", None, None),
    "slash": ("//", "/*", "*/"),
    "sql": ("--", "/*", "*/"),
    "html": (None, "<!--", "-->"),
    "css": (None, "/*", "*/"),
}


def _strip_comment_lines(lines, style):
    line_m, b_open, b_close = _COMMENT_STYLES[style]
    out, in_block = [], False
    for line in lines:
        s = line.strip()
        if in_block:
            if b_close and b_close in s:
                in_block = False
            continue
        if not s:
            out.append(line)
        elif line_m and s.startswith(line_m):
            continue
        elif b_open and s.startswith(b_open):
            if b_close and b_close not in s[len(b_open):]:
                in_block = True
            continue
        else:
            out.append(line)
    return out


def _req(params, key, rule):
    v = params.get(key)
    if v is None:
        raise ValueError("规则 %s 缺少必需参数 %s" % (rule, key))
    return str(v)


def _r_trim_trailing(t, p):
    return _line_rule(t, lambda ls: [l.rstrip() for l in ls])


def _r_remove_tabs(t, p):
    w = int(p.get("width", 4))
    return _line_rule(t, lambda ls: [l.replace("\t", " " * w) for l in ls])


def _r_remove_bom(t, p):
    return t.replace("\ufeff", "")


def _r_normalize_eol(t, p):
    eol = str(p.get("eol", "lf")).lower()
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    return t.replace("\n", "\r\n") if eol == "crlf" else t


def _r_squeeze(t, p):
    mx = max(0, int(p.get("max", 1)))

    def fn(ls):
        out, run = [], 0
        for l in ls:
            if l.strip() == "":
                run += 1
                if run <= mx:
                    out.append(l)
            else:
                run = 0
                out.append(l)
        return out

    return _line_rule(t, fn)


def _r_remove_empty(t, p):
    return _line_rule(t, lambda ls: [l for l in ls if l.strip()])


def _r_dedupe(t, p):
    def fn(ls):
        out = []
        for l in ls:
            if not out or out[-1] != l:
                out.append(l)
        return out

    return _line_rule(t, fn)


def _r_sort(t, p):
    return _line_rule(t, lambda ls: sorted(ls, reverse=bool(p.get("reverse", False))))


def _r_strip_comments(t, p):
    style = str(p.get("style", "hash")).lower()
    if style not in _COMMENT_STYLES:
        raise ValueError("strip-comments: 未知 style %r (可选: %s)" % (style, "|".join(_COMMENT_STYLES)))
    return _line_rule(t, lambda ls: _strip_comment_lines(ls, style))


def _r_regex_sub(t, p):
    rx = re.compile(_req(p, "pattern", "regex-sub"),
                    re.IGNORECASE if p.get("ignorecase") else 0)
    return rx.sub(str(p.get("replacement", "")), t)


def _r_delete_lines(t, p):
    rx = re.compile(_req(p, "pattern", "delete-lines-match"))
    inv = bool(p.get("invert", False))
    return _line_rule(t, lambda ls: [l for l in ls if (bool(rx.search(l)) == inv)])


def _r_keep_lines(t, p):
    rx = re.compile(_req(p, "pattern", "keep-lines-match"))
    return _line_rule(t, lambda ls: [l for l in ls if rx.search(l)])


RULES = {
    "trim-trailing": _r_trim_trailing,
    "remove-tabs": _r_remove_tabs,
    "remove-bom": _r_remove_bom,
    "normalize-eol": _r_normalize_eol,
    "squeeze-blank-lines": _r_squeeze,
    "remove-empty-lines": _r_remove_empty,
    "dedupe-lines": _r_dedupe,
    "sort-lines": _r_sort,
    "strip-comments": _r_strip_comments,
    "regex-sub": _r_regex_sub,
    "delete-lines-match": _r_delete_lines,
    "keep-lines-match": _r_keep_lines,
}

RULE_DOCS = {
    "trim-trailing": "去除每行行尾空白",
    "remove-tabs": "Tab 转空格 (width=4)",
    "remove-bom": "去除 UTF-8 BOM",
    "normalize-eol": "统一换行符 (eol=lf|crlf)",
    "squeeze-blank-lines": "压缩连续空行 (max=1)",
    "remove-empty-lines": "删除所有空行",
    "dedupe-lines": "去除相邻重复行",
    "sort-lines": "对行排序 (reverse=false)",
    "strip-comments": "粗略剥离注释 (style=hash|slash|sql|html|css)",
    "regex-sub": "正则替换 (pattern=..., replacement=, ignorecase=false)",
    "delete-lines-match": "删除匹配行 (pattern=..., invert=false)",
    "keep-lines-match": "仅保留匹配行 (pattern=...)",
}


# ---------- 通用辅助 ----------

def _parse_exts(s):
    exts = {e.strip().lower() for e in (s or "").split(",") if e.strip()}
    return exts or None


def _coerce(v):
    low = str(v).strip().lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    for conv in (int, float):
        try:
            return conv(str(v))
        except ValueError:
            pass
    return str(v)


def _parse_params(pairs):
    params = {}
    for item in pairs:
        k, sep, v = item.partition("=")
        if not sep or not k.strip():
            raise ValueError("--param 需要 KEY=VALUE 形式: %r" % item)
        params[k.strip()] = _coerce(v)
    return params


def _iter_targets(paths, dirpath, exts):
    targets = []
    for p in paths:
        pp = Path(p)
        if pp.is_file():
            targets.append(pp)
        else:
            print("跳过(不是文件): %s" % p, file=sys.stderr)
    if dirpath:
        root = Path(dirpath)
        if not root.is_dir():
            raise ValueError("目录不存在: %s" % dirpath)
        for dp, dns, fns in os.walk(root):
            dns[:] = sorted(d for d in dns if d not in DEFAULT_EXCLUDES)
            for fn in sorted(fns):
                if _BAK_RE.match(fn):
                    continue
                if exts is not None and os.path.splitext(fn)[1].lower() not in exts:
                    continue
                targets.append(Path(dp) / fn)
    return targets


def _make_backup(path):
    """复制原文件为 原名.bak-YYYYmmdd-HHMMSS, 同秒冲突时追加 -N。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = path.with_name("%s.bak-%s" % (path.name, stamp))
    n = 1
    while bak.exists():
        n += 1
        bak = path.with_name("%s.bak-%s-%d" % (path.name, stamp, n))
    try:
        shutil.copy2(path, bak)
    except OSError as e:
        print("备份失败 %s: %s" % (path, e), file=sys.stderr)
        return None
    return bak


def _backups_of(path):
    parent = path.parent
    if not parent.is_dir():
        return []
    out = []
    for p in parent.iterdir():
        m = _BAK_RE.match(p.name)
        if p.is_file() and m and m.group("orig") == path.name:
            out.append(p)
    return sorted(out, key=lambda p: p.name)


def _collect_backup_entries(paths, dirpath):
    entries = {}
    if dirpath:
        root = Path(dirpath)
        if not root.is_dir():
            raise ValueError("目录不存在: %s" % dirpath)
        for dp, dns, fns in os.walk(root):
            dns[:] = sorted(d for d in dns if d not in DEFAULT_EXCLUDES)
            for fn in sorted(fns):
                m = _BAK_RE.match(fn)
                if not m:
                    continue
                orig = Path(dp) / m.group("orig")
                entries.setdefault(str(orig), []).append(Path(dp) / fn)
    for p in paths:
        pp = Path(p)
        if not pp.exists():
            print("跳过(不存在): %s" % p, file=sys.stderr)
            continue
        baks = _backups_of(pp)
        if baks:
            entries.setdefault(str(pp), baks)
    for v in entries.values():
        v.sort(key=lambda p: p.name)
    return entries


# ---------- 子命令 ----------

def cmd_rules(args):
    print("内置规则 (参数用 --param key=value 传入):")
    for name in sorted(RULES):
        print("  %-20s %s" % (name, RULE_DOCS[name]))
    return 0


def cmd_apply(args):
    if args.rule not in RULES:
        print("未知规则: %s (用 rules 子命令查看全部规则)" % args.rule, file=sys.stderr)
        return 2
    try:
        targets = _iter_targets(args.paths, args.dir, _parse_exts(args.ext))
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if not targets:
        print("没有找到目标文件", file=sys.stderr)
        return 2
    failures = 0
    for path in targets:
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                text = f.read()
        except (UnicodeDecodeError, OSError) as e:
            print("跳过 %s: %s" % (path, e), file=sys.stderr)
            failures += 1
            continue
        try:
            new_text = RULES[args.rule](text, args.params_dict)
        except (ValueError, re.error) as e:
            print("规则参数错误: %s" % e, file=sys.stderr)
            return 2
        bak = _make_backup(path)
        if bak is None:
            failures += 1
            continue
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new_text)
        except OSError as e:
            print("写入失败 %s: %s" % (path, e), file=sys.stderr)
            failures += 1
            continue
        if new_text == text:
            print("[备份] %s -> %s | 应用 %s: 内容无变化" % (path, bak.name, args.rule))
        else:
            print("[备份] %s -> %s | 应用 %s: %d -> %d 行" % (
                path, bak.name, args.rule,
                len(text.splitlines()), len(new_text.splitlines())))
    if failures:
        print("完成, 但有 %d 个文件失败" % failures, file=sys.stderr)
        return 1
    return 0


def cmd_list(args):
    try:
        entries = _collect_backup_entries(args.paths, args.dir)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if not entries:
        print("未找到备份 (备份命名: <文件>.bak-YYYYmmdd-HHMMSS)")
        return 0
    count = 0
    for orig in sorted(entries):
        print("原文件: %s" % orig)
        for bak in entries[orig]:
            try:
                st = bak.stat()
            except OSError as e:
                print("    %s  (无法读取: %s)" % (bak.name, e))
                continue
            print("    %s  %10d 字节  备份于 %s" % (
                bak.name, st.st_size,
                datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")))
            count += 1
    print("共 %d 个备份, 对应 %d 个文件" % (count, len(entries)))
    return 0


def cmd_rollback(args):
    try:
        if args.paths:
            targets = [Path(p) for p in args.paths]
        elif args.dir:
            entries = _collect_backup_entries([], args.dir)
            if args.ext:
                exts = _parse_exts(args.ext)
                targets = [Path(o) for o in entries
                           if os.path.splitext(o)[1].lower() in exts]
            elif args.all:
                targets = [Path(o) for o in entries]
            else:
                print("批量回滚请用 --ext 过滤扩展名, 或加 --all 回滚全部 (避免误操作)", file=sys.stderr)
                return 2
        else:
            print("请指定要回滚的文件, 或使用 -d 目录批量回滚", file=sys.stderr)
            return 2
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    restored = failures = skipped = 0
    for path in targets:
        baks = _backups_of(path)
        if not baks:
            print("跳过 %s: 没有可用备份" % path)
            skipped += 1
            continue
        if args.stamp:
            matches = [b for b in baks if args.stamp in b.name]
            if not matches:
                print("跳过 %s: 找不到匹配 %r 的备份" % (path, args.stamp), file=sys.stderr)
                failures += 1
                continue
            bak = matches[-1]
        else:
            bak = baks[-1]
        try:
            shutil.copy2(bak, path)
        except OSError as e:
            print("回滚失败 %s: %s" % (path, e), file=sys.stderr)
            failures += 1
            continue
        restored += 1
        print("[回滚] %s <- %s" % (path, bak.name))
        if args.remove_backup:
            try:
                bak.unlink()
                print("       已删除备份 %s" % bak.name)
            except OSError as e:
                print("       删除备份失败: %s" % e, file=sys.stderr)
    print("完成: 回滚 %d 个, 跳过 %d 个, 失败 %d 个" % (restored, skipped, failures))
    return 1 if failures else 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass
    ap = argparse.ArgumentParser(
        prog="backup-inplace",
        description="带备份的就地清洗编辑: 应用清洗规则前自动生成时间戳 .bak 备份, 支持按备份回滚。")
    sub = ap.add_subparsers(dest="command", metavar="{rules|apply|list|rollback}")

    sub.add_parser("rules", help="列出内置清洗规则")

    p_apply = sub.add_parser("apply", help="备份后就地应用一条清洗规则")
    p_apply.add_argument("rule", help="规则名 (见 rules 子命令)")
    p_apply.add_argument("--param", action="append", default=[], metavar="KEY=VALUE",
                         help="规则参数, 可重复, 如 --param pattern=TODO")
    p_apply.add_argument("paths", nargs="*", metavar="FILE", help="目标文件 (可与 -d 并用)")
    p_apply.add_argument("-d", "--dir", help="递归处理整个目录")
    p_apply.add_argument("--ext", default="", metavar="EXTS", help="目录模式下的扩展名过滤, 逗号分隔")

    p_list = sub.add_parser("list", help="列出已有备份")
    p_list.add_argument("paths", nargs="*", metavar="FILE", help="查看这些文件的备份")
    p_list.add_argument("-d", "--dir", help="递归扫描目录下的全部备份")

    p_rb = sub.add_parser("rollback", help="从备份恢复文件")
    p_rb.add_argument("paths", nargs="*", metavar="FILE", help="要回滚的文件")
    p_rb.add_argument("-d", "--dir", help="批量回滚目录下有备份的文件")
    p_rb.add_argument("--ext", default="", metavar="EXTS", help="目录模式扩展名过滤 (与 --all 二选一)")
    p_rb.add_argument("--all", action="store_true", help="目录模式下回滚全部有备份的文件")
    p_rb.add_argument("--stamp", help="只回滚到时间戳含该子串的备份 (默认最近一次)")
    p_rb.add_argument("--remove-backup", action="store_true", help="回滚成功后删除所用备份")

    args = ap.parse_args(argv)
    if args.command is None:
        ap.print_help()
        return 2
    if args.command == "apply":
        try:
            args.params_dict = _parse_params(args.param)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        return cmd_apply(args)
    if args.command == "rules":
        return cmd_rules(args)
    if args.command == "list":
        if not args.paths and not args.dir:
            print("请指定文件或 -d 目录", file=sys.stderr)
            return 2
        return cmd_list(args)
    if args.command == "rollback":
        return cmd_rollback(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
