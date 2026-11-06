#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSV 结构校验：按声明规则校验并输出违规行清单。

支持规则：列数/表头、必填非空、类型（int/float/email/date）、正则模式。
规则可写在 JSON 文件中，或直接用命令行选项声明。

用法:
  python csv-validate.py data.csv --rules rules.json
  python csv-validate.py data.csv --cols "id,name,email" --required name,email \
         --type id:int --pattern email:"^[^@\\s]+@[^@\\s]+\\.[a-z]{2,}$"

rules.json 示例:
  {
    "cols": ["id", "name", "email"],   // 期望表头（可选）
    "ncols": 3,                        // 期望列数（可选）
    "required": ["id", "name"],        // 非空必填（可选）
    "types": {"id": "int", "age": "float"},  // 类型（可选）
    "patterns": {"email": "^[^@\\\\s]+@[^@\\\\s]+$"}  // 正则（可选）
  }

退出码: 0=全部通过；1=存在违规；2=文件/规则错误（--no-fail 可只报告不改退出码）。
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"


def load_rules(args):
    rules = {"cols": None, "ncols": None, "required": [], "types": {}, "patterns": {}}
    if args.rules:
        with open(args.rules, "r", encoding="utf-8") as f:
            user = json.load(f)
        for k in rules:
            if k in user:
                rules[k] = user[k]
    if args.cols:
        rules["cols"] = [c.strip() for c in args.cols.split(",") if c.strip()]
    if args.required:
        rules["required"] = [c.strip() for c in args.required.split(",") if c.strip()]
    for item in args.type or []:
        name, _, t = item.partition(":")
        rules["types"][name] = t
    for item in args.pattern or []:
        name, _, p = item.partition(":")
        rules["patterns"][name] = p
    return rules


def check_type(value, t):
    v = value.strip()
    if t == "int":
        int(v)
    elif t == "float":
        float(v)
    elif t == "email":
        if not re.match(EMAIL_RE, v):
            raise ValueError("不是合法邮箱")
    elif t == "date":
        datetime.strptime(v, "%Y-%m-%d")
    else:
        raise ValueError("未知类型 %r" % t)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="CSV 结构校验")
    ap.add_argument("csvfile")
    ap.add_argument("--rules", help="JSON 规则文件")
    ap.add_argument("--cols", help="期望表头（逗号分隔）")
    ap.add_argument("--required", help="必填列（逗号分隔）")
    ap.add_argument("--type", action="append", metavar="COL:TYPE",
                    help="类型规则: int/float/email/date")
    ap.add_argument("--pattern", action="append", metavar="COL:REGEX",
                    help="正则模式规则")
    ap.add_argument("--sep", default=",")
    ap.add_argument("--enc", default="utf-8-sig")
    ap.add_argument("--max-report", type=int, default=50, help="最多报告多少行违规")
    ap.add_argument("--no-fail", action="store_true", help="有违规也退出 0")
    args = ap.parse_args()

    try:
        rules = load_rules(args)
    except (OSError, json.JSONDecodeError) as e:
        print("规则错误: %s" % e, file=sys.stderr)
        sys.exit(2)

    violations = []
    try:
        with open(args.csvfile, "r", newline="", encoding=args.enc) as f:
            reader = csv.reader(f, delimiter=args.sep)
            header = next(reader, None)
            if header is None:
                print("错误: 空文件", file=sys.stderr)
                sys.exit(2)
            data_rows = list(reader)
    except OSError as e:
        print("读取错误: %s" % e, file=sys.stderr)
        sys.exit(2)

    if rules["ncols"] is not None and len(header) != rules["ncols"]:
        violations.append("表头列数 %d != 期望 %d" % (len(header), rules["ncols"]))
    if rules["cols"] is not None and header != rules["cols"]:
        violations.append("表头不一致: 实际 %s != 期望 %s" % (header, rules["cols"]))

    col_idx = {name: i for i, name in enumerate(header)}
    unknown = set()
    for name in list(rules["required"]) + list(rules["types"]) + list(rules["patterns"]):
        if name not in col_idx:
            unknown.add(name)
    if unknown:
        print("错误: 规则引用了不存在的列: %s" % ", ".join(sorted(unknown)), file=sys.stderr)
        sys.exit(2)

    compiled = {c: re.compile(p) for c, p in rules["patterns"].items()}
    ncols = len(header)
    row_no = 1
    for row in data_rows:
        row_no += 1
        if len(row) != ncols:
            violations.append("行%d: 列数 %d != 表头 %d: %r" % (row_no, len(row), ncols, row))
            continue
        for name in rules["required"]:
            if not row[col_idx[name]].strip():
                violations.append("行%d: 必填列 %r 为空" % (row_no, name))
        for name, t in rules["types"].items():
            v = row[col_idx[name]]
            if v.strip():  # 空值交给 required 规则
                try:
                    check_type(v, t)
                except ValueError:
                    violations.append("行%d: 列 %r=%r 不满足类型 %s" % (row_no, name, v, t))
        for name, rx in compiled.items():
            v = row[col_idx[name]]
            if v.strip() and not rx.match(v.strip()):
                violations.append("行%d: 列 %r=%r 不匹配正则 %r" % (row_no, name, v, rx.pattern))

    if violations:
        print("发现 %d 条违规:" % len(violations))
        for v in violations[: args.max_report]:
            print("  " + v)
        if len(violations) > args.max_report:
            print("  ... 其余 %d 条省略" % (len(violations) - args.max_report))
        sys.exit(0 if args.no_fail else 1)
    print("校验通过: %d 行数据，全部符合规则" % (row_no - 1))
    sys.exit(0)


if __name__ == "__main__":
    main()
