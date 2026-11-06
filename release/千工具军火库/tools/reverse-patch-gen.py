#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反向补丁生成 (reverse-patch-gen)。

用途:
    把一份 unified diff 的增删对调( '+' <-> '-' ), 同时互换 ---/+++ 文件头
    与 @@ 行号范围, 生成"反向补丁": 对新版本文件前向应用该补丁即可回到
    旧版本 (即得到可回滚的补丁文件)。

示例命令:
    git diff > change.patch
    python reverse-patch-gen.py change.patch -o rollback.patch
    python reverse-patch-gen.py change.patch            # 打印到 stdout
    python diff-apply-simulate.py 新版本文件 rollback.patch   # 预览回滚效果
    python reverse-patch-gen.py --selftest

说明:
    * 输出为纯净 unified diff; ---/+++ 之外的 git 扩展头
      (diff --git / index 等) 不保留。
    * "\\ No newline at end of file" 标记不做特殊处理(简化实现)。

仅用 Python 标准库, 单文件; Windows / Git Bash 可用。
"""

import argparse
import difflib
import re
import sys

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class Hunk:
    __slots__ = ("old_start", "old_count", "new_start", "new_count", "lines")

    def __init__(self, old_start, old_count, new_start, new_count):
        self.old_start = old_start
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


def reverse_files(files):
    """对每个文件段做增删对调, 返回反向补丁文本。"""
    out = []
    for fp in files:
        out.append("--- " + (fp.new_raw.strip() or "unknown"))
        out.append("+++ " + (fp.old_raw.strip() or "unknown"))
        for h in fp.hunks:
            ctx = [t for tag, t, _o, _n in h.lines if tag == " "]
            dels = [t for tag, t, _o, _n in h.lines if tag == "-"]
            adds = [t for tag, t, _o, _n in h.lines if tag == "+"]
            # 反向后: 旧侧 = 原新侧(起点 h.new_start, 行数 = adds+ctx)
            #         新侧 = 原旧侧(起点 h.old_start, 行数 = dels+ctx)
            old_count = len(adds) + len(ctx)
            new_count = len(dels) + len(ctx)
            out.append(f"@@ -{h.new_start},{old_count} "
                       f"+{h.old_start},{new_count} @@")
            for tag, t, _o, _n in h.lines:
                if tag == " ":
                    out.append(" " + t)
                elif tag == "-":
                    out.append("+" + t)
                else:
                    out.append("-" + t)
    return "\n".join(out) + ("\n" if out else "")


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
    # 场景 1: 修改 + 末尾插入 -> 反向后新旧两侧完全互换
    old = ["one", "two", "three", "four", "five", "six"]
    new = ["one", "two", "3.0", "four", "five", "six", "seven"]
    diff_text = "\n".join(difflib.unified_diff(
        old, new, fromfile="a/old.txt", tofile="b/new.txt", lineterm="")) + "\n"
    fps = [f for f in parse_unified_diff(diff_text) if f.hunks]
    assert len(fps) == 1 and len(fps[0].hunks) == 1, "diff 解析异常"
    oh = fps[0].hunks[0]
    rev = reverse_files(fps)
    rfiles = [f for f in parse_unified_diff(rev) if f.hunks]
    assert len(rfiles) == 1, "反向补丁解析异常"
    rf = rfiles[0]
    assert rf.old_path.endswith("new.txt") and rf.new_path.endswith("old.txt"), \
        (rf.old_path, rf.new_path)
    rh = rf.hunks[0]
    orig_new_side = [t for tag, t, _o, _n in oh.lines if tag in " +"]
    rev_old_side = [t for tag, t, _o, _n in rh.lines if tag in " -"]
    assert orig_new_side == rev_old_side, "反向后旧侧 != 原新侧"
    orig_old_side = [t for tag, t, _o, _n in oh.lines if tag in " -"]
    rev_new_side = [t for tag, t, _o, _n in rh.lines if tag in " +"]
    assert orig_old_side == rev_new_side, "反向后新侧 != 原旧侧"
    assert (rh.old_start, rh.new_start) == (oh.new_start, oh.old_start)
    # 场景 2: 纯插入 hunk (@@ -5,0 +6,2 @@) -> 反向为纯删除 (@@ -6,2 +5,0 @@)
    zero = "--- a/f.txt\n+++ b/f.txt\n@@ -5,0 +6,2 @@\n+ins1\n+ins2\n"
    zfps = [f for f in parse_unified_diff(zero) if f.hunks]
    zrev = reverse_files(zfps)
    zrf = [f for f in parse_unified_diff(zrev) if f.hunks][0].hunks[0]
    assert (zrf.old_start, zrf.old_count, zrf.new_start, zrf.new_count) == \
        (6, 2, 5, 0), (zrf.old_start, zrf.old_count, zrf.new_start, zrf.new_count)
    print("selftest PASS: 增删对调、---/+++ 互换、@@ 行号互换(含 0 行数镜像)均正确")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="reverse-patch-gen",
        description="把 unified diff 的增删对调, 生成反向(回滚)补丁")
    ap.add_argument("input", nargs="?", default="-",
                    help="unified diff 文件 (缺省读 stdin)")
    ap.add_argument("-o", "--output", default="",
                    help="输出补丁文件 (缺省打印到 stdout)")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)
    _setup_stdio()
    if args.selftest:
        return selftest()
    try:
        text = _read_text(args.input)
    except OSError as e:
        print(f"错误: 无法读取输入: {e}", file=sys.stderr)
        return 2
    fps = [f for f in parse_unified_diff(text) if f.hunks]
    if not fps:
        print("错误: 输入中没有 hunk", file=sys.stderr)
        return 1
    out = reverse_files(fps)
    nhunks = sum(len(f.hunks) for f in fps)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8", newline="\n") as f:
                f.write(out)
        except OSError as e:
            print(f"错误: 无法写入输出文件: {e}", file=sys.stderr)
            return 2
        dest = args.output
    else:
        sys.stdout.write(out)
        dest = "stdout"
    print(f"已生成反向补丁: 文件 {len(fps)} 个, hunk {nhunks} 个 -> {dest}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
