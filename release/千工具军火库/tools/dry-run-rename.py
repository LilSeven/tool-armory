"""重命名规则预演器 (dry-run-rename)

用途：输入任意重命名规则（「旧名|新名」对），输出旧名到新名的对照表，
并检查各类冲突（目标重名、目标已存在、源缺失），只预演不实际执行。

用法:
    python dry-run-rename.py RULES_FILE [--root DIR]
    cat rules.txt | python dry-run-rename.py -

示例:
    python dry-run-rename.py rules.txt --root ./files
    echo "old.txt|new.txt" | python dry-run-rename.py -

规则文件格式（每行一条，# 开头为注释）:
    旧名|新名
    旧名 -> 新名
    旧名<TAB>新名

冲突类型:
    [源缺失]     旧名在 --root 下不存在，也不会由更早的规则产生
    [目标重复]   两条规则映射到同一个新名
    [目标已存在] 新名已被磁盘文件或更早规则的产物占用且无人移走
退出码: 0 = 无冲突；1 = 存在冲突（表仍会输出）。
"""

import argparse
import sys
from pathlib import Path


def parse_rules(text: str):
    rules = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for sep in ("|", "->", "\t"):
            if sep in line:
                old, new = (x.strip() for x in line.split(sep, 1))
                if old and new:
                    rules.append((lineno, old, new))
                    break
        else:
            print(f"[警告] 第 {lineno} 行无法解析: {line}", file=sys.stderr)
    return rules


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="重命名规则预演：输出对照表并检查冲突，不执行")
    ap.add_argument("rules", help="规则文件路径，或 - 表示从 stdin 读")
    ap.add_argument("--root", default=".", help="规则所相对的目录（默认当前目录）")
    ns = ap.parse_args(argv)

    if ns.rules == "-":
        text = sys.stdin.read()
    else:
        rf = Path(ns.rules)
        if not rf.is_file():
            print(f"错误: 规则文件 {rf} 不存在", file=sys.stderr)
            return 2
        text = rf.read_text(encoding="utf-8")

    rules = parse_rules(text)
    if not rules:
        print("没有可用的重命名规则", file=sys.stderr)
        return 2

    root = Path(ns.root)
    # 目标重复的静态检查
    targets = {}
    conflicts = []
    for lineno, old, new in rules:
        if new in targets:
            conflicts.append(f"[目标重复] {new}: 由 {targets[new]} 和 {old} 同时映射（第 {lineno} 行）")
        else:
            targets[new] = old

    # 顺序模拟：exists 为「执行到当前行时」根目录中的文件名集合
    exists = {p.name for p in root.iterdir()} if root.is_dir() else set()
    print(f"{'旧名':<30} -> 新名")
    print("-" * 62)
    n_bad = 0
    for lineno, old, new in rules:
        status = ""
        if old not in exists:
            status = "  [源缺失]"
            conflicts.append(f"[源缺失] {old}（第 {lineno} 行）")
        elif new != old and new in exists:
            status = "  [目标已存在]"
            conflicts.append(f"[目标已存在] {new}（第 {lineno} 行）")
        else:
            exists.discard(old)
            exists.add(new)
        if status:
            n_bad += 1
        print(f"{old:<30} -> {new}{status}")
    print("-" * 62)
    print(f"共 {len(rules)} 条规则，{n_bad} 条有问题，{len(conflicts)} 个冲突")

    if conflicts:
        print("\n冲突明细:")
        for c in conflicts:
            print(" " + c)
        return 1
    print("无冲突，可安全执行（本工具不执行实际重命名）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
