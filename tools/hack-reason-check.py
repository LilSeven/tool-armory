#!/usr/bin/env python3
"""HACK 说明检查（hack-reason-check）——扫描 HACK/WORKAROUND 标记并检查其后是否附带原因说明。

逐行查找 HACK / WORKAROUND 标记（整词、区分大小写），并检查标记之后是否写明原因：
  * 同一行标记后的文字"词数"（英文按空格分词，中文按字计）达到 --min-words（默认 4）→ OK；
  * 同一行没写或写得太少时，向后看最多两行，若是注释行且不含新的 HACK/WORKAROUND
    标记，则视为说明文字继续判断 → OK（下一行说明）或 WEAK；
  * 什么都没有 → MISSING。
默认退出码恒为 0；加 --strict 时存在 WEAK/MISSING 则返回 1。仅依赖 Python 标准库。

用法:
    python hack-reason-check.py [路径...] [--min-words N] [--strict]

示例:
    python hack-reason-check.py src/ --min-words 4 --strict

自测（构造临时示例文件）:
    python -I hack-reason-check.py --self-test
"""

from __future__ import annotations

import argparse
import os
import re
import sys

MARKER_RE = re.compile(r"\b(HACK|WORKAROUND)\b")
COMMENT_PREFIXES = ("#", "//", "--", "*", ";", "%")
LEAD_NOISE_RE = re.compile(r"^[\s:：\-—=+>»]*")
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

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


def reason_words(text):
    """估算说明文字的词数：英文/数字按 token 计，中文按字计。"""
    text = LEAD_NOISE_RE.sub("", text)
    return len(TOKEN_RE.findall(text)) + len(CJK_RE.findall(text))


def check(paths, min_words=4):
    """返回 [{"path","line","status","via","text","words"}, ...]。"""
    findings = []
    for path in iter_files(paths):
        lines = read_lines(path)
        if lines is None:
            continue
        for i, text in enumerate(lines):
            m = MARKER_RE.search(text)
            if not m:
                continue
            n = reason_words(text[m.end():])
            via = "同行"
            if n == 0:
                cont = None
                for j in (i + 1, i + 2):
                    if j >= len(lines):
                        break
                    nxt = lines[j].strip()
                    if not nxt:
                        continue
                    if nxt.startswith(COMMENT_PREFIXES) and not MARKER_RE.search(nxt):
                        cont = nxt
                    break
                if cont is not None:
                    n = reason_words(cont)
                    via = "下一行"
            if n >= min_words:
                status = "OK"
            elif n > 0:
                status = "WEAK"
            else:
                status = "MISSING"
            findings.append({"path": path, "line": i + 1, "status": status,
                             "via": via, "text": text.strip(), "words": n})
    return findings


def render(findings, strict=False):
    order = {"MISSING": 0, "WEAK": 1, "OK": 2}
    findings.sort(key=lambda f: (order[f["status"]], f["path"], f["line"]))
    for f in findings:
        print("%-9s %s:%d  (%s %d 词)  %s"
              % ("[%s]" % f["status"], f["path"], f["line"],
                 f["via"], f["words"], f["text"][:100]))
    counts = {}
    for f in findings:
        counts[f["status"]] = counts.get(f["status"], 0) + 1
    print("---")
    print("共 %d 处 HACK/WORKAROUND: OK %d, WEAK %d, MISSING %d"
          % (len(findings), counts.get("OK", 0),
             counts.get("WEAK", 0), counts.get("MISSING", 0)))
    if strict and (counts.get("WEAK", 0) + counts.get("MISSING", 0)) > 0:
        return 1
    return 0


def self_test():
    """构造临时示例文件，断言四种情形（同行 OK / 下一行 OK / MISSING / WEAK）判定正确。"""
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="hack-check-")
    try:
        src = ("# HACK: 临时绕过上游库的编码 bug，等下个版本修复\n"
               "def f():\n"
               "    pass\n"
               "\n"
               "# HACK\n"
               "# because the upstream lib mis-encodes utf-8 payloads\n"
               "def g():\n"
               "    pass\n"
               "\n"
               "# HACK\n"
               "do_something()\n"
               "\n"
               "# WORKAROUND: 绕过\n"
               "value = 1\n")
        path = os.path.join(tmp, "demo.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        findings = check([tmp], min_words=4)
        assert len(findings) == 4, "应发现 4 处标记, 实际 %d" % len(findings)
        got = {(f["line"], f["status"]) for f in findings}
        want = {(1, "OK"), (5, "OK"), (10, "MISSING"), (13, "WEAK")}
        assert got == want, "状态判定不符: %s" % sorted(got)
        render(findings)
        print("说明检查断言全部通过（同行/下一行/缺失/过弱 四种情形均正确）")
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
        description="HACK 说明检查：检查 HACK/WORKAROUND 标记后是否附带原因说明")
    parser.add_argument("paths", nargs="*", default=["."],
                        help="要扫描的文件或目录（默认当前目录）")
    parser.add_argument("--min-words", type=int, default=4, metavar="N",
                        help="说明文字最少词数（默认 4；中文按字计）")
    parser.add_argument("--strict", action="store_true",
                        help="存在 WEAK/MISSING 时退出码为 1")
    args = parser.parse_args(argv)
    findings = check(args.paths, min_words=args.min_words)
    return render(findings, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
