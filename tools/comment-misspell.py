#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""comment-misspell —— 注释与字符串英文拼写检查（内置常见错拼词表）。

从源码中切出注释（#、//、/* */、<!-- -->、-- 等）与字符串字面量，用内置的
常见英文错拼词表逐词检查并给出建议写法；Markdown/TXT 等文档按普通文本整行检查。
只做词表精确匹配（含少量词形变化与所有格），不做模糊匹配，误报率低。

仅依赖 Python 标准库。

用法:
    python comment-misspell.py src/                     # 递归扫描目录
    python comment-misspell.py a.py b.js README.md      # 扫描指定文件
    python comment-misspell.py src/ --json              # JSON 输出
    python comment-misspell.py src/ --fail-on-find      # 有发现时退出码为 1
    python comment-misspell.py src/ -w adress=address   # 追加自定义错拼映射

退出码: 0=正常（无论是否发现）; 1=--fail-on-find 且有发现; 2=参数或路径错误。
"""

import argparse
import json
import os
import re
import sys

TOOL = "comment-misspell"

SKIP_DIRS = {".git", ".svn", ".hg", ".tox", ".idea", ".vscode", "node_modules",
             "__pycache__", ".mypy_cache", ".pytest_cache", ".venv", "venv",
             "dist", "build", ".eggs", "target"}
EXTRA_FILENAMES = {"Dockerfile", "Makefile", "GNUmakefile", "makefile"}
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
    block_end = None   # 处于块注释中：结束标记
    triple = None      # 处于三引号字符串中：定界符

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
            # 普通代码状态：找最早出现的特殊标记
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


# ---------------------------------------------------------------- 错拼词表

MISSPELL = {
    # 高频虚词/代词
    "teh": "the", "waht": "what", "thier": "their", "wierd": "weird",
    "wich": "which", "whcih": "which", "wether": "whether",
    # 常见动词/名词/形容词
    "recieve": "receive", "recieved": "received", "recieves": "receives",
    "recieving": "receiving", "reciept": "receipt",
    "beleive": "believe", "beleived": "believed", "beleives": "believes",
    "beleif": "belief",
    "seperate": "separate", "seperated": "separated", "seperately": "separately",
    "seperating": "separating", "seperation": "separation",
    "definately": "definitely", "definatly": "definitely",
    "occured": "occurred", "occuring": "occurring", "occurence": "occurrence",
    "occurance": "occurrence", "occassion": "occasion", "occassionally": "occasionally",
    "accomodate": "accommodate", "acheive": "achieve", "acheived": "achieved",
    "acheiving": "achieving", "adress": "address", "agressive": "aggressive",
    "alligned": "aligned", "alot": "a lot", "becuase": "because",
    "basicly": "basically", "carefull": "careful", "coudl": "could",
    "shoudl": "should", "woudl": "would", "doesnt": "doesn't", "dosnt": "doesn't",
    "cant": "can't", "wont": "won't", "begining": "beginning",
    "calender": "calendar", "collegue": "colleague", "comming": "coming",
    "commited": "committed", "concious": "conscious", "dilemna": "dilemma",
    "diffrent": "different", "disapear": "disappear", "durign": "during",
    "embarass": "embarrass", "enviroment": "environment", "equivelent": "equivalent",
    "existance": "existence", "experiance": "experience", "familar": "familiar",
    "finaly": "finally", "foriegn": "foreign", "freind": "friend",
    "fucntion": "function", "garantee": "guarantee", "guarentee": "guarantee",
    "gaurd": "guard", "goverment": "government", "grammer": "grammar",
    "happend": "happened", "hieght": "height", "independant": "independent",
    "immediatly": "immediately", "intergrate": "integrate", "intrest": "interest",
    "knowlege": "knowledge", "langauge": "language", "lenght": "length",
    "lenth": "length", "liason": "liaison", "libary": "library",
    "lisence": "license", "maintainance": "maintenance", "maintenence": "maintenance",
    "managable": "manageable", "managment": "management", "millenium": "millennium",
    "neccessary": "necessary", "negotation": "negotiation", "noticable": "noticeable",
    "numberous": "numerous", "offical": "official", "paralell": "parallel",
    "paramater": "parameter", "paramter": "parameter",
    "perseverence": "perseverance", "posession": "possession",
    "possable": "possible", "posion": "poison", "potentail": "potential",
    "prefered": "preferred", "privelege": "privilege", "probaly": "probably",
    "proccess": "process", "pronounciation": "pronunciation",
    "publically": "publicly", "realy": "really", "recommand": "recommend",
    "recomend": "recommend", "refered": "referred", "relevent": "relevant",
    "religous": "religious", "remeber": "remember", "repitition": "repetition",
    "resistence": "resistance", "resturant": "restaurant", "retreive": "retrieve",
    "retrive": "retrieve", "rhythem": "rhythm", "ridiculus": "ridiculous",
    "sence": "sense", "similiar": "similar", "sincerly": "sincerely",
    "speach": "speech", "strenght": "strength", "succesful": "successful",
    "successfull": "successful", "sucess": "success", "suceed": "succeed",
    "supercede": "supersede", "supress": "suppress", "suprise": "surprise",
    "suport": "support", "techinque": "technique", "threshhold": "threshold",
    "thruogh": "through", "tommorow": "tomorrow", "truely": "truly",
    "untill": "until", "usefull": "useful", "vaccum": "vacuum",
    "varient": "variant", "writting": "writing", "writen": "written",
    "wrok": "work", "yeild": "yield",
}

WORD_RE = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)*")


def lookup(word, dic):
    if word in dic:
        return dic[word]
    if word.endswith("'s") and word[:-2] in dic:
        return dic[word[:-2]] + "'s"
    if word.endswith("s") and word[:-1] in dic:
        return dic[word[:-1]] + "s"
    return None


def apply_case(word, sug):
    if len(word) > 1 and word.isupper():
        return sug.upper()
    if word[:1].isupper():
        return sug[:1].upper() + sug[1:]
    return sug


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
        prog=TOOL, description="注释与字符串英文拼写检查（内置常见错拼词表）")
    ap.add_argument("paths", nargs="+", help="要检查的文件或目录")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ap.add_argument("--fail-on-find", action="store_true",
                    help="发现错拼时以退出码 1 结束")
    ap.add_argument("-w", "--word", action="append", default=[],
                    metavar="WRONG=RIGHT", help="追加自定义错拼映射，可重复")
    ap.add_argument("--ext", action="append", default=[], metavar="EXT",
                    help="额外扫描的扩展名（如 .inc），可重复")
    args = ap.parse_args(argv)

    for p in args.paths:
        if not os.path.exists(p):
            print(f"错误: 路径不存在: {p}", file=sys.stderr)
            return 2

    dic = dict(MISSPELL)
    for pair in args.word:
        if "=" not in pair:
            print(f"错误: -w 需要 WRONG=RIGHT 格式: {pair}", file=sys.stderr)
            return 2
        w, r = pair.split("=", 1)
        dic[w.strip().lower()] = r.strip()

    exts = set(KNOWN_EXT)
    for e in args.ext:
        exts.add(e if e.startswith(".") else "." + e)
    exts = {e.lower() for e in exts}

    findings = []
    files_scanned = 0
    for path in iter_files(args.paths):
        ext = os.path.splitext(path)[1].lower()
        if ext not in exts and os.path.basename(path) not in EXTRA_FILENAMES:
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
        for kind, lineno, col, chunk in segment(text, sp):
            if kind == "code":
                continue
            for m in WORD_RE.finditer(chunk):
                raw = m.group(0)
                sug = lookup(raw.lower(), dic)
                if not sug:
                    continue
                findings.append({
                    "file": path, "line": lineno, "col": col + m.start(),
                    "kind": kind, "word": raw, "suggestion": apply_case(raw, sug),
                    "message": f'错拼 “{raw}” → 建议 “{apply_case(raw, sug)}”',
                    "context": trim_context(chunk),
                })
    findings.sort(key=lambda f: (f["file"], f["line"], f["col"]))

    if args.json:
        print(json.dumps({"tool": TOOL, "files_scanned": files_scanned,
                          "total": len(findings), "findings": findings},
                         ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print(f'{f["file"]}:{f["line"]}:{f["col"]}  [{f["kind"]}] {f["message"]}')
            print(f'    | {f["context"]}')
        if not findings:
            print("未发现错拼。")
        print(f"共扫描 {files_scanned} 个文件，发现 {len(findings)} 处疑似错拼。")

    return 1 if (args.fail_on_find and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
