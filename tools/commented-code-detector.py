#!/usr/bin/env python3
"""注释掉的代码检测（commented-code-detector）——用启发式规则找出被注释掉的代码块。

对常见注释风格（#、//、--，以及 C 家族的 /* */ 块注释）逐行剥掉注释前缀，
再按启发式特征给每行打分：return/break 等强特征、行尾分号、函数调用结尾、
赋值、括号密度、Python 控制行等加分；英文散文词（the/should/because…）与
句号结尾等减分。连续注释行达到 --min-lines（默认 3）行、其中至少 2 行得分
>= 2 且平均分 >= 1.0 时判为"疑似注释掉的代码块"。启发式工具，可能有误报/漏报。
仅依赖 Python 标准库。

用法:
    python commented-code-detector.py [路径...] [--min-lines N] [--style auto|#|//|--]

示例:
    python commented-code-detector.py src/ --min-lines 4

自测（构造临时示例文件）:
    python -I commented-code-detector.py --self-test
"""

from __future__ import annotations

import argparse
import os
import re
import sys

LINE_STYLES = {
    ".py": "#", ".pyw": "#", ".sh": "#", ".bash": "#", ".rb": "#",
    ".yml": "#", ".yaml": "#", ".toml": "#", ".pl": "#", ".r": "#",
    ".js": "//", ".mjs": "//", ".cjs": "//", ".ts": "//", ".tsx": "//", ".jsx": "//",
    ".java": "//", ".c": "//", ".h": "//", ".cpp": "//", ".cc": "//", ".cxx": "//",
    ".hpp": "//", ".hh": "//", ".cs": "//", ".go": "//", ".rs": "//",
    ".swift": "//", ".kt": "//", ".kts": "//", ".php": "//", ".dart": "//", ".scala": "//",
    ".lua": "--", ".sql": "--", ".hs": "--",
}
BLOCK_LANG_EXTS = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".java", ".c", ".h",
                   ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".cs", ".go", ".rs",
                   ".swift", ".kt", ".kts", ".php", ".dart", ".scala"}

CODE_KW_RE = re.compile(
    r"\b(return|break|continue|raise|throw|yield|if|elif|else|for|while|switch|case|"
    r"catch|except|finally|try|def|class|function|fn|var|let|const|import|from|package|"
    r"new|delete|assert|await|async|struct|enum|public|private|protected|static|void|"
    r"int|float|double|bool|string)\b")
STRONG_RE = re.compile(r"\b(return|break|continue|raise|throw|yield)\b")
ENDS_SEMI_RE = re.compile(r"[)\]\w\"']\s*;\s*$")
CALL_END_RE = re.compile(r"\w+\s*\(.*\)\s*;?\s*$")
ASSIGN_RE = re.compile(r"\w[\w.\[\]\"']*\s*(?:=|:=|<-|\+=|-=)[^=]")
PY_CTRL_RE = re.compile(
    r"^(?:if|elif|else|for|while|def|class|try|except|finally|with)\b[^:]*:\s*$")
PROSE_RE = re.compile(
    r"\b(the|this|that|these|those|with|when|we|you|they|should|would|could|because|"
    r"about|will|need|want|please|see|note|todo)\b", re.I)

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__",
             ".venv", "venv", ".tox", "dist", "build", ".idea", ".vscode"}
MAX_FILE_SIZE = 2 * 1024 * 1024


def read_lines(path):
    """把文件读成文本行；二进制（含 NUL）或超过大小上限时返回 None。"""
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_FILE_SIZE + 1)
    except OSError:
        return None
    if b"\x00" in data or len(data) > MAX_FILE_SIZE:
        return None
    return data.decode("utf-8", errors="replace").splitlines()


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for name in sorted(files):
                    yield os.path.join(root, name)


def score_line(text):
    """对剥掉注释前缀后的文本打"代码感"分；空文本返回 None。"""
    s = text.strip()
    if not s:
        return None
    score = 0
    if STRONG_RE.search(s):
        score += 2
    elif CODE_KW_RE.search(s):
        score += 1
    if ENDS_SEMI_RE.search(s):
        score += 1
    if CALL_END_RE.search(s):
        score += 1
    if ASSIGN_RE.search(s):
        score += 1
    if s.count("(") + s.count("[") + s.count("{") >= 2:
        score += 1
    if PY_CTRL_RE.match(s):
        score += 1
    has_punct = ("(" in s or "=" in s or ";" in s or "{" in s)
    if not has_punct:
        if PROSE_RE.search(s):
            score -= 2
        if re.search(r"[.!?]$", s) and " " in s:
            score -= 2
    return score


def make_parser(ext, style_opt):
    """按扩展名/强制风格构造行解析器，返回 parse(raw) -> (kind, text) 或 None。"""
    style = None if style_opt == "auto" else style_opt
    if style is None:
        style = LINE_STYLES.get(ext)
    if style is None:
        return None
    block = ext in BLOCK_LANG_EXTS
    state = {"in_block": False}

    def parse(raw):
        s = raw.strip()
        if not s:
            return "blank", ""
        if block:
            if state["in_block"]:
                if "*/" in s:
                    state["in_block"] = False
                    s = s.split("*/", 1)[0]
                text = s.lstrip("*").strip()
                return ("comment", text) if text else ("blank", "")
            if "/*" in s:
                after = s.split("/*", 1)[1]
                if "*/" in after:
                    text = after.split("*/", 1)[0].strip()
                else:
                    state["in_block"] = True
                    text = after.strip()
                return ("comment", text) if text else ("blank", "")
        if s.startswith(style):
            text = s[len(style):]
            if style == "#":
                text = text.lstrip("#!")
            return "comment", text.strip()
        return "code", ""

    return parse


def detect(paths, min_lines=3, style_opt="auto"):
    """返回 (疑似注释代码块列表, 统计信息)。"""
    findings = []
    skipped = 0
    nfiles = 0
    for path in iter_files(paths):
        lines = read_lines(path)
        if lines is None:
            continue
        parse = make_parser(os.path.splitext(path)[1].lower(), style_opt)
        if parse is None:
            skipped += 1
            continue
        nfiles += 1
        runs = []
        cur = []
        for i, raw in enumerate(lines, 1):
            kind, text = parse(raw)
            if kind == "comment":
                cur.append((i, text))
            else:
                if cur:
                    runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        for run in runs:
            if len(run) < min_lines:
                continue
            scored = [(ln, t, score_line(t)) for ln, t in run if t]
            if len(scored) < min_lines:
                continue
            vals = [sc for _, _, sc in scored]
            n_code = sum(1 for v in vals if v >= 2)
            avg = sum(vals) / len(vals)
            if n_code >= 2 and avg >= 1.0:
                findings.append({"path": path, "start": run[0][0], "end": run[-1][0],
                                 "avg": avg, "lines": [t for _, t, _ in scored]})
    return findings, {"files": nfiles, "skipped": skipped}


def render(findings, stats):
    for f in findings:
        print("%s:%d-%d  (%d 行, 平均分 %.1f)"
              % (f["path"], f["start"], f["end"], len(f["lines"]), f["avg"]))
        for t in f["lines"][:3]:
            print("    | %s" % t[:100])
        if len(f["lines"]) > 3:
            print("    | ...")
    print("---")
    print("扫描 %d 个文件（跳过 %d 个无法识别注释风格的文件）, 疑似注释掉的代码块 %d 处"
          % (stats["files"], stats["skipped"], len(findings)))


def self_test():
    """构造含注释代码块与散文注释的临时文件，断言只报代码块、不误报散文。"""
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="dead-code-")
    try:
        py_src = ("import os\n"
                  "\n"
                  "# def old_calc(x):\n"
                  "#     if x > 0:\n"
                  "#         return x * 2\n"
                  "#     return 0\n"
                  "\n"
                  "# This module handles the parsing logic.\n"
                  "# We should refactor it someday because it is slow.\n"
                  "# See the design document for more details.\n"
                  "\n"
                  "def add(a, b):\n"
                  "    return a + b\n")
        js_src = ("function main() {\n"
                  "    run();\n"
                  "}\n"
                  "\n"
                  "// const x = compute(a, b);\n"
                  "// if (x > 10) {\n"
                  "//     console.log(x);\n"
                  "// }\n"
                  "// This block is disabled for now.\n"
                  "\n"
                  "/* let total = 0;\n"
                  "   for (let i = 0; i < 10; i++) {\n"
                  "       total += i;\n"
                  "*/\n")
        with open(os.path.join(tmp, "code.py"), "w", encoding="utf-8") as f:
            f.write(py_src)
        with open(os.path.join(tmp, "app.js"), "w", encoding="utf-8") as f:
            f.write(js_src)
        findings, stats = detect([tmp], min_lines=3)
        spans = {(os.path.basename(f["path"]), f["start"], f["end"]) for f in findings}
        # js 5-9 行为同一连续注释 run：4 行代码 + 1 行拖尾说明，随块一起报告
        want = {("code.py", 3, 6), ("app.js", 5, 9), ("app.js", 11, 13)}
        assert spans == want, "检测到的代码块不符: %s" % sorted(spans)
        # 纯散文注释块（code.py 8-10 行）必须不被误报
        assert ("code.py", 8, 10) not in spans, "纯散文注释块被误报"
        assert stats["files"] == 2 and stats["skipped"] == 0, "统计不符: %s" % stats
        render(findings, stats)
        print("检测断言全部通过（3 处代码块命中，纯散文注释块未误报）")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "--self-test" in argv:
        argv = [a for a in argv if a != "--self-test"]
        try:
            rc = self_test()
        except AssertionError as exc:
            print("SELF-TEST FAIL: %s" % exc)
            return 1
        except Exception as exc:
            print("SELF-TEST FAIL: %s: %s" % (type(exc).__name__, exc))
            return 1
        print("SELF-TEST PASS")
        return rc
    parser = argparse.ArgumentParser(
        description="注释掉的代码检测：用启发式规则找出被注释掉的代码块")
    parser.add_argument("paths", nargs="*", default=["."],
                        help="要扫描的文件或目录（默认当前目录）")
    parser.add_argument("--min-lines", type=int, default=3, metavar="N",
                        help="判为代码块所需的最少连续注释行数（默认 3）")
    parser.add_argument("--style", choices=["auto", "#", "//", "--"], default="auto",
                        help="强制注释风格（默认按扩展名自动识别）")
    args = parser.parse_args(argv)
    findings, stats = detect(args.paths, min_lines=args.min_lines, style_opt=args.style)
    render(findings, stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
