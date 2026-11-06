#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hardcoded-ip-scan —— 硬编码 IP 与内网 URL 扫描。

查找代码与配置中写死的 IPv4/IPv6 地址与 http(s) URL，并按类别标注环境耦合风险：
内网 IP（10/8、172.16/12、192.168/16 等）、CGNAT、链路本地、公网 IP、
内网域名/主机名 URL（.local/.lan/.internal/.corp 或无后缀单标签主机名）。
默认跳过回环（127.0.0.0/8、::1）、0.0.0.0、广播与组播地址；--all 可一并显示。
URL 内已覆盖的 IP 不重复报告。发现需人工复核，属提示而非定论。

仅依赖 Python 标准库。

用法:
    python hardcoded-ip-scan.py src/                  # 递归扫描目录
    python hardcoded-ip-scan.py a.py config.yml --json # 扫描指定文件, JSON 输出
    python hardcoded-ip-scan.py src/ --all            # 连回环/通配/组播一起列出
    python hardcoded-ip-scan.py src/ --fail-on-find   # 有发现时退出码为 1

退出码: 0=正常（无论是否发现）; 1=--fail-on-find 且有发现; 2=参数或路径错误。
"""

import argparse
import json
import os
import re
import sys

TOOL = "hardcoded-ip-scan"

SKIP_DIRS = {".git", ".svn", ".hg", ".tox", ".idea", ".vscode", "node_modules",
             "__pycache__", ".mypy_cache", ".pytest_cache", ".venv", "venv",
             "dist", "build", ".eggs", "target"}
MAX_BYTES = 10 * 1024 * 1024

# ---------------------------------------------------------------- 匹配模式

OCT = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
IPV4_RE = re.compile(r"(?<![\d.])" + OCT + r"(?:\." + OCT + r"){3}(?![\d.])")
URL_RE = re.compile(
    r"(?i)\bhttps?://(" + OCT + r"(?:\." + OCT + r"){3}"
    r"|[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*)(?=[:/?#\s\"']|$)")
IPV4_FULL_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")
IPV6_ULA_RE = re.compile(r"\b(?:fc|fd)[0-9a-f]{2}(?::[0-9a-f]{1,4}){1,7}\b", re.I)
IPV6_LL_RE = re.compile(r"\bfe80(?::[0-9a-f]{0,4}){1,7}\b", re.I)
IPV6_LOOP_RE = re.compile(r"(?<![\w:])::1(?![\w:])")

INTRANET_TLDS = {"local", "lan", "internal", "intra", "corp", "priv",
                 "localdomain", "home", "workgroup"}

SEV = {
    "private":   ("high", "内网 IP"),
    "cgnat":     ("medium", "CGNAT 段 IP"),
    "linklocal": ("low", "链路本地 IP"),
    "public":    ("medium", "公网 IP"),
    "doc":       ("low", "文档保留段 IP"),
    "loopback":  ("low", "回环地址"),
    "wildcard":  ("low", "通配地址"),
    "broadcast": ("low", "广播地址"),
    "multicast": ("low", "组播地址"),
}
SKIP_DEFAULT = {"loopback", "wildcard", "broadcast", "multicast"}


def ip_category(ip):
    parts = [int(x) for x in ip.split(".")]
    a, b, c = parts[0], parts[1], parts[2]
    if ip == "0.0.0.0":
        return "wildcard"
    if a == 127:
        return "loopback"
    if a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168):
        return "private"
    if a == 169 and b == 254:
        return "linklocal"
    if a == 100 and 64 <= b <= 127:
        return "cgnat"
    if ip == "255.255.255.255":
        return "broadcast"
    if 224 <= a <= 239:
        return "multicast"
    if ((a == 192 and b == 0 and c == 2) or (a == 198 and b in (18, 19))
            or (a == 203 and b == 0 and c == 113)):
        return "doc"
    return "public"


def url_category(host, all_mode):
    """对 URL 主机名分类；返回 (sev, label) 或 None（不需要报告）。"""
    host = host.lower()
    if IPV4_FULL_RE.fullmatch(host):
        cat = ip_category(host)
        if cat in SKIP_DEFAULT and not all_mode:
            return None
        sev, label = SEV[cat]
        return (sev, f"{label} URL（{host}）")
    if host == "localhost" and not all_mode:
        return None
    labels = host.split(".")
    if len(labels) == 1:
        return ("medium", f"内网主机名 URL（{host}，无域名后缀）")
    tld = labels[-1]
    if tld in INTRANET_TLDS or host.endswith(".home.arpa"):
        return ("high", f"内网域名 URL（.{tld}）")
    return None  # 外部域名，不报


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
        prog=TOOL, description="查找代码中写死的 IP 地址与内网 URL，标记可疑环境耦合")
    ap.add_argument("paths", nargs="+", help="要扫描的文件或目录")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ap.add_argument("--all", action="store_true",
                    help="连回环/通配/广播/组播地址也列出")
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
            spans = []  # 已报告的区间；URL 覆盖范围内的 IP 不再单列
            for m in URL_RE.finditer(line):
                cat = url_category(m.group(1), args.all)
                spans.append((m.start(), m.end()))
                if cat is None:
                    continue
                sev, label = cat
                findings.append({
                    "file": path, "line": lineno, "col": m.start() + 1,
                    "rule": "hardcoded-url", "severity": sev,
                    "message": f'{label}: {trim_context(m.group(0), 100)}',
                    "context": trim_context(line),
                })
            for m in IPV4_RE.finditer(line):
                if any(a <= m.start() and m.end() <= b for a, b in spans):
                    continue
                cat = ip_category(m.group(0))
                if cat in SKIP_DEFAULT and not args.all:
                    continue
                sev, label = SEV[cat]
                findings.append({
                    "file": path, "line": lineno, "col": m.start() + 1,
                    "rule": "hardcoded-ip", "severity": sev,
                    "message": f"{label}: {m.group(0)}",
                    "context": trim_context(line),
                })
            for pat, rule, sev, label in (
                    (IPV6_ULA_RE, "hardcoded-ipv6-ula", "high", "内网 IPv6（ULA fc00::/7）"),
                    (IPV6_LL_RE, "hardcoded-ipv6-linklocal", "low", "IPv6 链路本地（fe80::/10）")):
                for m in pat.finditer(line):
                    if any(a <= m.start() and m.end() <= b for a, b in spans):
                        continue
                    findings.append({
                        "file": path, "line": lineno, "col": m.start() + 1,
                        "rule": rule, "severity": sev,
                        "message": f"{label}: {m.group(0)}",
                        "context": trim_context(line),
                    })
            if args.all:
                for m in IPV6_LOOP_RE.finditer(line):
                    if any(a <= m.start() and m.end() <= b for a, b in spans):
                        continue
                    findings.append({
                        "file": path, "line": lineno, "col": m.start() + 1,
                        "rule": "hardcoded-ipv6-loopback", "severity": "low",
                        "message": "IPv6 回环地址: ::1",
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
            print("未发现硬编码 IP 或内网 URL。")
        sev_desc = "、".join(f"{k} {v} 处" for k, v in sorted(by_sev.items()))
        print(f"共扫描 {files_scanned} 个文件（跳过二进制/超大 {files_skipped} 个），"
              f"发现 {len(findings)} 处硬编码地址"
              + (f"（{sev_desc}）" if sev_desc else "") + "。")

    return 1 if (args.fail_on_find and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
