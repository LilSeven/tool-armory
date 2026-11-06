#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""名单抽人 —— 从参数或文件名单中随机抽取一人/多人, 已抽者自动移出池。

用途:
    名单可来自命令行参数或文本文件(每行一个名字, # 开头为注释)。
    抽中的人会写入"池记录文件", 之后的抽取自动排除他们(抽完即移出池),
    直到用 --reset 清空记录让全员回到池中; --show-pool 可查看剩余名单。

示例:
    python list-picker.py 张三 李四 王五                  # 从参数中抽 1 人
    python list-picker.py -n 2 -f names.txt              # 从文件中抽 2 人
    python list-picker.py -f names.txt --show-pool       # 查看池中剩余名单
    python list-picker.py -f names.txt --reset           # 清空抽取记录
    python list-picker.py 张三 李四 --state pool.json    # 指定池记录文件
    python list-picker.py -f names.txt --no-save         # 抽但不记, 不影响池

池记录文件:
    用 -f 时默认为 <名单文件>.picked.json; 用参数名单时默认为当前目录下的
    .list-picker.state.json; 均可用 --state 覆盖。--reset 需与名单来源同用
    以定位记录文件。

退出码: 0 成功; 1 名单/池记录问题或池中人数不足; 2 参数错误。
"""

import argparse
import json
import random
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


def load_state(path):
    """读取池记录, 返回 (已抽集合, 错误信息或 None); 文件不存在视为空。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return set(), None
    except (OSError, ValueError) as exc:
        return None, "无法读取池记录 {}: {}".format(path, exc)
    if (isinstance(data, dict) and isinstance(data.get("picked"), list)
            and all(isinstance(x, str) for x in data["picked"])):
        return set(data["picked"]), None
    return None, ("池记录 {} 格式不正确(应为 {{\"picked\": [名字, ...]}}), "
                  "可删除该文件或用 --reset 重置".format(path))


def save_state(path, picked):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"picked": sorted(picked)}, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="list-picker",
        description="从参数或文件名单中随机抽人, 已抽者自动移出池。")
    parser.add_argument("names", nargs="*", help="名单(与 -f 二选一)")
    parser.add_argument("-n", "--count", type=positive_int, default=1,
                        metavar="N", help="抽取人数 (默认 1)")
    parser.add_argument("-f", "--file",
                        help="名单文件, 每行一个名字, # 开头为注释")
    parser.add_argument("--state", help="池记录文件路径 (覆盖默认位置)")
    parser.add_argument("--show-pool", action="store_true",
                        help="只显示池中剩余名单, 不抽取")
    parser.add_argument("--reset", action="store_true",
                        help="清空抽取记录, 全员回到池中(需同时给出名单来源)")
    parser.add_argument("--no-save", action="store_true",
                        help="本次抽取不写入池记录(不影响池)")
    parser.add_argument("--seed", type=int, help="随机种子(便于复现)")
    args = parser.parse_args(argv)

    if args.file and args.names:
        parser.error("不能同时使用 -f/--file 与位置参数名单, 二选一")

    if args.file:
        try:
            all_names = read_names(args.file)
        except OSError as exc:
            print("错误: 无法读取名单文件: {}".format(exc), file=sys.stderr)
            return 2
        default_state = args.file + ".picked.json"
    elif args.names:
        all_names = []
        seen = set()
        for name in args.names:
            cleaned = name.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                all_names.append(cleaned)
        default_state = ".list-picker.state.json"
    else:
        parser.error("请提供名单: 位置参数或 -f/--file 名单文件")

    state_path = args.state or default_state

    if args.reset:
        try:
            save_state(state_path, set())
        except OSError as exc:
            print("错误: 无法写入池记录 {}: {}".format(state_path, exc),
                  file=sys.stderr)
            return 1
        print("已清空池记录: {} ({} 人全部回到池中)".format(
            state_path, len(all_names)))
        return 0

    picked, err = load_state(state_path)
    if err:
        print("错误: {}".format(err), file=sys.stderr)
        return 1

    if args.no_save:
        remaining = list(all_names)
    else:
        remaining = [n for n in all_names if n not in picked]

    if args.show_pool:
        print("池中剩余 {}/{} 人 (记录: {})".format(
            len(remaining), len(all_names), state_path))
        for name in remaining:
            print("  " + name)
        return 0

    if len(remaining) < args.count:
        print("错误: 池中仅剩 {} 人, 不足以抽取 {} 人 (可用 --reset 重置)".format(
            len(remaining), args.count), file=sys.stderr)
        return 1

    picks = random.Random(args.seed).sample(remaining, args.count)

    if not args.no_save:
        picked.update(picks)
        try:
            save_state(state_path, picked)
        except OSError as exc:
            print("错误: 无法写入池记录 {}: {}".format(state_path, exc),
                  file=sys.stderr)
            return 1
        print("已移出池并记录到 {} (池中剩余 {} 人)".format(
            state_path, len(remaining) - args.count))

    if args.count == 1:
        print("抽中: {}".format(picks[0]))
    else:
        print("抽中 {} 人: {}".format(args.count, "、".join(picks)))
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
