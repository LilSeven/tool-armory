#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""随机分队 —— 把名单平均分成 N 组打印分组表, 支持指定队长。

用途:
    名单来自位置参数或文件(每行一个, # 开头为注释), 洗牌后轮流分配到 N 组,
    各组人数相差不超过 1。--captains 可指定每队队长(先一人一队放队长,
    再分队员); --pick-captains 则在分组完成后每组随机选一名队长。

示例:
    python team-splitter.py -g 2 张三 李四 王五 赵六 周五
    python team-splitter.py -g 3 -f names.txt
    python team-splitter.py -g 2 -f names.txt --captains 张三,李四
    python team-splitter.py -g 3 -f names.txt --pick-captains
    python team-splitter.py -g 2 -f names.txt --seed 42     # 固定种子, 便于复现

退出码: 0 成功; 1 名单/队长问题; 2 参数错误。
"""

import argparse
import random
import re
import sys


def _setup_stdio():
    """Windows 下把标准输出/错误切到 UTF-8, 避免中文在管道/重定向中乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def positive_int(value):
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("须为整数: {!r}".format(value))
    if n < 1:
        raise argparse.ArgumentTypeError("须为正整数")
    return n


def read_names(path):
    """读名单文件: 每行一个名字, 跳过空行与 # 注释, 去重保序。"""
    names, seen = [], set()
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        for raw in fh:
            name = raw.strip()
            if not name or name.startswith("#"):
                continue
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def dedupe(names):
    out, seen = [], set()
    for name in names:
        cleaned = name.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="team-splitter",
        description="把名单平均分成 N 组打印分组表, 支持指定队长。")
    parser.add_argument("names", nargs="*", help="名单(与 -f 二选一)")
    parser.add_argument("-g", "--groups", type=positive_int, default=2,
                        metavar="N", help="组数 (默认 2)")
    parser.add_argument("-f", "--file",
                        help="名单文件, 每行一个名字, # 开头为注释")
    parser.add_argument("--captains", metavar="A,B,...",
                        help="指定队长(逗号/顿号分隔), 先一人一队放队长再分队员")
    parser.add_argument("--pick-captains", action="store_true",
                        help="分组完成后每组随机选一名队长")
    parser.add_argument("--seed", type=int, help="随机种子(便于复现)")
    args = parser.parse_args(argv)

    if args.captains and args.pick_captains:
        parser.error("--captains 与 --pick-captains 不能同时使用")
    if args.file and args.names:
        parser.error("不能同时使用 -f/--file 与位置参数名单, 二选一")

    if args.file:
        try:
            members = read_names(args.file)
        except OSError as exc:
            print("错误: 无法读取名单文件: {}".format(exc), file=sys.stderr)
            return 2
    elif args.names:
        members = dedupe(args.names)
    else:
        parser.error("请提供名单: 位置参数或 -f/--file 名单文件")

    if len(members) < args.groups:
        print("提示: 人数({})少于组数({}), 部分组将为空".format(
            len(members), args.groups), file=sys.stderr)

    rng = random.Random(args.seed)
    captain_map = {}
    teams = [[] for _ in range(args.groups)]

    if args.captains:
        wanted = dedupe(re.split(r"[,，、\s]+", args.captains))
        unknown = [c for c in wanted if c not in set(members)]
        if unknown:
            print("错误: 指定的队长不在名单中: {}".format("、".join(unknown)),
                  file=sys.stderr)
            return 1
        if len(wanted) > args.groups:
            print("错误: 队长人数({})超过组数({})".format(
                len(wanted), args.groups), file=sys.stderr)
            return 1
        caps = list(wanted)
        rng.shuffle(caps)
        cap_set = set(wanted)
        rest = [m for m in members if m not in cap_set]
        rng.shuffle(rest)
        for i, cap in enumerate(caps):
            teams[i].append(cap)
            captain_map[i] = cap
        for i, name in enumerate(rest):
            teams[i % args.groups].append(name)
    else:
        pool = list(members)
        rng.shuffle(pool)
        for i, name in enumerate(pool):
            teams[i % args.groups].append(name)
        if args.pick_captains:
            for idx, team in enumerate(teams):
                if team:
                    captain_map[idx] = rng.choice(team)

    print("分队结果: {} 人 → {} 组".format(len(members), args.groups))
    for i, team in enumerate(teams, 1):
        cap = captain_map.get(i - 1)
        shown = list(team)
        if cap is not None and cap in shown:
            shown.remove(cap)
            shown.insert(0, cap)
        label = "第 {} 组".format(i)
        if cap is not None:
            label += " (队长: {})".format(cap)
        print("{}: {}".format(label, "、".join(shown) if shown else "(空)"))
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
