#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""超长函数扫描（func-length-scan）

用途：
    递归扫描文件或目录，识别源码中的函数体并测量其长度（含函数头
    与函数体最后一行），列出总行数超过指定阈值的函数及其行号范围。

    函数体识别方式：
      * python —— 按 def/async def 关键字 + 缩进层次识别（跳过注释
        与三引号字符串里的伪 def）；
      * brace  —— 按"函数签名特征 + 花括号配对"识别，适用于
        C/C++/Java/JavaScript/TypeScript/Go/Rust/C#/PHP 等花括号
        语言（自动剔除 if/for/while/switch 等控制语句，并剥离注释
        与字符串，避免其中的花括号干扰计数）。
    默认 --lang auto：按扩展名自动选择识别方式。

示例命令：
    python -I func-length-scan.py src/ --min-lines 50
    python -I func-length-scan.py . --lang python --min-lines 30 --top 20
    python -I func-length-scan.py main.c --min-lines 10

退出码：0 正常（无论是否发现超长函数）；2 参数或路径错误。
仅依赖 Python 标准库。
"""

import argparse
import os
import re
import sys
import unicodedata

DEFAULT_EXCLUDES = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules", "venv", ".venv",
    "dist", "build", ".idea", ".vscode", ".tox", ".mypy_cache",
}

PY_EXTS = {".py", ".pyw"}
BRACE_EXTS = {
    ".c", ".h", ".cc", ".cpp", ".hpp", ".cxx", ".hh", ".java", ".js",
    ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".cs", ".go", ".rs", ".swift",
    ".kt", ".kts", ".php", ".scala", ".dart", ".groovy",
}

DEF_RE = re.compile(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")
CAND_RE = re.compile(r"([A-Za-z_]\w*)\s*\(")

# 这些词后面直接跟 "(" 时不是函数定义（控制语句等）。
CONTROL_WORDS = {
    "if", "else", "elif", "for", "foreach", "while", "do", "switch",
    "case", "default", "try", "catch", "finally", "return", "break",
    "continue", "throw", "class", "struct", "enum", "union", "namespace",
    "interface", "record", "using", "sizeof", "typeof", "new", "delete",
    "lock", "synchronized", "template", "typename", "operator", "assert",
    "require", "print", "echo", "auto",
}


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _dw(s):
    """字符串显示宽度（全角字符记 2 列）。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
               for c in s)


def parse_exts(spec):
    """把 'a,b' 解析为扩展名集合；'*' 返回 None（不过滤）。"""
    spec = (spec or "").strip()
    if spec == "*":
        return None
    out = set()
    for e in spec.split(","):
        e = e.strip().lower()
        if e:
            out.add(e if e.startswith(".") else "." + e)
    return out


def iter_files(root, exts, excludes):
    """递归列出待扫描文件；exts=None 表示不限扩展名。"""
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in excludes and not d.startswith(".")
        )
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            if exts is not None and os.path.splitext(fn)[1].lower() not in exts:
                continue
            yield os.path.join(dirpath, fn)


def read_text(path):
    """读文本（utf-8，容错）；二进制文件返回 None。"""
    with open(path, "rb") as f:
        head = f.read(8192)
        if b"\x00" in head:
            return None
        f.seek(0)
        return f.read().decode("utf-8", errors="replace")


def _rel(path, root):
    if os.path.isdir(root):
        try:
            return os.path.relpath(path, root).replace(os.sep, "/")
        except ValueError:
            pass
    return path.replace(os.sep, "/")


def _py_clean(line, state):
    """返回去掉注释与字符串字面量后的代码片段（保留前导空白）。

    state["q"] 记录跨行三引号字符串的开头标记（三个引号）。
    """
    q = state["q"]
    i = 0
    n = len(line)
    if q is not None:
        end = line.find(q)
        if end == -1:
            return ""
        i = end + 3
        state["q"] = None
    out = []
    while i < n:
        c = line[i]
        if c == "#":
            break
        if c in "\"'":
            tri = line[i:i + 3]
            if tri in ('"""', "'''"):
                close = line.find(tri, i + 3)
                if close == -1:
                    state["q"] = tri
                    break
                i = close + 3
                continue
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == c:
                    break
                j += 1
            i = min(j + 1, n)
            out.append('""')
            continue
        out.append(c)
        i += 1
    return "".join(out)


def scan_python(text):
    """按缩进识别函数体，返回 [(name, start, end)]（行号 1 起，含首尾）。"""
    lines = text.splitlines()
    state = {"q": None}
    stack = []
    result = []
    last_content = 0
    for idx, raw in enumerate(lines, 1):
        if raw.strip():
            last_content = idx
        was_in_str = state["q"] is not None
        code = _py_clean(raw, state)
        if was_in_str:
            continue
        stripped = code.strip()
        if not stripped:
            continue
        expanded = raw.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip(" "))
        while stack and indent <= stack[-1][2]:
            name, start, _ = stack.pop()
            end = idx - 1
            while end > start and not lines[end - 1].strip():
                end -= 1
            result.append((name, start, end))
        m = DEF_RE.match(stripped)
        if m:
            stack.append((m.group(1), idx, indent))
    while stack:
        name, start, _ = stack.pop()
        result.append((name, start, max(start, last_content)))
    return result


def _c_clean(line, st):
    """去掉 //、/* */ 注释与字符串/字符/模板字面量内容（花括号语言）。"""
    out = []
    i = 0
    n = len(line)
    in_block = st["block"]
    while i < n:
        if in_block:
            j = line.find("*/", i)
            if j == -1:
                i = n
                break
            i = j + 2
            in_block = False
            out.append(" ")
            continue
        c = line[i]
        if c == "/" and i + 1 < n and line[i + 1] in "/*":
            if line[i + 1] == "/":
                break
            in_block = True
            i += 2
            continue
        if c in "\"'`":
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == c:
                    j += 1
                    break
                j += 1
            i = min(j, n)
            out.append('""')
            continue
        out.append(c)
        i += 1
    st["block"] = in_block
    return "".join(out)


def _find_candidate(t):
    """在清理过的一行里找函数名候选；找不到返回 None。

    位置规则：候选名的 "(" 后紧跟 "*"（函数指针声明如
    void (*cb)(int)），或名字本身被 "(" 包住（强制转换如 (short)x），
    都不算函数定义。
    """
    brace = t.find("{")
    for m in CAND_RE.finditer(t):
        name = m.group(1)
        if name in CONTROL_WORDS:
            continue
        if t[m.end(0) - 1] == "(":
            after = t[m.end(0):m.end(0) + 1]
            before = t[m.start() - 1:m.start()]
            if after == "*" or before == "(":
                continue
        if brace != -1 and m.end(0) - 1 > brace:
            # "{" 出现在候选名之前，说明这是 if/for 等语句体，不是函数
            return None
        return name
    return None


def scan_brace(text):
    """按签名特征+花括号配对识别函数体，返回 [(name, start, end)]。"""
    lines = text.splitlines()
    st = {"block": False}
    result = []
    depth = 0
    current = None      # [name, start_line, base_depth]
    pending = None      # (name, line) 等待 "{" 的签名候选
    pending_age = 0
    last_content = 0
    for idx, raw in enumerate(lines, 1):
        if raw.strip():
            last_content = idx
        t = _c_clean(raw, st).strip()
        if current is None:
            if pending is not None:
                pending_age += 1
                if pending_age > 3:
                    pending = None
            if (pending is None and t and not t.startswith("#")
                    and not t.endswith(";") and "(" in t):
                name = _find_candidate(t)
                if name:
                    pending = (name, idx)
                    pending_age = 0
        for ch in t:
            if ch == "{":
                if pending is not None and current is None:
                    current = [pending[0], pending[1], depth]
                    pending = None
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                if current is not None and depth == current[2]:
                    result.append((current[0], current[1], idx))
                    current = None
            elif ch == ";" and pending is not None:
                pending = None
    if current is not None:
        result.append((current[0], current[1], max(current[1], last_content)))
    return result


def main(argv=None):
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        prog="func-length-scan",
        description="扫描源码中的超长函数，输出函数名与行号范围。")
    ap.add_argument("path", help="要扫描的文件或目录")
    ap.add_argument("--min-lines", type=int, default=50,
                    help="超长阈值：函数总行数 > 该值才列出（默认 50）")
    ap.add_argument("--lang", choices=("auto", "python", "brace"),
                    default="auto",
                    help="函数识别方式（默认 auto 按扩展名自动选择）")
    ap.add_argument("--ext", default=None,
                    help="仅扫描这些扩展名（逗号分隔，如 .py,.c；'*'=全部；"
                         "默认随 --lang 自动确定）")
    ap.add_argument("--top", type=int, default=0,
                    help="只显示最长的前 N 个（0=全部）")
    ap.add_argument("--exclude", default="",
                    help="额外排除的目录名（逗号分隔）")
    args = ap.parse_args(argv)

    if not os.path.exists(args.path):
        print("错误：路径不存在：%s" % args.path, file=sys.stderr)
        return 2

    excludes = set(DEFAULT_EXCLUDES)
    excludes |= {x.strip() for x in args.exclude.split(",") if x.strip()}
    if args.lang == "python":
        default_exts = set(PY_EXTS)
    elif args.lang == "brace":
        default_exts = set(BRACE_EXTS)
    else:
        default_exts = PY_EXTS | BRACE_EXTS
    exts = parse_exts(args.ext) if args.ext else default_exts

    results = []
    n_files = n_funcs = n_skip = 0
    for path in iter_files(args.path, exts, excludes):
        n_files += 1
        ext = os.path.splitext(path)[1].lower()
        if args.lang == "python":
            mode = "python"
        elif args.lang == "brace":
            mode = "brace"
        elif ext in PY_EXTS:
            mode = "python"
        elif ext in BRACE_EXTS:
            mode = "brace"
        else:
            n_skip += 1
            continue
        try:
            text = read_text(path)
        except OSError as exc:
            print("警告：无法读取 %s：%s" % (path, exc), file=sys.stderr)
            continue
        if text is None:
            n_skip += 1
            continue
        funcs = scan_python(text) if mode == "python" else scan_brace(text)
        n_funcs += len(funcs)
        rel = _rel(path, args.path)
        for name, start, end in funcs:
            length = end - start + 1
            if length > args.min_lines:
                results.append((length, rel, name, start, end, mode))

    results.sort(key=lambda r: (-r[0], r[1], r[3]))
    shown = results if args.top <= 0 else results[:args.top]
    for length, rel, name, start, end, mode in shown:
        print("%s:%d-%d  [%s] %s  %d 行" % (rel, start, end, mode, name, length))
    tail = "共扫描 %d 个文件，识别函数 %d 个；超长（> %d 行）函数 %d 个" % (
        n_files, n_funcs, args.min_lines, len(results))
    if args.top > 0 and len(results) > len(shown):
        tail += "，仅显示前 %d 个" % len(shown)
    if n_skip:
        tail += "；跳过无法识别类型/二进制文件 %d 个" % n_skip
    print(tail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
