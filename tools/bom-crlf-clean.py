#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BOM 与换行符统一 — 删除 UTF-8 BOM，并把 CRLF/LF/CR 换行符统一为指定风格。

功能：
  * 检测并删除 UTF-8 BOM（EF BB BF）；遇到 UTF-16/32 BOM 会提示并按错误处理。
  * 统计文件中的 CRLF / LF / CR 数量，并把全部换行符统一为指定风格
    （--style lf|crlf|cr，默认 auto = 按文件中占多数的风格）。
  * 默认 dry-run 只输出报告，加 --write 才真正写回文件。
  * 不带文件参数时读取 stdin、结果写 stdout（管道模式，直接生效）。

示例命令：
  python bom-crlf-clean.py a.txt                          # 只报告，不修改
  python bom-crlf-clean.py a.txt --style crlf --write     # 统一为 CRLF 并写回
  python bom-crlf-clean.py *.md --style lf --write --keep-bom
  cat a.txt | python bom-crlf-clean.py --style lf > out.txt

退出码：0 全部处理成功（含“发现待清理项”）；2 发生读取/解码/写入错误。
"""

import argparse
import sys

BOM_UTF8 = b"\xef\xbb\xbf"
STYLE_MAP = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}


def detect_bom(data):
    """返回 BOM 名称（无 BOM 返回 None）。"""
    for bom, name in (
        (b"\xff\xfe\x00\x00", "utf-32-le"),
        (b"\x00\x00\xfe\xff", "utf-32-be"),
        (b"\xff\xfe", "utf-16-le"),
        (b"\xfe\xff", "utf-16-be"),
        (BOM_UTF8, "utf-8-sig"),
    ):
        if data.startswith(bom):
            return name
    return None


def count_eols(text):
    """统计 (CRLF, LF, CR) 出现次数（互不重叠计数）。"""
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    return crlf, lf, cr


def pick_auto(crlf, lf, cr):
    """auto 模式：取出现次数最多的换行风格；全为 0 时按 lf。"""
    counts = {"crlf": crlf, "lf": lf, "cr": cr}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else "lf"


def transform(raw, style, keep_bom, encoding):
    """对字节流执行 BOM/换行清理，返回 (新字节, 报告 dict)；失败抛 ValueError。"""
    bom = detect_bom(raw)
    if bom and bom != "utf-8-sig":
        raise ValueError("检测到 %s BOM，本工具仅支持 UTF-8 文本" % bom)
    had_bom = bom == "utf-8-sig"
    body = raw[3:] if had_bom else raw
    try:
        text = body.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ValueError("用 %s 解码失败：%s" % (encoding, exc)) from None
    crlf, lf, cr = count_eols(text)
    target = pick_auto(crlf, lf, cr) if style == "auto" else style
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    nl = STYLE_MAP[target]
    if nl != "\n":
        unified = unified.replace("\n", nl)
    out = unified.encode(encoding)
    if had_bom and keep_bom:
        out = BOM_UTF8 + out
    changes = {"lf": crlf + cr, "crlf": lf + cr, "cr": lf + crlf}[target]
    return out, {
        "had_bom": had_bom,
        "crlf": crlf, "lf": lf, "cr": cr,
        "target": target, "changes": changes,
    }


def _setup_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="删除 UTF-8 BOM 并统一 CRLF/LF/CR 换行符（默认 dry-run）")
    ap.add_argument("files", nargs="*",
                    help="待处理文件；缺省时读 stdin 写 stdout（管道模式）")
    ap.add_argument("--style", choices=["auto", "lf", "crlf", "cr"], default="auto",
                    help="目标换行风格（默认 auto = 文件中占多数的风格）")
    ap.add_argument("--write", action="store_true", help="写回文件（默认只报告）")
    ap.add_argument("--keep-bom", action="store_true",
                    help="保留 UTF-8 BOM（默认删除）")
    ap.add_argument("--encoding", default="utf-8",
                    help="文件文本编码（默认 utf-8）")
    args = ap.parse_args(argv)
    _setup_utf8_stdio()

    if not args.files:
        if sys.stdin.isatty():
            ap.error("没有输入文件，且 stdin 是终端；请传入文件或用管道喂入")
        raw = sys.stdin.buffer.read()
        try:
            out, _rep = transform(raw, args.style, args.keep_bom, args.encoding)
        except ValueError as exc:
            print("stdin: 错误：%s" % exc, file=sys.stderr)
            return 2
        sys.stdout.buffer.write(out)
        return 0

    errors = 0
    for name in args.files:
        try:
            with open(name, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            print("%s: 错误：无法读取（%s）" % (name, exc), file=sys.stderr)
            errors += 1
            continue
        try:
            out, rep = transform(raw, args.style, args.keep_bom, args.encoding)
        except ValueError as exc:
            print("%s: 错误：%s" % (name, exc), file=sys.stderr)
            errors += 1
            continue
        needs_change = rep["changes"] > 0 or (rep["had_bom"] and not args.keep_bom)
        if not needs_change:
            action = "无需修改"
        elif args.write:
            action = "已写入"
        else:
            action = "dry-run（加 --write 生效）"
        plan = []
        if rep["had_bom"] and not args.keep_bom:
            plan.append("删除 UTF-8 BOM")
        if rep["changes"]:
            plan.append("统一 %d 处换行符 → %s" % (rep["changes"], rep["target"].upper()))
        print("%s: BOM=%s  CRLF=%d LF=%d CR=%d  →  %s  [%s]" % (
            name, "有" if rep["had_bom"] else "无",
            rep["crlf"], rep["lf"], rep["cr"],
            "；".join(plan) if plan else "无需修改", action))
        if args.write and needs_change:
            try:
                with open(name, "wb") as fh:
                    fh.write(out)
            except OSError as exc:
                print("%s: 错误：写入失败（%s）" % (name, exc), file=sys.stderr)
                errors += 1
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
