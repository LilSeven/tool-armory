#!/usr/bin/env python3
"""映射表重命名 (csv-map-rename) —— 读取两列 CSV(旧名,新名)对照表, 批量重命名目录下的文件。

CSV 规则:
    每行两列: 旧文件名,新文件名; 忽略纯空行; 首行是表头时加 --header 跳过。
    以下情况整行跳过并在结束时逐条报告原因:
      列数不足 2 / 旧名为空 / 新旧名相同 / 旧文件在目录中不存在 /
      目标名已存在 / 同一批中多个旧名映射到同一个新名。
    默认 dry-run 只打印计划, 加 -y/--yes 才真正执行。

示例:
    python csv-map-rename.py ./files mapping.csv          # 预览
    python csv-map-rename.py ./files mapping.csv -y       # 执行
    python csv-map-rename.py ./files mapping.csv --header -y

退出码: 0 成功(含被跳过的行); 1 有重命名执行失败; 2 参数/文件错误。
"""

import argparse
import csv
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="按两列 CSV(旧名,新名)对照表批量重命名(默认 dry-run, -y 执行)。")
    ap.add_argument("directory", help="目标目录")
    ap.add_argument("csv", help="两列对照表 CSV 文件")
    ap.add_argument("--header", action="store_true",
                    help="CSV 首行为表头, 跳过之")
    ap.add_argument("-y", "--yes", action="store_true",
                    help="真正执行重命名(缺省仅预览)")
    args = ap.parse_args(argv)

    d = Path(args.directory)
    if not d.is_dir():
        print(f"错误: 目录不存在或不是目录: {d}", file=sys.stderr)
        return 2
    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"错误: CSV 文件不存在: {csv_path}", file=sys.stderr)
        return 2

    try:
        with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as f:
            rows = list(csv.reader(f))
    except OSError as e:
        print(f"错误: 读取 CSV 失败: {e}", file=sys.stderr)
        return 2

    if args.header and rows:
        rows = rows[1:]

    plan, skips = [], []
    seen_targets = {}
    for i, row in enumerate(rows, start=1):
        cells = [c.strip() for c in row]
        if not any(cells):
            skips.append((i, "空行")); continue
        if len(cells) < 2 or not cells[0] or not cells[1]:
            skips.append((i, "列数不足或名字为空")); continue
        old, new = cells[0], cells[1]
        if old == new:
            skips.append((i, f"新旧名相同: {old}")); continue
        if not (d / old).is_file():
            skips.append((i, f"旧文件不存在: {old}")); continue
        if (d / new).exists():
            skips.append((i, f"目标已存在: {old} -> {new}")); continue
        if new in seen_targets:
            skips.append((i, f"目标名重复: {old} -> {new} (与第 {seen_targets[new]} 行冲突)"))
            continue
        seen_targets[new] = i
        plan.append((d / old, d / new, old, new, i))

    tag = "[dry-run] " if not args.yes else ""
    done = errors = 0
    for src, dst, old, new, i in plan:
        if args.yes:
            try:
                src.rename(dst)
                print(f"已重命名 第{i}行 {old} -> {new}")
                done += 1
            except OSError as e:
                print(f"失败   第{i}行 {old} -> {new}: {e}", file=sys.stderr)
                errors += 1
        else:
            print(f"将重命名 第{i}行 {old} -> {new}")

    print(f"完成: 成功 {done}, 跳过 {len(skips)}, 失败 {errors} (CSV 共 {len(rows)} 行)"
          + ("" if args.yes else " [dry-run, 加 -y 执行]"))
    for i, reason in skips:
        print(f"  跳过 第{i}行: {reason}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
