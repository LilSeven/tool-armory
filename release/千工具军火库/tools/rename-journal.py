#!/usr/bin/env python3
"""重命名日志与撤销 (rename-journal) —— 批量重命名并把每批操作写入 JSON 日志, 支持一键回滚最近一批。

用法:
    python rename-journal.py do   <目录> --replace 旧串 新串 [-y] [--journal 日志.json]
    python rename-journal.py undo <目录> [--journal 日志.json]

说明:
    do:   把文件名中出现的旧串替换为新串并重命名; 每个成功操作(原路径->新路径)
          连同 batch_id、时间戳记录为一个批次, 写入 JSON 日志文件
          (默认 <目录>/.rename-journal.json)。默认 dry-run, 加 -y 才执行。
    undo: 从日志中找出属于 <目录> 的最近一批操作, 按相反顺序将新路径改名回
          原路径; 回滚后该批次从日志中移除。缺失的文件会被跳过并报告。

示例:
    python rename-journal.py do ./files --replace draft final -y
    python rename-journal.py undo ./files

退出码: 0 成功; 1 有操作失败; 2 参数/目录/日志错误。
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def load_journal(path: Path):
    if not path.is_file():
        return {"batches": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("batches"), list):
            raise ValueError("日志结构不正确")
        return data
    except (OSError, ValueError) as e:
        print(f"错误: 读取日志失败: {e}", file=sys.stderr)
        sys.exit(2)


def save_journal(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def cmd_do(args) -> int:
    d = Path(args.directory)
    if not d.is_dir():
        print(f"错误: 目录不存在或不是目录: {d}", file=sys.stderr)
        return 2
    old_s, new_s = args.replace
    journal = d / ".rename-journal.json" if not args.journal else Path(args.journal)

    plan = []
    for p in sorted(d.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        if old_s in p.name:
            plan.append((p, p.with_name(p.name.replace(old_s, new_s))))
    plan = [(s, t) for s, t in plan if t.name != s.name]
    if not plan:
        print("没有需要重命名的文件。")
        return 0

    tag = "[dry-run] " if not args.yes else ""
    ops, errors = [], 0
    for src, dst in plan:
        if dst.exists():
            print(f"跳过 {src.name} -> {dst.name} (目标已存在)")
            continue
        if args.yes:
            try:
                src.rename(dst)
                print(f"已重命名 {src.name} -> {dst.name}")
                ops.append({"src": str(src.resolve()), "dst": str(dst.resolve())})
            except OSError as e:
                print(f"失败   {src.name} -> {dst.name}: {e}", file=sys.stderr)
                errors += 1
        else:
            print(f"将重命名 {src.name} -> {dst.name}")

    if args.yes and ops:
        data = load_journal(journal)
        data["batches"].append({
            "batch_id": uuid.uuid4().hex[:8],
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "dir": str(d.resolve()),
            "operations": ops,
        })
        save_journal(journal, data)
        print(f"已记录 {len(ops)} 条操作到日志: {journal} (可用 undo 回滚)")
    else:
        print(f"完成 ({len(plan)} 项)"
              + ("" if args.yes else " [dry-run, 加 -y 执行]"))
    return 1 if errors else 0


def cmd_undo(args) -> int:
    d = Path(args.directory)
    if not d.is_dir():
        print(f"错误: 目录不存在或不是目录: {d}", file=sys.stderr)
        return 2
    journal = d / ".rename-journal.json" if not args.journal else Path(args.journal)
    if not journal.is_file():
        print(f"错误: 日志文件不存在: {journal}", file=sys.stderr)
        return 2

    data = load_journal(journal)
    idx = next((i for i in range(len(data["batches"]) - 1, -1, -1)
                if data["batches"][i].get("dir") == str(d.resolve())), None)
    if idx is None:
        print("错误: 日志中没有属于该目录的批次可回滚。", file=sys.stderr)
        return 2
    batch = data["batches"][idx]
    print(f"回滚批次 {batch['batch_id']} ({batch['time']}, {len(batch['operations'])} 条操作):")

    restored = errors = 0
    for op in reversed(batch["operations"]):
        src, dst = Path(op["src"]), Path(op["dst"])
        if dst.exists():
            try:
                dst.rename(src)
                print(f"已回滚 {dst.name} -> {src.name}")
                restored += 1
            except OSError as e:
                print(f"失败   {dst.name} -> {src.name}: {e}", file=sys.stderr)
                errors += 1
        elif src.exists():
            print(f"跳过 {dst.name} (已是原名 {src.name})")
        else:
            print(f"跳过 {dst.name} (文件不存在)")
        # 无论成败都从批次中移除该条, 避免重复回滚

    data["batches"].pop(idx)
    save_journal(journal, data)
    print(f"回滚完成: 恢复 {restored}, 失败 {errors}; 该批次已从日志移除。")
    return 1 if errors else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="批量重命名 + JSON 日志 + 一键回滚最近一批。")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_do = sub.add_parser("do", help="执行一批重命名并记入日志")
    ap_do.add_argument("directory", help="目标目录")
    ap_do.add_argument("--replace", nargs=2, metavar=("旧串", "新串"),
                       required=True, help="把文件名中的旧串替换为新串")
    ap_do.add_argument("--journal", metavar="FILE", help="日志文件路径(默认 <目录>/.rename-journal.json)")
    ap_do.add_argument("-y", "--yes", action="store_true", help="真正执行(缺省仅预览)")
    ap_do.set_defaults(func=cmd_do)

    ap_undo = sub.add_parser("undo", help="回滚该目录最近一批重命名")
    ap_undo.add_argument("directory", help="目标目录")
    ap_undo.add_argument("--journal", metavar="FILE", help="日志文件路径(默认 <目录>/.rename-journal.json)")
    ap_undo.set_defaults(func=cmd_undo)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
