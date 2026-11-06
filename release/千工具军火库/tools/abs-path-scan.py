#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""abs-path-scan —— 硬编码绝对路径扫描（可移植性检查）。

查找代码与配置里写死的绝对路径，按耦合程度分级提示跨机器/跨平台会失效的路径：
Windows 盘符路径（如 C:\\... 或 C:/...，含用户目录/系统目录/临时目录细分）、
UNC 网络共享（\\\\server\\share）、Unix 系统路径（/Users/、/home/、/root/、
/etc/、/opt/、/var/、/tmp/、/usr/ 等）。 shebang 行（#!）视为可移植惯例，跳过。
Windows 路径与其中嵌套的 Unix 路径不会重复报告。发现需人工复核。

仅依赖 Python 标准库。

用法:
    python abs-path-scan.py src/                     # 递归扫描目录
    python abs-path-scan.py a.py config.yml --json   # 扫描指定文件, JSON 输出
    python abs-path-scan.py src/ --fail-on-find      # 有发现时退出码为 1

退出码: 0=正常（无论是否发现）; 1=--fail-on-find 且有发现; 2=参数或路径错误。
"""

import argparse
import json
import os
import re
import sys

TOOL = "abs-path-scan"

SKIP_DIRS = {".git", ".svn", ".hg", ".tox", ".idea", ".vscode", "node_modules",
             "__pycache__", ".mypy_cache", ".pytest_cache", ".venv", "venv",
             "dist", "build", ".eggs", "target"}
MAX_BYTES = 10 * 1024 * 1024

# ---------------------------------------------------------------- 匹配模式

# Windows 盘符路径：盘符前不能是单词字符/./:/-，排除 "https://" 之类误报
WIN_RE = re.compile(r"(?<![\w.:\-])[A-Za-z]:[\\/][^\s\"'<>|*?]*")
# UNC 网络共享：\\server\share\...
UNC_RE = re.compile(r"\\\\[A-Za-z0-9_.\-]+\\[^\s\"'<>|*?]+")
# Unix 常见根目录；前导排除单词字符/~/./://-，避免命中 URL 路径段与 C:/Users
UNIX_RE = re.compile(
    r"(?<![\w~.:/\-])/(?:Users|home|root|tmp|var|etc|opt|usr|mnt|media|srv"
    r"|Applications|Library|data|workspace|www)(?:/[^\s\"'<>|*?]*)?")

TRAIL_PUNCT = ".,;:!)]}>\"'"

SEVERITY_ORDER = ["critical", "high", "medium", "low"]


def trim_trailing(s):
    while s and s[-1] in TRAIL_PUNCT:
        s = s[:-1]
    return s


def classify_win(p):
    m = re.match(r"[A-Za-z]:[\\/](.*)$", p, re.S)
    rest = m.group(1) if m else ""
    first = re.split(r"[\\/]+", rest)[0].lower() if rest else ""
    low = p.lower()
    if first in ("users", "documents and settings"):
        return "high", "Windows 用户目录（用户名耦合）"
    if "appdata" in low or "local settings" in low:
        return "high", "Windows 用户配置目录（AppData）"
    if first == "windows":
        return "medium", "Windows 系统目录"
    if first in ("temp", "tmp"):
        return "low", "Windows 临时目录"
    return "medium", "Windows 绝对路径"


def classify_unix(p):
    stripped = p.strip("/")
    first = stripped.split("/")[0] if stripped else ""
    if first in ("Users", "home", "root"):
        return "high", f"Unix/macOS 用户主目录（/{first}/…）"
    if first == "tmp":
        return "low", "Unix 临时目录（/tmp）"
    if first in ("Applications", "Library"):
        return "medium", "macOS 系统目录"
    return "medium", "Unix 系统路径"


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
        prog=TOOL, description="查找硬编码绝对路径，提示可移植性问题")
    ap.add_argument("paths", nargs="+", help="要扫描的文件或目录")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ap.add_argument("--fail-on-find", action="store_true",
                    help="有发现时以退出码 1 结束")
    args = ap.parse_args(argv)

    for p in args.paths:
        if not os.path.exists(p):
            print(f"错误: 路径不存在: {p}", file=sys.stderr)
            return 2

    findings = []
    files_scanned = 0
    files_skipped = 0
    for path in iter_files(args.paths):
        try:
            text = read_text_best(path)
        except OSError as exc:
            print(f"警告: 无法读取 {path}: {exc}", file=sys.stderr)
            continue
        if text is None:
            files_skipped += 1
            continue
        files_scanned += 1
        for lineno, line in enumerate(text.splitlines(), 1):
            if lineno == 1 and line.startswith("#!"):
                continue  # shebang 是可移植惯例
            spans = []  # 已报告区间；嵌套其中的 Unix 路径不重复报
            for m in WIN_RE.finditer(line):
                p = trim_trailing(m.group(0))
                if len(p) < 3:
                    continue
                sev, label = classify_win(p)
                spans.append((m.start(), m.end()))
                findings.append({
                    "file": path, "line": lineno, "col": m.start() + 1,
                    "rule": "windows-path", "severity": sev,
                    "message": f"{label}: {p}",
                    "context": trim_context(line),
                })
            for m in UNC_RE.finditer(line):
                if any(a <= m.start() and m.end() <= b for a, b in spans):
                    continue
                p = trim_trailing(m.group(0))
                spans.append((m.start(), m.end()))
                findings.append({
                    "file": path, "line": lineno, "col": m.start() + 1,
                    "rule": "unc-path", "severity": "medium",
                    "message": f"UNC 网络共享路径（机器名耦合）: {p}",
                    "context": trim_context(line),
                })
            for m in UNIX_RE.finditer(line):
                if any(a <= m.start() and m.end() <= b for a, b in spans):
                    continue
                p = trim_trailing(m.group(0))
                if p.count("/") < 1:
                    continue
                sev, label = classify_unix(p)
                findings.append({
                    "file": path, "line": lineno, "col": m.start() + 1,
                    "rule": "unix-path", "severity": sev,
                    "message": f"{label}: {p}",
                    "context": trim_context(line),
                })
    findings.sort(key=lambda f: (f["file"], f["line"], f["col"]))

    by_sev = {}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1

    if args.json:
        print(json.dumps({"tool": TOOL, "files_scanned": files_scanned,
                          "files_skipped_binary": files_skipped,
                          "total": len(findings), "by_severity": by_sev,
                          "findings": findings},
                         ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print(f'{f["file"]}:{f["line"]}:{f["col"]}  [{f["severity"]}] {f["rule"]}: {f["message"]}')
            print(f'    | {f["context"]}')
        if not findings:
            print("未发现硬编码绝对路径。")
        sev_desc = "、".join(f"{k} {v} 处" for k, v in
                             sorted(by_sev.items(), key=lambda kv: SEVERITY_ORDER.index(kv[0])))
        print(f"共扫描 {files_scanned} 个文件（跳过二进制/超大 {files_skipped} 个），"
              f"发现 {len(findings)} 处硬编码路径"
              + (f"（{sev_desc}）" if sev_desc else "") + "。")

    return 1 if (args.fail_on_find and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
