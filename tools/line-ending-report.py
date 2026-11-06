#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""换行符体检（line-ending-report）

用途：
    检测每个文件使用 LF（\\n）、CRLF（\\r\\n）还是 CR（\\r）换行，
    标记混用文件并给出各类换行所在行号，输出换行风格一致性报告
    （风格分布、主导风格与一致率）。

示例命令：
    python -I line-ending-report.py src/
    python -I line-ending-report.py . --ext .py,.txt --show 10
    python -I line-ending-report.py a.txt b.txt  # 不支持多路径，请逐个或扫目录

判定规则：
    * 以字节流检测，不受文本编码影响；
    * 某行以 \\r\\n 结尾 → CRLF；仅 \\n → LF；仅 \\r → CR；
      末行无换行符不影响判定；无任何换行 → 无换行；
    * 同一文件出现多种换行 → 混用；
    * 二进制文件（前 8KB 含 \\0）自动跳过。

退出码：0 正常；2 参数或路径错误。仅依赖 Python 标准库。
"""

import argparse
import os
import sys
import unicodedata
from collections import Counter

DEFAULT_EXCLUDES = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules", "venv", ".venv",
    "dist", "build", ".idea", ".vscode", ".tox", ".mypy_cache",
}

DEFAULT_EXT_SPEC = (
    ".py,.pyw,.js,.mjs,.cjs,.ts,.tsx,.jsx,.java,.kt,.kts,.scala,.go,.rs,"
    ".c,.h,.cpp,.hpp,.cc,.cxx,.cs,.swift,.rb,.php,.pl,.lua,.dart,.groovy,"
    ".sh,.bash,.zsh,.ps1,.bat,.cmd,.sql,.html,.htm,.css,.scss,.less,.vue,"
    ".json,.yaml,.yml,.toml,.ini,.cfg,.conf,.xml,.md,.txt"
)

STYLE_ORDER = ("LF", "CRLF", "CR", "混用", "无换行")


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
    """递归列出待检测文件；exts=None 表示不限扩展名。"""
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


def _rel(path, root):
    if os.path.isdir(root):
        try:
            return os.path.relpath(path, root).replace(os.sep, "/")
        except ValueError:
            pass
    return path.replace(os.sep, "/")


def analyze(path, show):
    """按字节检测换行风格；二进制文件返回 None。"""
    with open(path, "rb") as f:
        data = f.read()
    if b"\x00" in data[:8192]:
        return None
    counts = {"CRLF": 0, "LF": 0, "CR": 0}
    none_end = 0
    at = {"CRLF": [], "LF": [], "CR": []}
    for idx, ln in enumerate(data.splitlines(keepends=True), 1):
        if ln.endswith(b"\r\n"):
            k = "CRLF"
        elif ln.endswith(b"\n"):
            k = "LF"
        elif ln.endswith(b"\r"):
            k = "CR"
        else:
            none_end += 1
            continue
        counts[k] += 1
        if len(at[k]) < show:
            at[k].append(idx)
    kinds = [k for k in ("CRLF", "LF", "CR") if counts[k]]
    if len(kinds) > 1:
        style = "混用"
    elif kinds:
        style = kinds[0]
    else:
        style = "无换行"
    return {"style": style, "CRLF": counts["CRLF"], "LF": counts["LF"],
            "CR": counts["CR"], "none": none_end, "at": at}


def _pct(part, total):
    return "%.1f%%" % (100.0 * part / total) if total else "-"


def main(argv=None):
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        prog="line-ending-report",
        description="检测各文件是 LF、CRLF 还是混用，输出换行风格一致性报告。")
    ap.add_argument("path", help="要体检的文件或目录")
    ap.add_argument("--ext", default=DEFAULT_EXT_SPEC,
                    help="仅检测这些扩展名（逗号分隔；'*'=全部文件）")
    ap.add_argument("--top", type=int, default=0,
                    help="文件明细表最多显示 N 行（0=全部）")
    ap.add_argument("--show", type=int, default=5,
                    help="混用文件每种换行最多列出的行号个数（默认 5）")
    ap.add_argument("--exclude", default="", help="额外排除的目录名（逗号分隔）")
    args = ap.parse_args(argv)

    if not os.path.exists(args.path):
        print("错误：路径不存在：%s" % args.path, file=sys.stderr)
        return 2

    excludes = set(DEFAULT_EXCLUDES)
    excludes |= {x.strip() for x in args.exclude.split(",") if x.strip()}
    exts = parse_exts(args.ext)

    infos = []
    n_bin = 0
    for path in iter_files(args.path, exts, excludes):
        try:
            info = analyze(path, args.show)
        except OSError as exc:
            print("警告：无法读取 %s：%s" % (path, exc), file=sys.stderr)
            continue
        if info is None:
            n_bin += 1
            continue
        infos.append((_rel(path, args.path), info))
    if args.top > 0:
        shown = infos[:args.top]
    else:
        shown = infos

    print("== 换行符体检：%s ==" % args.path)
    print("检测文件 %d 个（二进制跳过 %d 个）" % (len(infos), n_bin))
    print()

    headers = ("文件", "风格", "CRLF", "LF", "CR", "无换行")
    rows = [(rel, i["style"], str(i["CRLF"]), str(i["LF"]),
             str(i["CR"]), str(i["none"])) for rel, i in shown]
    widths = []
    for col, h in enumerate(headers):
        w = _dw(h)
        for r in rows:
            w = max(w, _dw(r[col]))
        widths.append(w)
    right_cols = {2, 3, 4, 5}

    def fmt(cells):
        parts = []
        for col, cell in enumerate(cells):
            gap = max(widths[col] - _dw(cell), 0)
            parts.append(" " * gap + cell if col in right_cols
                         else cell + " " * gap)
        return "  ".join(parts).rstrip()

    print(fmt(headers))
    for r in rows:
        print(fmt(r))
    if args.top > 0 and len(infos) > len(shown):
        print("…（仅显示前 %d 个，共 %d 个）" % (len(shown), len(infos)))

    mixed = [(rel, i) for rel, i in shown if i["style"] == "混用"]
    if mixed:
        print()
        print("混用文件明细：")
        for rel, i in mixed:
            seg = []
            for k in ("CRLF", "LF", "CR"):
                if i["at"][k]:
                    seg.append("%s 行 %s" % (k, ",".join(map(str, i["at"][k]))))
            print("  %s → %s" % (rel, "；".join(seg)))

    dist = Counter(i["style"] for _, i in infos)
    total = len(infos)
    parts = ["%s %d 个 (%s)" % (k, dist[k], _pct(dist[k], total))
             for k in STYLE_ORDER if dist.get(k)]
    print()
    print("汇总：" + ("，".join(parts) if parts else "无文件"))

    styled = [i for _, i in infos if i["style"] != "无换行"]
    if styled:
        dom = max(("LF", "CRLF", "CR"),
                  key=lambda k: sum(1 for i in styled if i["style"] == k))
        consistent = sum(1 for i in styled if i["style"] == dom)
        n_mixed = dist.get("混用", 0)
        print("主导风格：%s（并列时按 LF>CRLF>CR 取先者）；"
              "一致率 %s（%d/%d 个有换行文件与主导一致）"
              % (dom, _pct(consistent, len(styled)),
                 consistent, len(styled)))
        if n_mixed:
            print("警告：发现 %d 个混用换行文件，建议统一后提交。" % n_mixed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
