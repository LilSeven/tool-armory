#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文文件名批量清洗（cn-file-rename）

批量重命名目录下的文件：全角字符转半角、压缩多余空格、删除文件系统
不允许的特殊符号（\\ / : * ? " < > |）与控制字符；可选一并删除装饰
符号（★●① 等纯装饰图形，用 --symbols）。默认预览，--apply 实际执行
并生成撤销清单（JSON），--undo <清单> 可整体恢复原文件名。

用法：
    python -I cn-file-rename.py <目录>                # 预览（不改动）
    python -I cn-file-rename.py <目录> --apply        # 执行并写撤销清单
    python -I cn-file-rename.py <目录> --apply --symbols
    python -I cn-file-rename.py <目录> --recursive --apply
    python -I cn-file-rename.py --undo <清单.json>    # 按清单撤销

选项：
    --apply         实际执行重命名（缺省仅预览）
    --symbols       额外删除装饰符号（★●①→ 等）
    --recursive     递归处理子目录（只重命名文件，不动目录名）
    --undo MANIFEST 按撤销清单恢复原文件名
    --self-test     运行内置自测并退出

示例：
    python -I cn-file-rename.py D:/资料            # 先预览
    python -I cn-file-rename.py D:/资料 --apply
    python -I cn-file-rename.py --undo D:/资料/.rename-undo-20261103-120000.json
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

FORBIDDEN = '\\/:*?"<>|'
DECOR_CHARS = set(
    "★☆✦✧♥♦♣♠●○◎◇◆□■▲△▼▽※§¶†‡♀♂♪♫☺☻✓✔✕✗"
    "→←↑↓↔⇒⇔①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
    "㈠㈡㈢㈣㈤㈥㈦㈧㈨㈩㊣"
)
RESERVED = {"CON", "PRN", "AUX", "NUL"}
RESERVED |= {"COM{}".format(i) for i in range(1, 10)}
RESERVED |= {"LPT{}".format(i) for i in range(1, 10)}


def fullwidth_to_halfwidth(s):
    out = []
    for ch in s:
        o = ord(ch)
        if o == 0x3000:
            out.append(" ")
        elif 0xFF01 <= o <= 0xFF5E:
            out.append(chr(o - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def clean_name(name, remove_symbols=False):
    """清洗单个文件名；结果为空串表示无法给出安全新名（应跳过）。"""
    s = "".join(ch for ch in name if ord(ch) >= 32 and ord(ch) != 127)
    s = fullwidth_to_halfwidth(s)
    s = "".join(ch for ch in s if ch not in FORBIDDEN)
    if remove_symbols:
        s = "".join(ch for ch in s if ch not in DECOR_CHARS)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(" .")          # Windows 不允许结尾的空格与点
    if not s or set(s) <= {"."}:
        return ""
    if s.split(".", 1)[0].upper() in RESERVED:
        s = "_" + s
    return s


def plan_renames(root, recursive=False, remove_symbols=False):
    """返回 (moves, unchanged)；moves 为 (旧路径, 新路径) 列表。"""
    moves = []
    unchanged = 0
    planned = set()
    if recursive:
        entries = ((dp, fn) for dp, _dirs, fns in os.walk(root) for fn in fns)
    else:
        entries = ((root, fn) for fn in os.listdir(root)
                   if os.path.isfile(os.path.join(root, fn)))
    for dirpath, fn in entries:
        new = clean_name(fn, remove_symbols)
        if not new or new == fn:
            unchanged += 1
            continue
        old_path = os.path.join(dirpath, fn)
        new_path = os.path.join(dirpath, new)
        if new.lower() != fn.lower():   # 仅大小写变化时可直接重命名
            n = 1
            stem, dot, ext = new.rpartition(".")
            while os.path.exists(new_path) or new_path in planned:
                new_path = os.path.join(
                    dirpath, "{} ({}){}{}".format(stem, n, dot, ext) if dot
                    else "{} ({})".format(new, n))
                n += 1
        planned.add(new_path)
        moves.append((old_path, new_path))
    return moves, unchanged


def apply_plan(root, moves):
    """执行重命名，返回 (完成列表, 撤销清单路径)。"""
    done = []
    for old_path, new_path in moves:
        try:
            os.rename(old_path, new_path)
        except OSError as e:
            print("[跳过] {} -> {}: {}".format(old_path, new_path, e), file=sys.stderr)
            continue
        done.append((old_path, new_path))
    manifest_path = None
    if done:
        ts = datetime.now()
        manifest_path = os.path.join(
            root, ".rename-undo-{:%Y%m%d-%H%M%S}.json".format(ts))
        data = {
            "tool": "cn-file-rename",
            "created": ts.isoformat(timespec="seconds"),
            "root": root,
            "moves": [{"from": os.path.relpath(o, root),
                       "to": os.path.relpath(n, root)} for o, n in done],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return done, manifest_path


def undo_manifest(manifest_path):
    """按清单逆序恢复；返回 (恢复数, 跳过数)。"""
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    root = data.get("root") or os.path.dirname(os.path.abspath(manifest_path))
    restored = skipped = 0
    for mv in reversed(data.get("moves", [])):
        to_abs = os.path.join(root, mv["to"])
        from_abs = os.path.join(root, mv["from"])
        if os.path.exists(to_abs) and not os.path.exists(from_abs):
            os.rename(to_abs, from_abs)
            restored += 1
        else:
            skipped += 1
            print("[跳过] 原名已占用或新名不存在: {}".format(to_abs), file=sys.stderr)
    return restored, skipped


def self_test():
    tmp = tempfile.mkdtemp(prefix="cnfr_selftest_")
    try:
        # 单元断言
        assert clean_name("ＡＢＣ　１２３  双空格.txt") == "ABC 123 双空格.txt"
        assert clean_name("报告？？草稿Ｖ２：final.docx") == "报告草稿V2final.docx"
        assert clean_name("decor★版①.txt", remove_symbols=True) == "decor版.txt"
        assert clean_name("decor★版①.txt") == "decor★版①.txt"   # 不加 --symbols 保留
        assert clean_name("正常.txt") == "正常.txt"
        assert clean_name("CON.txt") == "_CON.txt"
        # 集成：预览 → 执行 → 撤销
        names = ["ＡＢＣ　１２３  双空格.txt", "报告？？草稿Ｖ２：final.docx",
                 "decor★版①.txt", "正常.txt"]
        for n in names:
            open(os.path.join(tmp, n), "w", encoding="utf-8").close()
        moves, unchanged = plan_renames(tmp)
        assert len(moves) == 2 and unchanged == 2, (moves, unchanged)
        done, manifest = apply_plan(tmp, moves)
        assert len(done) == 2 and manifest and os.path.exists(manifest)
        listing = set(os.listdir(tmp))
        assert "ABC 123 双空格.txt" in listing
        assert "报告草稿V2final.docx" in listing
        assert "正常.txt" in listing and "decor★版①.txt" in listing
        restored, skipped = undo_manifest(manifest)
        assert (restored, skipped) == (2, 0)
        assert set(names) <= set(os.listdir(tmp))
        print("cn-file-rename 自测通过：清洗规则/预览/执行/撤销清单 各环节 OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="中文文件名批量清洗：全角转半角、去多余空格与特殊符号")
    parser.add_argument("directory", nargs="?", help="目标目录")
    parser.add_argument("--apply", action="store_true", help="实际执行重命名（缺省仅预览）")
    parser.add_argument("--symbols", action="store_true", help="额外删除装饰符号")
    parser.add_argument("--recursive", action="store_true", help="递归处理子目录")
    parser.add_argument("--undo", metavar="MANIFEST", help="按撤销清单恢复原文件名")
    parser.add_argument("--self-test", action="store_true", help="运行内置自测后退出")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.undo:
        try:
            restored, skipped = undo_manifest(args.undo)
        except (OSError, ValueError, KeyError) as e:
            print("撤销失败: {}".format(e), file=sys.stderr)
            return 1
        print("撤销完成：恢复 {} 个，跳过 {} 个".format(restored, skipped))
        return 0

    if not args.directory or not os.path.isdir(args.directory):
        parser.error("请提供有效的目标目录")
        return 2

    moves, unchanged = plan_renames(args.directory, args.recursive, args.symbols)
    if not moves:
        print("无需改名：{} 个文件已符合规则".format(unchanged))
        return 0
    for old_path, new_path in moves:
        print("{}  ->  {}".format(os.path.relpath(old_path, args.directory),
                                  os.path.relpath(new_path, args.directory)))
    print("共 {} 个待改名，{} 个无需改动".format(len(moves), unchanged))
    if not args.apply:
        print("（预览模式，未做任何改动；加 --apply 执行）")
        return 0
    done, manifest = apply_plan(args.directory, moves)
    print("已重命名 {} 个".format(len(done)))
    if manifest:
        print("撤销清单: {}".format(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
