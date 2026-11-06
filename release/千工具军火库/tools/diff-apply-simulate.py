#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补丁模拟应用 (diff-apply-simulate)。

用途:
    在内存中把一份 unified diff 应用到目标文件, 只在 stdout 输出应用后
    的文件内容预览, 不写任何文件(纯 dry-run)。hunk 按上下文精确匹配,
    行号有漂移时在 ±N 行范围内搜索回正; 匹配不到则跳过该 hunk 并报告。

示例命令:
    python diff-apply-simulate.py target.txt fix.patch
    git diff | python diff-apply-simulate.py target.txt
    python diff-apply-simulate.py target.txt fix.patch --max-offset 20
退出码: 0=全部 hunk 应用成功; 1=存在失败 hunk(预览仍输出); 2=用法错误。
(应用报告输出到 stderr, stdout 保持纯净便于重定向)

仅用 Python 标准库, 单文件; Windows / Git Bash 可用。
"""

import argparse
import difflib
import os
import re
import sys

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class Hunk:
    __slots__ = ("old_start", "old_count", "new_start", "new_count", "lines")

    def __init__(self, old_start, old_count, new_start, new_count):
        self.old_start = old_start      # 1 起; 纯插入时为插入点前一行
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.lines = []                 # (tag, text, old_no, new_no), tag in " -+"


class FilePatch:
    __slots__ = ("old_raw", "new_raw", "old_path", "new_path", "hunks")

    def __init__(self):
        self.old_raw = ""
        self.new_raw = ""
        self.old_path = ""
        self.new_path = ""
        self.hunks = []


def parse_unified_diff(text):
    """把 unified diff 文本解析为 FilePatch 列表(宽松容错, 忽略扩展头)。"""
    files = []
    cur = None
    hunk = None
    old_rem = new_rem = 0
    old_no = new_no = 0
    for raw in text.splitlines():
        line = raw[:-1] if raw.endswith("\r") else raw
        if hunk is not None and old_rem <= 0 and new_rem <= 0:
            hunk = None
        if hunk is not None:
            if line.startswith("\\"):          # "\ No newline at end of file"
                continue
            tag = line[0] if line else " "
            body = line[1:] if line else ""
            if tag not in " -+":
                tag, body = " ", line          # 异常行按上下文兜底
            if tag == " ":
                old_no += 1
                new_no += 1
                old_rem -= 1
                new_rem -= 1
            elif tag == "-":
                old_no += 1
                old_rem -= 1
            else:
                new_no += 1
                new_rem -= 1
            hunk.lines.append((tag, body, old_no, new_no))
            continue
        m = HUNK_RE.match(line)
        if m:
            o, oc, n, nc = m.groups()
            hunk = Hunk(int(o), int(oc) if oc else 1,
                        int(n), int(nc) if nc else 1)
            if cur is None:
                cur = FilePatch()
                files.append(cur)
            cur.hunks.append(hunk)
            old_no = hunk.old_start - 1
            new_no = hunk.new_start - 1
            old_rem, new_rem = hunk.old_count, hunk.new_count
            continue
        if line.startswith("--- "):
            cur = FilePatch()
            cur.old_raw = line[4:]
            cur.old_path = cur.old_raw.split("\t")[0].strip()
            files.append(cur)
            continue
        if line.startswith("+++ ") and cur is not None and not cur.new_raw:
            cur.new_raw = line[4:]
            cur.new_path = cur.new_raw.split("\t")[0].strip()
            continue
        # diff --git / index / 空行等扩展头: 忽略
    return files


def simulate(target_lines, fp, max_offset):
    """在内存中应用一个文件段的 hunks。

    返回 (out_lines, report, ok_count, total)。
    report 为 [(hunk序号, 成功消息|None, 失败消息|None), ...]。
    """
    out = []
    report = []
    pos = 0
    ok = 0
    total = len(fp.hunks)
    for idx, h in enumerate(fp.hunks, 1):
        old_body = [t for tag, t, _o, _n in h.lines if tag in " -"]
        new_body = [t for tag, t, _o, _n in h.lines if tag in " +"]
        if h.old_count == 0 and not old_body:
            # 纯插入: 在第 old_start 行之后插入 (0 基下标 = old_start)
            at = min(max(h.old_start, pos), len(target_lines))
            out.extend(target_lines[pos:at])
            out.extend(new_body)
            pos = at
            ok += 1
            report.append((idx, f"插入于第 {at} 行之后", None))
            continue
        want = h.old_start - 1
        n, m = len(target_lines), len(old_body)
        hi = n - m
        found = None
        for k in range(max_offset + 1):
            cands = (want,) if k == 0 else (want + k, want - k)
            for c in cands:
                if pos <= c <= hi and target_lines[c:c + m] == old_body:
                    found = c
                    break
            if found is not None:
                break
        if found is None:
            report.append((idx, None,
                           f"失败: 在 ±{max_offset} 行内未匹配到上下文, 已跳过"))
            continue
        out.extend(target_lines[pos:found])
        out.extend(new_body)
        pos = found + m
        ok += 1
        off = found - want
        report.append((idx,
                       f"应用成功: 目标第 {found + 1} 行" +
                       (f" (偏移 {off:+d})" if off else ""),
                       None))
    out.extend(target_lines[pos:])
    return out, report, ok, total


def _setup_stdio():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _read_text(src):
    if src == "-":
        return sys.stdin.read()
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def selftest():
    # 场景 A: 两个 hunk 精确应用
    target_lines = [f"line-{i:02d}" for i in range(1, 21)]
    new_lines = list(target_lines)
    new_lines[2] = "line-XX"                        # 改第 3 行
    new_lines[15:15] = ["INSERTED-A", "INSERTED-B"]  # 第 15 行后插入
    patch_text = "\n".join(difflib.unified_diff(
        target_lines, new_lines, fromfile="t.txt", tofile="t.txt",
        lineterm="")) + "\n"
    fps = [f for f in parse_unified_diff(patch_text) if f.hunks]
    assert len(fps) == 1 and len(fps[0].hunks) == 2, "diff 解析异常"
    out, report, ok, total = simulate(target_lines, fps[0], 100)
    assert (ok, total) == (2, 2), report
    assert out == new_lines, out

    # 场景 B: 把第 2 个 hunk 的旧行号 +5, 靠上下文搜索回正(偏移 -5)
    lines = patch_text.splitlines()
    seen = 0
    for i, ln in enumerate(lines):
        if ln.startswith("@@ "):
            seen += 1
            if seen == 2:
                m = HUNK_RE.match(ln)
                lines[i] = ln.replace("-" + m.group(1) + ",",
                                      "-" + str(int(m.group(1)) + 5) + ",", 1)
                break
    sfps = [f for f in parse_unified_diff("\n".join(lines) + "\n") if f.hunks]
    out, report, ok, total = simulate(target_lines, sfps[0], 100)
    assert (ok, total) == (2, 2), report
    assert out == new_lines, out
    assert "偏移 -5" in report[1][1], report

    # 场景 C: 上下文不存在 -> hunk 失败, 目标内容保持不变
    bad = ("--- t.txt\n+++ t.txt\n@@ -3,3 +3,3 @@\n"
           " no-such-context\n-line-03\n+line-YY\n line-04\n")
    bfp = [f for f in parse_unified_diff(bad) if f.hunks][0]
    out, report, ok, total = simulate(target_lines, bfp, 100)
    assert ok == 0 and total == 1, report
    assert out == target_lines, out
    assert "失败" in report[0][2], report

    # 场景 D: 纯插入 hunk (@@ -5,0 +6,2 @@)
    ins = "--- t.txt\n+++ t.txt\n@@ -5,0 +6,2 @@\n+INSERTED-A\n+INSERTED-B\n"
    ifp = [f for f in parse_unified_diff(ins) if f.hunks][0]
    out, report, ok, total = simulate(target_lines, ifp, 100)
    assert ok == 1, report
    assert out == target_lines[:5] + ["INSERTED-A", "INSERTED-B"] + target_lines[5:], out

    print("selftest PASS: 精确应用 / 行号偏移回正(偏移-5) / 失败保持原文 / "
          "纯插入 hunk 全部符合预期")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="diff-apply-simulate",
        description="在内存中模拟 patch 应用, 只输出结果预览不落盘")
    ap.add_argument("target", nargs="?", default="",
                    help="目标文件路径 ('-' 表示 stdin)")
    ap.add_argument("patch", nargs="?", default="",
                    help="unified diff 补丁文件 (缺省读 stdin)")
    ap.add_argument("--section", type=int, default=1,
                    help="补丁中的第几个文件段 (1 起, 默认 1)")
    ap.add_argument("--max-offset", type=int, default=100,
                    help="hunk 上下文搜索的行号漂移范围 (默认 100)")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)
    _setup_stdio()
    if args.selftest:
        return selftest()
    if not args.target:
        ap.error("需要提供目标文件路径 (或用 --selftest 运行自测)")
    if args.target == "-" and args.patch in ("", "-"):
        print("错误: target 与 patch 不能同时来自 stdin", file=sys.stderr)
        return 2
    try:
        target_text = _read_text(args.target)
        patch_text = _read_text(args.patch) if args.patch else sys.stdin.read()
    except OSError as e:
        print(f"错误: 无法读取文件: {e}", file=sys.stderr)
        return 2
    fps = [f for f in parse_unified_diff(patch_text) if f.hunks]
    if not fps:
        print("错误: 补丁中没有 hunk", file=sys.stderr)
        return 2
    if not 1 <= args.section <= len(fps):
        print(f"错误: --section 超出范围 (补丁共 {len(fps)} 个文件段)",
              file=sys.stderr)
        return 2
    fp = fps[args.section - 1]
    base = os.path.basename(fp.old_path.split("\t")[0])
    if base and base not in ("/dev/null",) and \
            base != os.path.basename(args.target):
        print(f"提示: 补丁针对 {fp.old_path}, 与目标 {args.target} 不同, "
              "仍按上下文尝试", file=sys.stderr)
    target_lines = target_text.splitlines()
    out, report, ok, total = simulate(target_lines, fp, args.max_offset)
    for idx, okmsg, errmsg in report:
        print(f"hunk #{idx}: {okmsg if okmsg else errmsg}", file=sys.stderr)
    print(f"模拟完成: {ok}/{total} hunk 成功 | 纯内存预览, 未写任何文件",
          file=sys.stderr)
    tail = "" if (target_text and not target_text.endswith("\n")) else "\n"
    sys.stdout.write("\n".join(out) + (tail if out else ""))
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
