#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清洗规则流水线 (clean-pipeline)。

用途:
    用 YAML/JSON 配置把多个清洗步骤按顺序组合成一条流水线, 单条命令递归处理
    整个目录的文本文件。默认仅预览(不写盘), 用 --write 就地覆盖, 或 --out 输出到新目录。

内置规则 (steps 中按顺序引用; 带参数的规则写成嵌套映射):
    trim-trailing        去除每行行尾空白
    remove-tabs          Tab 转空格            参数: width=4
    remove-bom           去除文件头的 UTF-8 BOM
    normalize-eol        统一换行符            参数: eol=lf|crlf (默认 lf)
    squeeze-blank-lines  压缩连续空行          参数: max=1
    remove-empty-lines   删除所有空行
    dedupe-lines         去除相邻重复行
    sort-lines           对行排序              参数: reverse=false
    strip-comments       粗略剥离注释          参数: style=hash|slash|sql|html|css
    lower / upper        全文转小写 / 大写
    regex-sub            正则替换              参数: pattern, replacement="", ignorecase=false
    delete-lines-match   删除匹配行            参数: pattern, invert=false
    keep-lines-match     仅保留匹配行          参数: pattern

配置示例 pipeline.yaml (YAML 支持常用子集: 缩进映射/列表/行注释/常用标量;
引号内为字面量不做转义, 正则建议不加引号; 列表项的子键缩进需比 "- " 内容更深):
    steps:
      - trim-trailing
      - squeeze-blank-lines:
          max: 2
      - regex-sub:
          pattern: TODO.*$
          replacement: ""

示例命令:
    python clean-pipeline.py pipeline.yaml ./data --dry-run
    python clean-pipeline.py pipeline.yaml ./data --write --ext .txt,.md
    python clean-pipeline.py pipeline.json ./data --out ./cleaned

注意:
    行级规则内部统一按 LF 处理; 若需保留 CRLF, 在流水线最后加 normalize-eol(eol=crlf)。
    无法按 UTF-8 解码的文件会被跳过并计入 skipped; .bak-时间戳 备份文件一律跳过。
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_EXCLUDES = [".git", ".hg", ".svn", "__pycache__", "node_modules", ".idea", ".vscode", ".bzr"]

_BAK_SUFFIX_RE = re.compile(r"\.bak-\d{8}-\d{6}(?:-\d+)?$")


class PipelineError(Exception):
    """配置或规则执行错误。"""


# ---------- 迷你 YAML 解析器 (常用子集) ----------

def _strip_inline_comment(line):
    q = None
    for i, ch in enumerate(line):
        if q is not None:
            if ch == q:
                q = None
        elif ch in "'\"":
            q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _parse_scalar(s):
    s = s.strip()
    if s == "" or s in ("~", "null", "Null", "NULL"):
        return None
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [] if not inner else [_parse_scalar(x) for x in inner.split(",")]
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    for conv in (int, float):
        try:
            return conv(s)
        except ValueError:
            pass
    return s


def parse_mini_yaml(text):
    """解析常用 YAML 子集: 缩进映射、'- ' 列表、行注释、常用标量。"""
    items = []
    for no, raw in enumerate(text.splitlines(), 1):
        if raw.lstrip(" ").startswith("\t"):
            raise PipelineError("第 %d 行: 缩进不允许使用 Tab" % no)
        line = _strip_inline_comment(raw)
        if not line.strip():
            continue
        items.append((len(line) - len(line.lstrip(" ")), line.strip(), no))
    if not items:
        return None
    value, i = _parse_block(items, 0, items[0][0])
    if i < len(items):
        raise PipelineError("第 %d 行: 无法解析的内容 %r" % (items[i][2], items[i][1]))
    return value


def _parse_block(items, i, indent):
    if items[i][1].startswith("- "):
        return _parse_list(items, i, indent)
    return _parse_map(items, i, indent)


def _parse_map(items, i, indent):
    out = {}
    while i < len(items):
        ind, content, no = items[i]
        if ind < indent or content.startswith("- "):
            break
        if ind > indent:
            raise PipelineError("第 %d 行: 意外的缩进 %r" % (no, content))
        key, sep, rest = content.partition(":")
        if not sep:
            raise PipelineError("第 %d 行: 缺少 ':', 不是合法的映射键: %r" % (no, content))
        key = str(_parse_scalar(key))
        rest = rest.strip()
        i += 1
        if rest:
            out[key] = _parse_scalar(rest)
        elif i < len(items) and items[i][0] > indent:
            out[key], i = _parse_block(items, i, items[i][0])
        elif i < len(items) and items[i][0] == indent and items[i][1].startswith("- "):
            out[key], i = _parse_list(items, i, indent)
        else:
            out[key] = None
    return out, i


def _parse_list(items, i, indent):
    out = []
    while i < len(items):
        ind, content, no = items[i]
        if ind < indent or (ind == indent and not content.startswith("- ")):
            break
        if ind > indent:
            raise PipelineError("第 %d 行: 意外的缩进 %r" % (no, content))
        rest = content[2:].strip()
        i += 1
        if not rest:
            if i < len(items) and items[i][0] > indent:
                val, i = _parse_block(items, i, items[i][0])
                out.append(val)
            else:
                out.append(None)
        elif rest.startswith(("'", '"')) or ":" not in rest:
            out.append(_parse_scalar(rest))
        else:
            # 列表项是映射: "- 规则名:" 或 "- 键: 值", 后续更深的行归它所有
            child_indent = indent + 2
            synth = [(child_indent, rest, no)]
            while i < len(items) and items[i][0] > indent:
                synth.append(items[i])
                i += 1
            val, j = _parse_block(synth, 0, child_indent)
            if j < len(synth):
                raise PipelineError("第 %d 行: 无法解析的列表项 %r" % (synth[j][2], synth[j][1]))
            out.append(val)
    return out, i


# ---------- 规则引擎 ----------

def _as_lines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _line_rule(text, fn):
    """以行为单位应用变换, 保留文件末尾是否有换行的特征。"""
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
    "hash": ("#", None, None),          # Python/Shell/Ruby/YAML...
    "slash": ("//", "/*", "*/"),        # JS/Java/C 系
    "sql": ("--", "/*", "*/"),          # SQL
    "html": (None, "<!--", "-->"),      # HTML/XML
    "css": (None, "/*", "*/"),          # CSS 仅块注释
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
        raise PipelineError("规则 %s 缺少必需参数 %s" % (rule, key))
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
        raise PipelineError("strip-comments: 未知 style %r (可选: %s)" % (style, "|".join(_COMMENT_STYLES)))
    return _line_rule(t, lambda ls: _strip_comment_lines(ls, style))


def _r_lower(t, p):
    return t.lower()


def _r_upper(t, p):
    return t.upper()


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
    "lower": _r_lower,
    "upper": _r_upper,
    "regex-sub": _r_regex_sub,
    "delete-lines-match": _r_delete_lines,
    "keep-lines-match": _r_keep_lines,
}


# ---------- 配置加载与执行 ----------

def load_config(path):
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise PipelineError("读取配置失败: %s" % e)
    if p.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except ValueError as e:
            raise PipelineError("JSON 解析失败: %s" % e)
    else:
        data = parse_mini_yaml(text)
    if not isinstance(data, dict):
        raise PipelineError("配置顶层必须是映射 (包含 steps 键)")
    return data


def build_steps(cfg):
    raw = cfg.get("steps")
    if raw is None:
        raise PipelineError("配置缺少 steps 列表")
    if not isinstance(raw, list):
        raise PipelineError("steps 必须是列表")
    steps = []
    for idx, item in enumerate(raw):
        if isinstance(item, str):
            steps.append((item, {}))
        elif isinstance(item, dict) and len(item) == 1:
            (name, params), = item.items()
            params = params or {}
            if not isinstance(params, dict):
                raise PipelineError("第 %d 个步骤: 规则 %s 的参数必须是映射" % (idx + 1, name))
            steps.append((str(name), params))
        else:
            raise PipelineError("第 %d 个步骤无法识别: %r (应为 规则名 或 {规则名: 参数})" % (idx + 1, item))
    for name, _ in steps:
        if name not in RULES:
            raise PipelineError("未知规则: %s (可选: %s)" % (name, ", ".join(RULES)))
    return steps


def apply_steps(text, steps):
    for name, params in steps:
        text = RULES[name](text, params)
    return text


def _parse_exts(s):
    exts = {e.strip().lower() for e in (s or "").split(",") if e.strip()}
    return exts or None


def _iter_files(root, exts, excludes):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in excludes)
        for fn in sorted(filenames):
            if _BAK_SUFFIX_RE.search(fn):
                continue
            if exts is not None and os.path.splitext(fn)[1].lower() not in exts:
                continue
            yield Path(dirpath) / fn


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass
    ap = argparse.ArgumentParser(
        prog="clean-pipeline",
        description="清洗规则流水线: 按 YAML/JSON 配置把多个清洗步骤按顺序应用到目录内所有文本文件。",
        epilog="默认仅预览不写盘; --write 就地覆盖; --out 写入新目录(保留相对路径)。",
    )
    ap.add_argument("config", help="流水线配置文件 (.yaml/.yml/.json)")
    ap.add_argument("directory", help="要处理的目录")
    ap.add_argument("--ext", default="", metavar="EXTS",
                    help="仅处理这些扩展名, 逗号分隔 (如 .txt,.md); 默认全部文件")
    ap.add_argument("--exclude-dirs", default=",".join(DEFAULT_EXCLUDES), metavar="DIRS",
                    help="要跳过的子目录名, 逗号分隔")
    ap.add_argument("--write", action="store_true", help="就地覆盖原文件")
    ap.add_argument("--out", metavar="DIR", help="清洗结果写入新目录 (与 --write 互斥)")
    ap.add_argument("--dry-run", action="store_true", help="仅预览, 不写盘 (默认行为, 显式声明用)")
    args = ap.parse_args(argv)

    if args.write and args.out:
        ap.error("--write 与 --out 不能同时使用")
    do_write = args.write and not args.dry_run
    out_root = None if args.dry_run else (Path(args.out) if args.out else None)
    mode = "就地覆盖" if do_write else ("输出到 %s" % args.out if out_root else "预览(不写盘)")

    try:
        steps = build_steps(load_config(args.config))
    except PipelineError as e:
        print("配置错误: %s" % e, file=sys.stderr)
        return 2

    root = Path(args.directory)
    if not root.is_dir():
        print("目录不存在: %s" % root, file=sys.stderr)
        return 2
    if out_root is not None:
        try:
            out_root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print("无法创建输出目录: %s" % e, file=sys.stderr)
            return 2

    exts = _parse_exts(args.ext)
    excludes = {d.strip() for d in args.exclude_dirs.split(",") if d.strip()}
    total = changed = skipped = 0
    for path in _iter_files(root, exts, excludes):
        total += 1
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                text = f.read()
        except UnicodeDecodeError:
            skipped += 1
            print("跳过(非 UTF-8): %s" % path, file=sys.stderr)
            continue
        except OSError as e:
            skipped += 1
            print("跳过(读取失败): %s (%s)" % (path, e), file=sys.stderr)
            continue
        try:
            new_text = apply_steps(text, steps)
        except (PipelineError, re.error) as e:
            print("规则错误: %s" % e, file=sys.stderr)
            return 2
        rel = path.relative_to(root)
        if new_text == text:
            print("[无变化] %s (%d 行)" % (rel.as_posix(), len(text.splitlines())))
            continue
        changed += 1
        print("[变更] %s: %d -> %d 行" % (rel.as_posix(),
                                          len(text.splitlines()), len(new_text.splitlines())))
        if do_write:
            dest = path
        elif out_root is not None:
            dest = out_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
        else:
            continue
        try:
            with open(dest, "w", encoding="utf-8", newline="") as f:
                f.write(new_text)
        except OSError as e:
            print("写入失败 %s: %s" % (dest, e), file=sys.stderr)
            return 1

    print("完成(%s): 扫描 %d 个文件, 变更 %d 个, 跳过 %d 个; 规则链: %s" % (
        mode, total, changed, skipped, " -> ".join(name for name, _ in steps)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
