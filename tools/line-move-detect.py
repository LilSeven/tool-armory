#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""移动行识别 (line-move-detect)。

用途:
    读取一份 unified diff, 在"删除行(-)"与"新增行(+)"之间做相似行配对,
    识别被移动而非被重写的代码。
    判定规则:
      * 文本完全一致                        -> exact (相似度 1.00)
      * 去首尾空白后 SequenceMatcher 相似度 >= 阈值 -> similar
      * 删除块与新增块紧邻(原位替换, 即"重写")的配对默认不报告,
        需要 --include-rewrite 才显示。

示例命令:
    git diff | python line-move-detect.py
    python line-move-detect.py change.diff
    python line-move-detect.py change.diff --threshold 0.6 --include-rewrite
    python line-move-detect.py --selftest

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
        self.old_start = old_start      # 1 起; 纯插入/删除时为边界行
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


def _runs(hunk):
    """把 hunk 行体切成连续同标记的 run: [(tag, start, end), ...](end 不含)。"""
    runs = []
    for i, (tag, _t, _o, _n) in enumerate(hunk.lines):
        if runs and runs[-1][0] == tag:
            runs[-1][2] = i + 1
        else:
            runs.append([tag, i, i + 1])
    return [tuple(r) for r in runs]


def detect_moves(fp, threshold, include_rewrite):
    """返回 (moves, del_total, add_total)。

    move 为 dict(old_no, new_no, score, kind, text, in_place)。
    配对按 (相似度降序, 非原位优先, 距离大者优先) 贪心进行, 每行至多配一次。
    """
    moves = []
    cands = []
    del_total = add_total = 0
    for h in fp.hunks:
        dels = [(i, o, t) for i, (tag, t, o, _n) in enumerate(h.lines) if tag == "-"]
        adds = [(i, n, t) for i, (tag, t, _o, n) in enumerate(h.lines) if tag == "+"]
        del_total += len(dels)
        add_total += len(adds)
        if not dels or not adds:
            continue
        runs = _runs(h)
        run_of = {}
        for ridx, (tag, a, b) in enumerate(runs):
            for i in range(a, b):
                run_of[i] = (ridx, tag)

        def in_place(di, ai):
            ridx, tag = run_of[di]
            if tag != "-" or ridx + 1 >= len(runs):
                return False
            t2, a2, b2 = runs[ridx + 1]
            return t2 == "+" and a2 <= ai < b2

        # 组合爆炸保护: 单 hunk 候选对过多时只做精确匹配
        heavy = len(dels) * len(adds) > 250000
        for di, dno, dt in dels:
            for ai, ano, at in adds:
                if dt == at:
                    score, kind = 1.0, "exact"
                elif heavy:
                    continue
                else:
                    score = difflib.SequenceMatcher(
                        None, dt.strip(), at.strip()).ratio()
                    if score < threshold:
                        continue
                    kind = "similar"
                ip = in_place(di, ai)
                cands.append((-score, 1 if ip else 0, -abs(ai - di),
                              dno, ano, score, kind, dt, ip))
    cands.sort()
    used_old, used_new = set(), set()
    for _ns, _ipf, _nd, dno, ano, score, kind, dt, ip in cands:
        if dno in used_old or ano in used_new:
            continue
        if ip and not include_rewrite:
            continue
        used_old.add(dno)
        used_new.add(ano)
        moves.append({"old_no": dno, "new_no": ano, "score": score,
                      "kind": kind, "text": dt, "in_place": ip})
    moves.sort(key=lambda m: m["old_no"])
    return moves, del_total, add_total


def _setup_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _read_text(src):
    if src == "-":
        return sys.stdin.read()
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def selftest():
    old = ["line-a", "line-b", "line-c", "line-d", "line-e", "x = 1", "line-f"]
    new = ["line-a", "line-c", "line-d", "line-e", "line-b", "x = 2", "line-f"]
    diff_text = "\n".join(difflib.unified_diff(
        old, new, fromfile="old.py", tofile="new.py", lineterm="")) + "\n"
    fps = [f for f in parse_unified_diff(diff_text) if f.hunks]
    assert len(fps) == 1 and len(fps[0].hunks) == 1, "diff 解析异常"
    moves, dtotal, atotal = detect_moves(fps[0], 0.75, False)
    assert (dtotal, atotal) == (2, 2), (dtotal, atotal)
    assert len(moves) == 1, moves
    mv = moves[0]
    assert (mv["old_no"], mv["new_no"], mv["kind"], mv["in_place"]) == \
        (2, 5, "exact", False), mv
    moves2, _d, _a = detect_moves(fps[0], 0.75, True)
    assert len(moves2) == 2 and moves2[1]["in_place"], moves2
    print("selftest PASS: 移动行 L2->L5 (exact) 识别成功; "
          "原位改写(x = 1 -> x = 2)默认排除, --include-rewrite 时可见")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="line-move-detect",
        description="识别 unified diff 中被移动(而非重写)的代码行")
    ap.add_argument("input", nargs="?", default="-",
                    help="unified diff 文件路径 (缺省读 stdin)")
    ap.add_argument("-t", "--threshold", type=float, default=0.75,
                    help="相似行判定阈值 0~1 (默认 0.75)")
    ap.add_argument("--include-rewrite", action="store_true",
                    help="同时显示原位替换(重写)配对")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)
    _setup_stdio()
    if args.selftest:
        return selftest()
    if not 0.0 <= args.threshold <= 1.0:
        ap.error("--threshold 必须在 0~1 之间")
    try:
        text = _read_text(args.input)
    except OSError as e:
        print(f"错误: 无法读取输入: {e}", file=sys.stderr)
        return 2
    fps = [f for f in parse_unified_diff(text) if f.hunks]
    if not fps:
        print("输入中没有可分析的 hunk", file=sys.stderr)
        return 1
    tot_moves = 0
    for fp in fps:
        name = fp.old_path or "(未知文件)"
        moves, dtotal, atotal = detect_moves(
            fp, args.threshold, args.include_rewrite)
        print(f"== {name} ==")
        if moves:
            for mv in moves:
                tag = "exact" if mv["kind"] == "exact" else f"{mv['score']:.2f}"
                mark = " (原位改写)" if mv["in_place"] else ""
                print(f"  L{mv['old_no']} -> L{mv['new_no']}  "
                      f"{tag:<6}{mark}  | {mv['text']}")
        else:
            print("  未发现移动行")
        print(f"  统计: 删除 {dtotal} 行 / 新增 {atotal} 行, 配对 {len(moves)} 对")
        tot_moves += len(moves)
    print(f"合计: 文件 {len(fps)} | 移动配对 {tot_moves} | 阈值 {args.threshold}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
