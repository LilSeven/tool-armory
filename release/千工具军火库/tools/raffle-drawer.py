#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽奖机 —— 从 CSV 名单抽 N 名中奖者，中奖者移出奖池，绝不重复中奖。

用法:
    python raffle-drawer.py names.csv -n 3                 # 抽 3 名幸运奖
    python raffle-drawer.py names.csv -n 1 --prize 一等奖   # 自定义奖项名
    python raffle-drawer.py names.csv -n 3 --header        # CSV 首行是表头时跳过
    python raffle-drawer.py names.csv -n 3 --seed 42       # 固定种子, 复现结果
    python raffle-drawer.py names.csv -n 2 --state winners.json
        # 跨轮模式: 历届中奖者记入 winners.json, 下轮运行自动排除

CSV 格式:
    每行一位参与者, 取第一列作为姓名, 其余列忽略; 空行跳过, 重名只保留一次;
    编码为 UTF-8 (允许带 BOM)。

防重复机制:
    单轮抽奖用不放回抽样, 天然不重复;
    跨轮抽奖把历届中奖者存入 --state 指定的 JSON 文件, 每轮先移出再抽。
"""

import argparse
import csv
import json
import random
import sys


def setup_stdio():
    """统一输入输出编码, 避免中文在管道/重定向时乱码。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def load_names(path, has_header):
    """读 CSV, 返回 (去重后的姓名列表, 丢弃的重复数)。"""
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if has_header and rows:
        rows = rows[1:]
    names, seen, dup = [], set(), 0
    for row in rows:
        if not row:
            continue
        name = (row[0] or "").strip()
        if not name:
            continue
        if name in seen:
            dup += 1
            continue
        seen.add(name)
        names.append(name)
    return names, dup


def load_state(path):
    """读取跨轮状态文件; 不存在则初始化。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"winners": [], "rounds": []}
    except (OSError, ValueError) as e:
        raise SystemExit("[错误] 状态文件 {} 读不了: {}".format(path, e))
    if not isinstance(data, dict):
        raise SystemExit("[错误] 状态文件 {} 内容不是 JSON 对象".format(path))
    if not isinstance(data.get("winners"), list):
        data["winners"] = []
    if not isinstance(data.get("rounds"), list):
        data["rounds"] = []
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="抽奖机: 从 CSV 名单抽 N 名中奖者, 中者移出奖池防重复。")
    parser.add_argument("csv", help="参与者名单 CSV 文件")
    parser.add_argument("-n", "--count", type=int, default=1, help="中奖名额 (默认 1)")
    parser.add_argument("--prize", default="幸运奖", help="奖项名称 (默认 幸运奖)")
    parser.add_argument("--header", action="store_true", help="CSV 第一行是表头, 跳过")
    parser.add_argument("--state", metavar="JSON",
                        help="跨轮状态文件, 记录历届中奖者并自动排除")
    parser.add_argument("--seed", type=int, default=None, help="随机种子, 复现结果用")
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("-n 中奖名额至少为 1")

    try:
        names, dup = load_names(args.csv, args.header)
    except OSError as e:
        raise SystemExit("[错误] 名单读不了: {}".format(e))

    excluded = 0
    state = None
    if args.state:
        state = load_state(args.state)
        before = len(names)
        won = set(state["winners"])
        names = [n for n in names if n not in won]
        excluded = before - len(names)

    if not names:
        raise SystemExit("[错误] 奖池是空的: 名单里没有可用参与者")
    if args.count > len(names):
        raise SystemExit("[错误] 名额 {} 超过奖池人数 {}".format(args.count, len(names)))

    rng = random.Random(args.seed)
    winners = rng.sample(names, args.count)

    bits = ["奖池 {} 人".format(len(names))]
    if excluded:
        bits.append("已移出历届中奖者 {} 人".format(excluded))
    if dup:
        bits.append("去重丢弃 {} 人".format(dup))
    print("、".join(bits) + "。")
    print("恭喜以下 {} 位获得「{}」:".format(len(winners), args.prize))
    for i, name in enumerate(winners, 1):
        print("  {}. {}".format(i, name))
    print("没抽中的朋友别灰心, 奖池已把他们稳稳留下。")

    if state is not None:
        state["winners"].extend(winners)
        state["rounds"].append({"prize": args.prize, "winners": winners})
        try:
            with open(args.state, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except OSError as e:
            raise SystemExit("[错误] 状态文件 {} 写不了: {}".format(args.state, e))
        print("(历届中奖者共 {} 人, 已记入 {})".format(len(state["winners"]), args.state))
    return 0


if __name__ == "__main__":
    setup_stdio()
    sys.exit(main())
