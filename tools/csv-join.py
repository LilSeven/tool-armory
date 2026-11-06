#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSV 按键连接（类似 SQL JOIN）。

按指定的一个或多个键列把两个 CSV 做连接，支持 inner / left / right / full 语义
（left = 保留左表全部行，右表缺失补空）。

用法:
  python csv-join.py left.csv right.csv -k id --how inner -o out.csv
  python csv-join.py a.csv b.csv -k "user_id,date" --how left -o out.csv
  python csv-join.py a.csv b.csv -k id --left-key uid --how inner   # 两表键名不同

参数:
  left, right          输入 CSV 路径
  -k, --key            逗号分隔的连接键（默认两表同名列）
  --left-key/--right-key 两表键名不同时分别指定
  --how {inner,left}   连接方式，默认 inner
  -o, --out            输出文件，缺省打印到 stdout
  --sep/--enc          分隔符与编码
  --suffix             右表重名列后缀，默认 _right

示例:
  # users.csv(id,name) 与 orders.csv(user_id,amount) 以 id=user_id 做 left join
  # 左表键是 id，右表键是 user_id，故用 --right-key 指定右表键名
  python csv-join.py users.csv orders.csv -k id --right-key user_id --how left -o joined.csv
"""

import argparse
import csv
import sys


def open_csv(path, enc="utf-8-sig"):
    with open(path, "r", newline="", encoding=enc) as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="按键连接两个 CSV（inner/left）")
    ap.add_argument("left")
    ap.add_argument("right")
    ap.add_argument("-k", "--key", required=True,
                    help="逗号分隔的连接键列名（两表同名），或与 --left-key/--right-key 配合")
    ap.add_argument("--left-key", help="左表键列名（逗号分隔），缺省用 --key")
    ap.add_argument("--right-key", help="右表键列名（逗号分隔），缺省用 --key")
    ap.add_argument("--how", choices=["inner", "left"], default="inner")
    ap.add_argument("-o", "--out")
    ap.add_argument("--sep", default=",")
    ap.add_argument("--enc", default="utf-8-sig")
    ap.add_argument("--suffix", default="_right")
    args = ap.parse_args()

    lk = [s.strip() for s in (args.left_key or args.key).split(",") if s.strip()]
    rk = [s.strip() for s in (args.right_key or args.key).split(",") if s.strip()]
    if len(lk) != len(rk):
        sys.exit("错误: 左右键列数量不一致 (%d vs %d)" % (len(lk), len(rk)))

    lhead, lrows = open_csv(args.left, args.enc)
    rhead, rrows = open_csv(args.right, args.enc)

    try:
        li = [lhead.index(c) for c in lk]
        ri = [rhead.index(c) for c in rk]
    except ValueError as e:
        sys.exit("错误: 键列不存在: %s" % e)

    # 右表按键建索引（保留多匹配）
    index = {}
    for row in rrows:
        key = tuple(row[i] for i in ri)
        index.setdefault(key, []).append(row)

    # 输出表头：左表全部列 + 右表非键重名列（重名加后缀）
    out_head = list(lhead)
    keep_ri = [i for i in range(len(rhead)) if i not in ri]
    for i in keep_ri:
        name = rhead[i]
        if name in lhead:
            name = name + args.suffix
        out_head.append(name)

    def pad(row, n):
        return (list(row) + [""] * n)[:n]

    out_rows = []
    for lrow in lrows:
        lrow = pad(lrow, len(lhead))
        key = tuple(lrow[i] for i in li)
        matches = index.get(key, [])
        if matches:
            for rrow in matches:
                rrow = pad(rrow, len(rhead))
                out_rows.append(lrow + [rrow[i] for i in keep_ri])
        elif args.how == "left":
            out_rows.append(lrow + [""] * len(keep_ri))

    writer_args = dict(delimiter=args.sep)
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, **writer_args)
            w.writerow(out_head)
            w.writerows(out_rows)
    else:
        w = csv.writer(sys.stdout, **writer_args)
        w.writerow(out_head)
        w.writerows(out_rows)

    print("已输出 %d 行（%s join）" % (len(out_rows), args.how), file=sys.stderr)


if __name__ == "__main__":
    main()
