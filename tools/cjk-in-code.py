#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cjk-in-code —— 代码中的中文（CJK）内容扫描，输出国际化检查清单。

把源码切成注释、字符串字面量与代码三部分，逐段查找 CJK 字符（中文汉字、中文
标点/全角符号，并顺带识别日文假名与韩文谚文），按出现位置输出 i18n 检查清单，
帮助发现需要抽取到资源文件的文案，或不应进入发布内容的多语言文本。

仅依赖 Python 标准库。

用法:
    python cjk-in-code.py src/                     # 递归扫描代码文件
    python cjk-in-code.py a.py b.js --json         # 扫描指定文件, JSON 输出
    python cjk-in-code.py src/ --ext .md           # 把 Markdown 文档也纳入扫描
    python cjk-in-code.py src/ --fail-on-find      # 有发现时退出码为 1

退出码: 0=正常（无论是否发现）; 1=--fail-on-find 且有发现; 2=参数或路径错误。
"""

import argparse
import json
import os
import re
import sys

TOOL = "cjk-in-code"

SKIP_DIRS = {".git", ".svn", ".hg", ".tox", ".idea", ".vscode", "node_modules",
             "__pycache__", ".mypy_cache", ".pytest_cache", ".venv", "venv",
             "dist", "build", ".eggs", "target"}
MAX_BYTES = 10 * 1024 * 1024

# ---------------------------------------------------------------- 语言规范

LANGS = {
    "python":  {"line": ("#",), "blocks": (), "strings": ('"""', "'''", '"', "'")},
    "c":       {"line": ("//",), "blocks": (("/*", "*/"),), "strings": ('"', "'", "`")},
    "shell":   {"line": ("#",), "blocks": (), "strings": ('"', "'")},
    "sql":     {"line": ("--",), "blocks": (("/*", "*/"),), "strings": ("'", '"')},
    "lua":     {"line": ("--",), "blocks": (("--[[", "]]"),), "strings": ('"', "'")},
    "html":    {"line": (), "blocks": (("<!--", "-->"),), "strings": ('"', "'")},
    "css":     {"line": (), "blocks": (("/*", "*/"),), "strings": ('"', "'")},
    "json":    {"line": (), "blocks": (), "strings": ('"',)},
    "text":    {"prose": True},
    "generic": {"line": ("#", "//"), "blocks": (("/*", "*/"),), "strings": ('"', "'")},
}

EXT_LANG = {
    **{e: "python" for e in (".py", ".pyw", ".pyi")},
    **{e: "c" for e in (".c .h .cpp .cc .cxx .hpp .hh .hxx .cs .java .kt .kts "
                        ".scala .groovy .go .rs .swift .dart .m .mm .js .mjs "
                        ".cjs .jsx .ts .tsx .vue .php .phtml .sol .zig .ino "
                        ".scss .less .jsonc").split()},
    **{e: "shell" for e in (".sh .bash .zsh .ksh .ps1 .psm1 .psd1 .rb .rake "
                            ".gemspec .podspec .yml .yaml .toml .ini .cfg .conf "
                            ".properties .env .pl .pm .r .jl .gitignore").split()},
    ".sql": "sql", ".lua": "lua",
    **{e: "html" for e in (".html .htm .xhtml .xml .svg .xsl .xslt .plist").split()},
    ".css": "css", ".json": "json",
    **{e: "text" for e in (".md .markdown .rst .txt .text").split()},
}
KNOWN_EXT = set(EXT_LANG)
DOC_EXTS = {".md", ".markdown", ".rst", ".txt", ".text"}
DEFAULT_EXTS = KNOWN_EXT - DOC_EXTS   # 默认只扫代码类文件，文档可用 --ext 加入

KIND_LABEL = {"comment": "注释", "string": "字符串字面量",
              "code": "代码/标识符", "text": "文本"}


def spec_for(path):
    return LANGS[EXT_LANG.get(os.path.splitext(path)[1].lower(), "generic")]


def segment(text, spec, include_code=False):
    """把源码切分为 (kind, lineno, col, chunk) 片段。

    kind: "comment" 注释 / "string" 字符串字面量 / "text" 整行文本(prose) /
    "code" 代码（仅 include_code=True 时输出）。chunk 均为单行内文本，不含换行。
    """
    out = []
    if spec.get("prose"):
        for lineno, ln in enumerate(text.splitlines(), 1):
            if ln.strip():
                out.append(("text", lineno, 1, ln))
        return out

    line_marks = spec.get("line", ())
    blocks = spec.get("blocks", ())
    strings = spec.get("strings", ())
    block_end = None
    triple = None

    for lineno, s in enumerate(text.splitlines(), 1):
        pos, n = 0, len(s)
        while pos < n:
            if block_end is not None:
                e = s.find(block_end, pos)
                if e < 0:
                    out.append(("comment", lineno, pos + 1, s[pos:]))
                    pos = n
                else:
                    out.append(("comment", lineno, pos + 1, s[pos:e]))
                    pos = e + len(block_end)
                    block_end = None
                continue
            if triple is not None:
                e = s.find(triple, pos)
                if e < 0:
                    out.append(("string", lineno, pos + 1, s[pos:]))
                    pos = n
                else:
                    out.append(("string", lineno, pos + 1, s[pos:e]))
                    pos = e + len(triple)
                    triple = None
                continue
            best = None  # (idx, kind, marker, extra)
            for mk in line_marks:
                i2 = s.find(mk, pos)
                if i2 >= 0 and (best is None or i2 < best[0]
                                or (i2 == best[0] and len(mk) > len(best[2]))):
                    best = (i2, "line", mk, None)
            for st, en in blocks:
                i2 = s.find(st, pos)
                if i2 >= 0 and (best is None or i2 < best[0]
                                or (i2 == best[0] and len(st) > len(best[2]))):
                    best = (i2, "block", st, en)
            for d in strings:
                i2 = s.find(d, pos)
                if i2 >= 0 and (best is None or i2 < best[0]
                                or (i2 == best[0] and len(d) > len(best[2]))):
                    best = (i2, "str", d, None)
            if best is None:
                if include_code and s[pos:].strip():
                    out.append(("code", lineno, pos + 1, s[pos:]))
                break
            idx, kind, mk, extra = best
            if include_code and s[pos:idx].strip():
                out.append(("code", lineno, pos + 1, s[pos:idx]))
            if kind == "line":
                out.append(("comment", lineno, idx + 1, s[idx + len(mk):]))
                pos = n
            elif kind == "block":
                pos = idx + len(mk)
                block_end = extra
            else:
                if len(mk) >= 3:
                    pos = idx + len(mk)
                    triple = mk
                else:
                    j = idx + len(mk)
                    closed = False
                    while j < n:
                        if s[j] == "\\":
                            j += 2
                            continue
                        if s.startswith(mk, j):
                            j += len(mk)
                            closed = True
                            break
                        j += 1
                    end = j - len(mk) if closed else n
                    body = s[idx + len(mk):end]
                    if body:
                        out.append(("string", lineno, idx + len(mk) + 1, body))
                    pos = min(j, n)
    return out


# ---------------------------------------------------------------- 文件工具

def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for f in sorted(files):
                    yield os.path.join(root, f)
        else:
            raise FileNotFoundError(p)


def read_text_best(path):
    """尽力把文件读成文本；二进制（含 NUL）或超大的文件返回 None。"""
    with open(path, "rb") as fh:
        data = fh.read()
    if b"\x00" in data or len(data) > MAX_BYTES:
        return None
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


# ---------------------------------------------------------------- CJK 识别

CJK_RUN_RE = re.compile(
    "[\u2e80-\u2eff\u3000-\u303f\u3040-\u30ff\u31c0-\u31ef\u3200-\u32ff"
    "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af\ufe30-\ufe4f"
    "\uff00-\uffef]+")
HAN_RE = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_RE = re.compile("[\u3040-\u30ff]")
HANGUL_RE = re.compile("[\uac00-\ud7af]")


def classify_run(run):
    if KANA_RE.search(run):
        return "日文假名"
    if HANGUL_RE.search(run):
        return "韩文谚文"
    if HAN_RE.search(run):
        return "中文汉字"
    return "中文标点/全角符号"


def trim_context(s, limit=120):
    s = s.strip()
    return s if len(s) <= limit else s[:limit - 1] + "…"


# ---------------------------------------------------------------- 主流程

def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        prog=TOOL, description="扫描代码中的中文注释与中文字符串，输出国际化检查清单")
    ap.add_argument("paths", nargs="+", help="要扫描的文件或目录")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ap.add_argument("--fail-on-find", action="store_true",
                    help="发现 CJK 内容时以退出码 1 结束")
    ap.add_argument("--ext", action="append", default=[], metavar="EXT",
                    help="额外扫描的扩展名（如 .md），可重复")
    args = ap.parse_args(argv)

    for p in args.paths:
        if not os.path.exists(p):
            print(f"错误: 路径不存在: {p}", file=sys.stderr)
            return 2

    exts = {e.lower() for e in DEFAULT_EXTS}
    for e in args.ext:
        exts.add((e if e.startswith(".") else "." + e).lower())

    findings = []
    files_scanned = 0
    for path in iter_files(args.paths):
        ext = os.path.splitext(path)[1].lower()
        if ext not in exts:
            continue
        try:
            text = read_text_best(path)
        except OSError as exc:
            print(f"警告: 无法读取 {path}: {exc}", file=sys.stderr)
            continue
        if text is None:
            continue
        files_scanned += 1
        sp = spec_for(path)
        for kind, lineno, col, chunk in segment(text, sp, include_code=True):
            for m in CJK_RUN_RE.finditer(chunk):
                run = m.group(0)
                cat = classify_run(run)
                show = run if len(run) <= 24 else run[:23] + "…"
                findings.append({
                    "file": path, "line": lineno, "col": col + m.start(),
                    "kind": kind, "category": cat, "text": show,
                    "message": f'{KIND_LABEL[kind]}含 {cat}: “{show}”',
                    "context": trim_context(chunk),
                })
    findings.sort(key=lambda f: (f["file"], f["line"], f["col"]))

    by_kind = {}
    for f in findings:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1

    if args.json:
        print(json.dumps({"tool": TOOL, "files_scanned": files_scanned,
                          "total": len(findings), "by_kind": by_kind,
                          "findings": findings},
                         ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print(f'{f["file"]}:{f["line"]}:{f["col"]}  [{f["kind"]}] {f["message"]}')
            print(f'    | {f["context"]}')
        if not findings:
            print("未发现 CJK 内容。")
        kind_desc = "、".join(f'{KIND_LABEL[k]} {c} 处' for k, c in sorted(by_kind.items()))
        print(f"共扫描 {files_scanned} 个文件，发现 {len(findings)} 处 CJK 内容"
              + (f"（{kind_desc}）" if kind_desc else "") + "。")

    return 1 if (args.fail_on_find and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
