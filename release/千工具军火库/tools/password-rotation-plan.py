#!/usr/bin/env python3
"""密码轮换计划表 (password-rotation-plan)。

用途:
    为账号清单生成带轮换日期的密码更新计划。每个账号按轮换周期
    (默认 90 天) 或错峰间隔计算下一次改密到期日, 输出占位计划表。
    计划中"new_password"一列永远是 <TO-FILL> 占位符, 本工具不生成、
    不存储、不输出任何明文密码。

账号行格式 (命令行参数或 --in 文件, 每行一个):
    名称[,上次轮换日期YYYY-MM-DD[,负责人]]
    ("#" 开头的行和空行会被忽略, 仅限 --in 文件)

退出码: 0=成功, 2=参数或数据错误。

示例:
    python -I password-rotation-plan.py github:alice gitlab:bob
    python -I password-rotation-plan.py --in accounts.txt --interval-days 90
    python -I password-rotation-plan.py --in accounts.txt --format csv --out plan.csv
    python -I password-rotation-plan.py db:sa,2026-08-01,ops --format json
"""
import argparse
import csv
import io
import json
import sys
import unicodedata
from datetime import date, timedelta

PLACEHOLDER = "<TO-FILL>"


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
               for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def load_accounts(items, infile=None):
    lines = list(items)
    if infile:
        with open(infile, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                lines.append(line)
    accounts = []
    for line in lines:
        parts = [p.strip() for p in line.split(",")]
        if not parts[0]:
            raise ValueError(f"账号行缺少名称: {line!r}")
        last = None
        if len(parts) > 1 and parts[1]:
            last = date.fromisoformat(parts[1])
        owner = parts[2] if len(parts) > 2 and parts[2] else ""
        accounts.append({"account": parts[0], "last_rotated": last, "owner": owner})
    if not accounts:
        raise ValueError("没有可用的账号, 请用位置参数或 --in 提供账号清单")
    return accounts


def build_plan(accounts, interval_days, start, stagger_days):
    plan = []
    for i, acct in enumerate(accounts):
        last = acct["last_rotated"]
        if last is not None:
            due = last + timedelta(days=interval_days)
            days_left = (due - start).days
            if due < start:
                status = "OVERDUE"
            elif due == start:
                status = "DUE"
            else:
                status = "OK"
        else:
            due = start + timedelta(days=i * stagger_days)
            days_left = (due - start).days
            status = "PLANNED"
        plan.append({
            "no": i + 1,
            "account": acct["account"],
            "owner": acct["owner"],
            "last_rotated": last.isoformat() if last else "-",
            "due_date": due.isoformat(),
            "days_left": days_left,
            "status": status,
            "new_password": PLACEHOLDER,
        })
    return plan


def render_table(plan) -> str:
    headers = ["no", "account", "owner", "last_rotated", "due_date",
               "days_left", "status", "new_password"]
    rows = [[str(rec[h]) for h in headers] for rec in plan]
    widths = [_display_width(h) for h in headers]
    for row in rows:
        for j, cell in enumerate(row):
            widths[j] = max(widths[j], _display_width(cell))
    lines = ["  ".join(_pad(h, widths[j]) for j, h in enumerate(headers)),
             "  ".join("-" * w for w in widths)]
    lines.extend("  ".join(_pad(cell, widths[j]) for j, cell in enumerate(row))
                 for row in rows)
    return "\n".join(lines)


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="password-rotation-plan",
        description="为账号清单生成带轮换日期的密码更新占位计划(不含明文密码)。",
    )
    parser.add_argument("accounts", nargs="*",
                        help="账号行: 名称[,上次轮换日期YYYY-MM-DD[,负责人]]")
    parser.add_argument("--in", dest="infile",
                        help="从文件读取账号清单(每行一条, # 为注释)")
    parser.add_argument("--interval-days", type=int, default=90,
                        help="轮换周期天数 (默认 90)")
    parser.add_argument("--start-date", default=date.today().isoformat(),
                        help="计划起始日 YYYY-MM-DD (默认今天)")
    parser.add_argument("--stagger-days", type=int, default=7,
                        help="无历史日期账号的错峰间隔天数 (默认 7)")
    parser.add_argument("--format", choices=("table", "csv", "json"),
                        default="table", help="输出格式 (默认 table)")
    parser.add_argument("--out", help="写入文件而不打印到 stdout")
    args = parser.parse_args(argv)

    try:
        start = date.fromisoformat(args.start_date)
        if args.interval_days < 1:
            raise ValueError("--interval-days 必须 >= 1")
        if args.stagger_days < 0:
            raise ValueError("--stagger-days 必须 >= 0")
        accounts = load_accounts(args.accounts, args.infile)
        plan = build_plan(accounts, args.interval_days, start, args.stagger_days)
    except (ValueError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    if args.format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(plan[0].keys()),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(plan)
        text = buf.getvalue().rstrip("\n")
    elif args.format == "json":
        text = json.dumps(plan, ensure_ascii=False, indent=2)
    else:
        text = render_table(plan)

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
        print(f"已写入 {args.out} ({len(plan)} 条计划)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
