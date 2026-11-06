#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""secret-pattern-scan —— 硬编码密钥/口令/Token 扫描。

用一组内置正则模式查找代码与配置文件中疑似硬编码的敏感串：已知密钥格式
（AWS/Google/Slack/Stripe/GitHub）、JWT、PEM 私钥文件头、password=... 形式的
键值赋值、数据库连接串内嵌口令、URL 内嵌凭据、Bearer Token。
默认把敏感值打码输出，避免报告本身泄露密钥（--no-mask 可关闭）。
对赋值类发现做了占位符/环境变量/常量名过滤以降噪，但结果仍需人工复核。

仅依赖 Python 标准库。

用法:
    python secret-pattern-scan.py src/                  # 递归扫描目录
    python secret-pattern-scan.py .env deploy.yaml      # 扫描指定文件
    python secret-pattern-scan.py src/ --json           # JSON 输出
    python secret-pattern-scan.py src/ --no-mask        # 不打码（仅本地自查用）
    python secret-pattern-scan.py src/ --fail-on-find   # 有发现时退出码为 1

退出码: 0=正常（无论是否发现）; 1=--fail-on-find 且有发现; 2=参数或路径错误。
"""

import argparse
import json
import math
import os
import re
import sys

TOOL = "secret-pattern-scan"

SKIP_DIRS = {".git", ".svn", ".hg", ".tox", ".idea", ".vscode", "node_modules",
             "__pycache__", ".mypy_cache", ".pytest_cache", ".venv", "venv",
             "dist", "build", ".eggs", "target"}
MAX_BYTES = 10 * 1024 * 1024

# ---------------------------------------------------------------- 检测规则

RULES = [
    {"id": "private-key", "sev": "critical", "label": "PEM 私钥文件头",
     "re": r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----", "group": 0},
    {"id": "aws-access-key", "sev": "high", "label": "AWS Access Key ID",
     "re": r"\bAKIA[0-9A-Z]{16}\b", "group": 0},
    {"id": "aws-secret-key", "sev": "high", "label": "疑似 AWS Secret Access Key（40 位凭据串）",
     "re": r"(?i)aws.{0,40}?['\"][0-9a-zA-Z/+]{40}['\"]", "group": 0},
    {"id": "google-api-key", "sev": "high", "label": "Google API Key",
     "re": r"\bAIza[0-9A-Za-z_\-]{35}\b", "group": 0},
    {"id": "github-token", "sev": "high", "label": "GitHub Token",
     "re": r"\b(?:gh[pousr]_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{22,255})\b",
     "group": 0},
    {"id": "slack-token", "sev": "high", "label": "Slack Token",
     "re": r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b", "group": 0},
    {"id": "stripe-key", "sev": "high", "label": "Stripe 密钥",
     "re": r"\b[sr]k_(?:live|test)_[0-9a-zA-Z]{16,}\b", "group": 0},
    {"id": "bearer-token", "sev": "high", "label": "Bearer Token",
     "re": r"(?i)\bBearer\s+[A-Za-z0-9._\-]{16,}\b", "group": 0},
    {"id": "jwt", "sev": "high", "label": "JWT",
     "re": r"\beyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\b",
     "group": 0},
    {"id": "db-uri-credentials", "sev": "high", "label": "数据库连接串内嵌口令",
     "re": r"(?i)\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis|amqps?|mssql)"
           r"://[^\s:@/\"']+:(?P<cred>[^\s@/\"']+)@",
     "gname": "cred"},
    {"id": "url-credentials", "sev": "medium", "label": "URL 内嵌用户凭据",
     "re": r"\b[a-z][a-z0-9+.\-]*://[^\s/:@\"']+:[^\s/:@\"']+@", "group": 0},
    {"id": "keyword-assignment", "sev": "medium", "label": "疑似口令/密钥明文赋值",
     "re": r"(?i)\b(pass(?:word|wd)?|pwd|secret|token|api[_\-]?key|access[_\-]?key"
           r"|secret[_\-]?key|auth[_\-]?token|client[_\-]?secret|consumer[_\-]?key"
           r"|private[_\-]?key|credentials?)\b[\"']?\s*[:=]\s*[\"']?([^\s\"'#;]{6,})",
     "group": 2},
]
for _r in RULES:
    _r["compiled"] = re.compile(_r["re"])

PLACEHOLDER_WORDS = {
    "changeme", "change_me", "change-me", "your_password", "your-password",
    "your_api_key", "your-token", "your_secret", "password", "passwd",
    "secret", "token", "placeholder", "example", "sample", "dummy", "fake",
    "todo", "tbd", "none", "null", "nil", "true", "false", "xxx", "xxxx",
    "xxxxxx", "test", "testing", "notset", "not_set", "unset", "default",
}
PLACEHOLDER_RE = re.compile(
    r"^(?:\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|%[A-Za-z_][A-Za-z0-9_]*%"
    r"|\{\{[^}]*\}\}|\{[\w.\-]+\}|<[^>]*>|\*+|\.+|x{3,}|X{3,}|-{3,}|_+)$")
CONST_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def is_placeholder(value):
    v = value.strip().strip("'\"")
    if v.lower() in PLACEHOLDER_WORDS:
        return True
    if PLACEHOLDER_RE.match(v):
        return True
    if CONST_RE.match(v):        # 全大写常量名，多为变量引用而非明文
        return True
    return False


def mask(s):
    if len(s) <= 6:
        return "*" * len(s)
    return s[:3] + "*" * (len(s) - 5) + s[-2:]


def shannon_entropy(s):
    if not s:
        return 0.0
    freq = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


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
        prog=TOOL, description="用正则模式查找疑似硬编码的密码、API key、token 等敏感串")
    ap.add_argument("paths", nargs="+", help="要扫描的文件或目录")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ap.add_argument("--no-mask", action="store_true",
                    help="不在报告中打码敏感值（仅建议本地自查时使用）")
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
            spans = []  # 本行已报告的区间，用于去重（包含关系）
            for rule in RULES:
                for m in rule["compiled"].finditer(line):
                    s, e = m.start(), m.end()
                    if any((a <= s and e <= b) or (s <= a and b <= e)
                           for a, b in spans):
                        continue
                    if "gname" in rule:
                        secret = m.group(rule["gname"])
                        gstart = m.start(rule["gname"])
                    elif rule["group"] == 0:
                        secret = m.group(0)
                        gstart = m.start(0)
                    else:
                        secret = m.group(rule["group"])
                        gstart = m.start(rule["group"])
                    if rule["id"] == "keyword-assignment" and is_placeholder(secret):
                        continue
                    spans.append((s, e))
                    shown_secret = secret if args.no_mask else mask(secret)
                    full = m.group(0)
                    off = gstart - m.start(0)
                    shown = full[:off] + shown_secret + full[off + len(secret):]
                    note = ""
                    if rule["id"] == "keyword-assignment":
                        ent = shannon_entropy(secret)
                        if ent >= 3.5:
                            note = f"（值熵 {ent:.2f}，偏高，建议人工确认）"
                    findings.append({
                        "file": path, "line": lineno, "col": s + 1,
                        "rule": rule["id"], "severity": rule["sev"],
                        "message": f'{rule["label"]}: {shown}{note}',
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
            print("未发现疑似硬编码密钥。")
        sev_desc = "、".join(f"{k} {v} 处" for k, v in sorted(by_sev.items()))
        print(f"共扫描 {files_scanned} 个文件（跳过二进制/超大 {files_skipped} 个），"
              f"发现 {len(findings)} 处疑似敏感串"
              + (f"（{sev_desc}）" if sev_desc else "") + "。")

    return 1 if (args.fail_on_find and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
