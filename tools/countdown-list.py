#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""倒计时清单管理 —— 维护一个纪念日/事项清单文件(JSON)，按剩余天数升序显示各事项倒计时。

用法:
    python countdown-list.py add 项目上线 2026-12-31        # 一次性事项
    python countdown-list.py add 生日 1990-03-05 --yearly   # 每年重复(按最近的月日计算)
    python countdown-list.py add 项目上线 2027-05-01 --force  # 同名覆盖
    python countdown-list.py list                           # 按剩余天数排序显示
    python countdown-list.py remove 项目上线                # 删除
    python countdown-list.py --file K:\\cd.json list        # 自定义清单文件(--file 放在子命令前后均可)

清单文件默认为 ~/.countdown_list.json；日期格式 YYYY-MM-DD。
已过期的一次性事项排在最后并标注"已过期"；--yearly 事项永远显示下一次周年。

退出码: 0 成功; 1 未找到/重名/写入失败等操作错误; 2 参数或日期格式错误。
仅用 Python 标准库。
"""

import argparse
import json
import sys
import unicodedata
from datetime import date
from pathlib import Path

DEFAULT_FILE = Path.home() / ".countdown_list.json"


def parse_date(text):
    t = text.strip()
    if t.lower() == "today":
        return date.today()
    return date.fromisoformat(t)


def next_occurrence(d, today):
    """--yearly 事项的下一次发生日期(2月29日按 2月28日 处理)。"""
    def in_year(y):
        try:
            return date(y, d.month, d.day)
        except ValueError:
            return date(y, 2, 28)
    cand = in_year(today.year)
    if cand < today:
        cand = in_year(today.year + 1)
    return cand


def target_date(item, today):
    d = date.fromisoformat(item["date"])
    return next_occurrence(d, today) if item.get("yearly") else d


def load(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("清单文件格式错误: 应为 JSON 数组")
    return data


def save(path, items):
    with path.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
        f.write("\n")


def dw(s):
    """终端显示宽度: 全角/宽字符按 2 计。"""
    return sum(2 if unicodedata.east_asian_width(c) in "FW" else 1 for c in s)


def pad(s, w):
    return s + " " * max(0, w - dw(s))


def remaining_text(days):
    if days == 0:
        return "就是今天!"
    return f"剩 {days} 天" if days > 0 else f"已过期 {-days} 天"


def main(argv=None):
    p = argparse.ArgumentParser(description="纪念日倒计时清单管理")
    p.add_argument("--file", default=None,
                   help=f"清单文件路径 (默认 {DEFAULT_FILE})")
    sub = p.add_subparsers(dest="cmd", required=True)

    def file_opt(sp):
        sp.add_argument("--file", default=argparse.SUPPRESS,
                        help="清单文件路径 (同全局 --file)")

    pa = sub.add_parser("add", help="添加/更新事项")
    pa.add_argument("name", help="事项名称")
    pa.add_argument("date", help="日期 YYYY-MM-DD (yearly 时为首次日期)")
    pa.add_argument("--yearly", action="store_true", help="每年重复的纪念日")
    pa.add_argument("--force", action="store_true", help="同名时覆盖")
    file_opt(pa)

    pl = sub.add_parser("list", help="按剩余天数排序显示")
    file_opt(pl)

    pr = sub.add_parser("remove", help="删除事项")
    pr.add_argument("name")
    file_opt(pr)

    args = p.parse_args(argv)
    path = Path(getattr(args, "file", None) or DEFAULT_FILE)
    try:
        items = load(path)
    except (ValueError, OSError) as e:
        print(f"错误: 读取清单失败: {e}", file=sys.stderr)
        return 2

    if args.cmd == "add":
        try:
            d = parse_date(args.date)
        except ValueError as e:
            print(f"错误: 日期无效 {args.date!r}: {e}", file=sys.stderr)
            return 2
        old_idx = next((i for i, x in enumerate(items)
                        if isinstance(x, dict) and x.get("name") == args.name), None)
        if old_idx is not None and not args.force:
            print(f"错误: 已存在同名事项 {args.name!r}，加 --force 覆盖", file=sys.stderr)
            return 1
        item = {"name": args.name, "date": d.isoformat(), "yearly": args.yearly}
        if old_idx is not None:
            items[old_idx] = item
            action = "已更新"
        else:
            items.append(item)
            action = "已添加"
        try:
            save(path, items)
        except OSError as e:
            print(f"错误: 写入清单失败: {e}", file=sys.stderr)
            return 1
        tgt = target_date(item, date.today())
        days = (tgt - date.today()).days
        tag = " (每年重复)" if args.yearly else ""
        print(f"{action}: {args.name} -> {tgt.isoformat()}{tag} [{remaining_text(days)}]")
        return 0

    if args.cmd == "remove":
        idx = next((i for i, x in enumerate(items)
                    if isinstance(x, dict) and x.get("name") == args.name), None)
        if idx is None:
            idx = next((i for i, x in enumerate(items)
                        if isinstance(x, dict)
                        and str(x.get("name", "")).lower() == args.name.lower()), None)
        if idx is None:
            print(f"错误: 未找到事项 {args.name!r}", file=sys.stderr)
            return 1
        removed = items.pop(idx)
        try:
            save(path, items)
        except OSError as e:
            print(f"错误: 写入清单失败: {e}", file=sys.stderr)
            return 1
        print(f"已删除: {removed.get('name')}")
        return 0

    # list
    today = date.today()
    rows = []
    for item in items:
        if not isinstance(item, dict) or "name" not in item:
            continue
        try:
            tgt = target_date(item, today)
            days = (tgt - today).days
        except (ValueError, TypeError):
            tgt, days = None, None
        rows.append((item, tgt, days))
    future = sorted((r for r in rows if r[2] is not None and r[2] >= 0),
                    key=lambda r: r[2])
    past = sorted((r for r in rows if r[2] is None or r[2] < 0),
                  key=lambda r: r[1] or date.min)
    ordered = future + past
    if not ordered:
        print(f"清单为空: {path}")
        return 0
    name_w = max([dw(str(r[0].get("name", ""))) for r in ordered] + [4])
    print(f"倒计时清单: {path} (共 {len(ordered)} 项, 基准 {today.isoformat()}, "
          f"按剩余天数升序)")
    for i, (item, tgt, days) in enumerate(ordered, 1):
        name = str(item.get("name", ""))
        if tgt is None:
            dtxt, rtxt = str(item.get("date", "?")), "日期无效"
        else:
            dtxt = tgt.isoformat()
            rtxt = remaining_text(days) + (" (每年)" if item.get("yearly") else "")
        print(f"  {i:>2}. {pad(name, name_w)}  {dtxt}  {rtxt}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
