#!/usr/bin/env python3
"""文件名清洗 (sanitize-rename) —— 去除或替换文件名中的空格、非法字符、全角符号与连续横线, 输出安全文件名。

清洗顺序:
    1. NFKC 规范化: 全角字母/数字/符号(如 ＡＢＣ１２３ ？ ！ ．)转为半角;
    2. Windows 非法字符 < > : " / \\ | ? * 及控制字符替换为占位符(默认 _);
    3. 空格按 --space 处理: dash(默认, 替换为 -) / underscore / remove / keep;
    4. 连续横线折叠为单个 '-' (可用 --keep-dashes 关闭);
    5. 去掉首尾的 '.' '-' ' '。
    默认 dry-run 只打印计划, 加 -y/--yes 才真正执行。

示例:
    python sanitize-rename.py ./files                # 预览清洗结果
    python sanitize-rename.py ./files -y             # 执行
    python sanitize-rename.py ./files --space underscore --placeholder '~' -y
    python sanitize-rename.py ./files --keep-dashes -y
"""

import argparse
import sys
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ILLEGAL = set('<>:"/\\|?*')


def sanitize(name: str, space: str = "dash", placeholder: str = "_",
             collapse: bool = True) -> str:
    """把单个文件名清洗为安全文件名。"""
    out = unicodedata.normalize("NFKC", name)
    out = "".join(
        placeholder if (c in ILLEGAL or ord(c) < 32) else c for c in out)
    if space == "dash":
        out = out.replace(" ", "-")
    elif space == "underscore":
        out = out.replace(" ", "_")
    elif space == "remove":
        out = out.replace(" ", "")
    if collapse:
        while "--" in out:
            out = out.replace("--", "-")
    return out.strip(".- ")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="清洗目录下的文件名: 空格/非法字符/全角/连续横线 (默认 dry-run, -y 执行)。")
    ap.add_argument("directory", help="目标目录")
    ap.add_argument("--space", choices=["dash", "underscore", "remove", "keep"],
                    default="dash", help="空格处理方式 (默认 dash)")
    ap.add_argument("--placeholder", default="_",
                    help="非法字符的替换占位符 (默认 _)")
    ap.add_argument("--keep-dashes", action="store_true",
                    help="不折叠连续横线")
    ap.add_argument("--include-hidden", action="store_true",
                    help="包含以点开头的隐藏文件")
    ap.add_argument("-y", "--yes", action="store_true",
                    help="真正执行重命名(缺省仅预览)")
    args = ap.parse_args(argv)

    d = Path(args.directory)
    if not d.is_dir():
        print(f"错误: 目录不存在或不是目录: {d}", file=sys.stderr)
        return 2

    done = skipped = unchanged = errors = 0
    for p in sorted(d.iterdir()):
        if not p.is_file():
            continue
        if not args.include_hidden and p.name.startswith("."):
            continue
        new_name = sanitize(p.name, args.space, args.placeholder,
                            not args.keep_dashes)
        if not new_name or new_name == p.name:
            unchanged += 1
            continue
        target = p.with_name(new_name)
        if target.exists():
            print(f"跳过 {p.name} -> {new_name} (目标已存在)")
            skipped += 1
            continue
        if args.yes:
            try:
                p.rename(target)
                print(f"已清洗 {p.name} -> {new_name}")
                done += 1
            except OSError as e:
                print(f"失败   {p.name} -> {new_name}: {e}", file=sys.stderr)
                errors += 1
        else:
            print(f"将清洗 {p.name} -> {new_name}")

    print(f"完成: 成功 {done}, 跳过 {skipped}, 无需处理 {unchanged}, 失败 {errors}"
          + ("" if args.yes else " [dry-run, 加 -y 执行]"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
