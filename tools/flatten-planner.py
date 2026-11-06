#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""flatten-planner.py —— 目录扁平化预演：预演“把深层文件提升到目标层级”会发生哪些名称冲突（仅预演，绝不改动文件）。

思路：扫描目录树，把比 --level 更深的文件“想象中”移动到其相对路径第 level 层的
祖先目录（--level 0 即全部提升到根目录），然后逐个检查目标位置上是否已有同名
条目，或同批待提升文件互相撞名。Windows 文件名不区分大小写，故按不区分大小写
判断冲突。--resolve auto 会给出确定性的建议新名（name_2.ext 形式）。

规则与边界：
  * 比 level 更浅（或正好在该层）的文件保持不动，作为目标位置的既有占位；
  * 若目标目录下已有同名“子目录”，也记为冲突（目录被视为仍存在；若你随后会删除
    腾空后的空目录，此类冲突实际会消失，输出中已注明）；
  * 本工具只读：不移动、不重命名、不删除任何文件。

示例命令：
    python flatten-planner.py D:\\mess                      # 全部提升到根目录，报告冲突
    python flatten-planner.py D:\\mess --level 1            # 保留第一层，更深文件提升到第一层
    python flatten-planner.py D:\\mess --resolve auto       # 为冲突给出建议去重名
    python flatten-planner.py D:\\mess --list               # 额外列出全部计划移动

退出码：0=完成（有冲突也返回 0，冲突只是报告内容）；2=根目录不存在或不是目录。
"""

import argparse
import os
import sys


def human(n):
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    x = float(n)
    i = 0
    while x >= 1024.0 and i < len(units) - 1:
        x /= 1024.0
        i += 1
    return ("%d %s" % (round(x), units[i])) if i == 0 else ("%.2f %s" % (x, units[i]))


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def scan(root):
    """一次遍历目录树，返回 (dirs_info, all_files, errors)。

    dirs_info[rel] = {"depth": 相对深度, "files": {name.casefold(): (name, size)},
                      "subdirs": set(子目录名.casefold())}，rel 为 "." 表示根目录。
    all_files = [(rel_dir, name, size), ...]
    """
    dirs_info = {}
    all_files = []
    errors = []

    def on_error(err):
        errors.append(str(err))

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error, followlinks=False):
        rel = os.path.relpath(dirpath, root)
        info = dirs_info.setdefault(rel, {"depth": 0, "files": {}, "subdirs": set()})
        info["depth"] = 0 if rel == "." else rel.count(os.sep) + 1
        for d in dirnames:
            info["subdirs"].add(d.casefold())
        for name in filenames:
            try:
                size = os.lstat(os.path.join(dirpath, name)).st_size
            except OSError as e:
                errors.append(str(e))
                continue
            info["files"][name.casefold()] = (name, size)
            all_files.append((rel, name, size))
    return dirs_info, all_files, errors


def build_plan(dirs_info, all_files, level, resolve):
    """返回 (stationary, plan, conflicts, deep)。

    plan = [(src_rel, dst_rel, 原名, 结果名), ...]（结果名仅在 auto 下可能不同）
    conflicts[(dst_rel, 名字.casefold())] = 冲突组信息
    """
    stationary = []
    deep = []
    for rel_dir, name, size in all_files:
        depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
        if depth <= level:
            stationary.append((rel_dir, name, size))
        else:
            deep.append((os.path.join(rel_dir, name), rel_dir, name, size))
    deep.sort(key=lambda t: t[0].casefold())

    work = {}       # 目标目录 rel -> {casefold: (name, size)}：既有占位 + 已计划的结果
    preexist = {}   # 目标目录 rel -> set(casefold)：仅原有文件
    for rel, info in dirs_info.items():
        if info["depth"] == level:
            work[rel] = dict(info["files"])
            preexist[rel] = set(info["files"])

    plan = []
    conflicts = {}
    holders = {}

    def dst_rel_of(rel_dir):
        if level == 0:
            return "."
        return os.sep.join(rel_dir.split(os.sep)[:level])

    for src_path, rel_dir, name, size in deep:
        drel = dst_rel_of(rel_dir)
        w = work.setdefault(drel, {})
        pre = preexist.setdefault(drel, set())
        subdirs = dirs_info.get(drel, {}).get("subdirs", set())
        key = name.casefold()
        new_name = name
        conflict = (key in w) or (key in subdirs)
        grp = None
        if conflict:
            grp = conflicts.setdefault((drel, key), {
                "display": w[key][0] if key in pre else name,
                "occupant": w[key][0] if key in pre else None,
                "dir_clash": key in subdirs,
                "holder": holders.get((drel, key)),
                "sources": [],
            })
        if conflict and resolve == "auto":
            stem, ext = os.path.splitext(name)
            k = 2
            while True:
                cand = "%s_%d%s" % (stem, k, ext)
                ck = cand.casefold()
                if ck not in w and ck not in subdirs:
                    new_name = cand
                    break
                k += 1
        w[new_name.casefold()] = (new_name, size)
        if conflict:
            grp["sources"].append((src_path, size, new_name if new_name != name else None))
        else:
            holders[(drel, key)] = src_path
        plan.append((src_path, drel, name, new_name))
    return stationary, plan, conflicts, deep


def fmt_dst(drel):
    return "根目录" if drel == "." else drel


def main():
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        description="目录扁平化预演：预测把深层文件提升到目标层级时的名称冲突（只读，不改动任何文件）。")
    ap.add_argument("root", help="要分析的根目录")
    ap.add_argument("--level", type=int, default=0,
                    help="保留到第几层（0=全部提升到根目录，默认 0）")
    ap.add_argument("--resolve", choices=("report", "auto"), default="report",
                    help="auto=为冲突文件给出建议去重名（name_2.ext 形式）")
    ap.add_argument("--list", dest="show_list", action="store_true",
                    help="额外列出全部计划移动")
    args = ap.parse_args()
    if args.level < 0:
        ap.error("--level 不能为负数")

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("错误：根目录不存在或不是目录：%s" % args.root, file=sys.stderr)
        return 2

    dirs_info, all_files, errors = scan(root)
    stationary, plan, conflicts, deep = build_plan(dirs_info, all_files, args.level, args.resolve)

    mode = "全部提升到根目录" if args.level == 0 else "比第 %d 层深的文件提升到第 %d 层" % (args.level + 1, args.level)
    print("== 扁平化预演（level=%d：%s） ==" % (args.level, mode))
    print("扫描：%d 个文件、%d 个子目录（无法访问 %d）；待提升 %d 个，已在目标层级不动 %d 个，涉及 %d 个目标目录。"
          % (len(all_files), max(0, len(dirs_info) - 1), len(errors),
             len(deep), len(stationary), len({p[1] for p in plan})))
    n_conflict_files = sum(len(g["sources"]) for g in conflicts.values())
    if conflicts:
        print("冲突：%d 组，涉及 %d 个待提升文件。（仅预演，未改动任何文件；可用 --resolve auto 查看建议新名）"
              % (len(conflicts), n_conflict_files))
    else:
        print("冲突：无。（仅预演，未改动任何文件。）")

    if deep:
        if conflicts:
            print()
            print("冲突明细：")
            for (drel, _key), g in sorted(conflicts.items(), key=lambda kv: (kv[0][0], kv[0][1])):
                print("  [%s] 名字 %r：" % (fmt_dst(drel), g["display"]))
                if g["occupant"] is not None:
                    print("    · 目标处已有同名文件 %s，将保持不动" % g["occupant"])
                if g["dir_clash"]:
                    print("    · 目标处已有同名子目录（若随后删除腾空的空目录，此冲突会消失）")
                if g["holder"]:
                    print("    · 同批待提升文件 %s 已先占用此名（将保留原名）" % g["holder"])
                for src, size, new_name in g["sources"]:
                    if new_name:
                        print("    - %s（%s）  建议 → %s" % (src, human(size), new_name))
                    else:
                        print("    - %s（%s）  （冲突未解，可尝试 --resolve auto）" % (src, human(size)))

        if args.show_list:
            print()
            print("计划移动明细（%d 个，仅预演）：" % len(plan))
            width = min(60, max(len(p[0]) for p in plan))
            for src, drel, orig, new in plan:
                dst = new if drel == "." else os.path.join(drel, new)
                mark = "" if new == orig else "  *改名"
                print("  %s  →  %s%s" % (src.ljust(width), dst, mark))
    else:
        print("没有需要提升的文件（所有文件都不深于第 %d 层）。" % args.level)

    if errors:
        print("（警告：%d 个条目无法访问，已跳过）" % len(errors), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
