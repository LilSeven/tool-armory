#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真心话大冒险（truth-or-dare）：内置题库随机抽真心话或大冒险，支持追加自定义题目。

用法示例：
    python truth-or-dare.py                        # 随机来一题（真心话/大冒险混合）
    python truth-or-dare.py truth                  # 指定抽真心话
    python truth-or-dare.py dare -n 3              # 连抽 3 道大冒险（不重复）
    python truth-or-dare.py --add-truth "你的第一份工资花在哪了？"   # 追加自定义真心话
    python truth-or-dare.py --add-dare "模仿一种动物叫声"            # 追加自定义大冒险
    python truth-or-dare.py --bank my-bank.json truth               # 用指定题库文件抽题
    python truth-or-dare.py --list                # 查看题库规模

说明：
    - 仅依赖 Python 标准库；
    - 自定义题目保存在 JSON 题库文件（默认 truth-or-dare-bank.json，可用 --bank 指定），
      抽题时与内置题库合并使用；
    - 退出码：0 成功；输入/用法错误为非 0（校验错误 1，命令行用法错误 2）。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

DEFAULT_BANK = "truth-or-dare-bank.json"

TRUTHS = [
    "说一个你至今没告诉过任何人的小习惯。",
    "办公室里你最佩服谁？为什么？",
    "你最近一次说谎是什么时候，骗的是谁？",
    "如果明天中了彩票，你做的第一件事是什么？",
    "说一件你学生时代最丢人的事。",
    "你手机相册里最不想被人看到的一张照片是什么？",
    "你熬夜最晚的一次是为了什么？",
    "同事里谁最像你理想中的自己？",
    "你偷偷羡慕过谁的生活？",
    "说一个你坚持最久的爱好。",
    "如果可以和任意一位历史人物吃饭，你选谁？",
    "你最近戒不掉的一样东西是什么？",
    "说一个你以为大家都知道、其实只有你知道的小秘密。",
    "上一次哭是因为什么？",
]

DARES = [
    "用夸张的表情朗读一段工作群聊天记录。",
    "模仿一位在场同事的口头禅，让大家猜是谁。",
    "接下来 1 分钟内，说话不许带「的」字。",
    "给大家展示你手机里最近一张照片并解释。",
    "用唱歌的方式说出你今天三餐吃了什么。",
    "做 10 个深蹲，边做边喊口号。",
    "模仿一种动物叫声，直到有人笑出声。",
    "让右边的人给你摆一个 pose，保持 15 秒。",
    "用最快的速度说一句绕口令，说错重来一次。",
    "当场给一位很久没联系的朋友发「在吗」。",
    "用一句话真诚夸奖在场的每一个人。",
    "表演你接到甲乙方电话时的标志性叹气。",
    "把「我饿了」用三种不同情绪各说一遍。",
    "闭眼单脚站立 20 秒，倒了重来。",
]


def setup_stdio() -> None:
    """统一按 UTF-8 输出，避免 Windows 终端/重定向场景下的乱码或编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def load_bank(path: str) -> dict:
    """读取自定义题库 JSON；文件不存在视为空题库，格式不对抛 ValueError。"""
    p = Path(path)
    if not p.exists():
        return {"truths": [], "dares": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"题库文件损坏或不可读：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise ValueError(f"题库文件格式不对（应为 JSON 对象）：{path}")
    truths, dares = data.get("truths", []), data.get("dares", [])
    if not isinstance(truths, list) or not isinstance(dares, list):
        raise ValueError(f"题库文件的 truths/dares 应为字符串数组：{path}")
    return {"truths": [str(t) for t in truths], "dares": [str(d) for d in dares]}


def save_bank(path: str, bank: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def draw_questions(pool: list, count: int, rng: random.Random) -> list:
    """从 [(类型, 题目)] 池中不重复地抽 count 题。"""
    unique = list(dict.fromkeys(pool))
    if count > len(unique):
        raise ValueError(
            f"题不够抽：当前题库共 {len(unique)} 题，却要求抽 {count} 题。"
            "可用 --add-truth / --add-dare 补充，或调小 -n。"
        )
    return rng.sample(unique, count)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="truth-or-dare",
        description="真心话大冒险：从内置 + 自定义题库里随机抽题。",
    )
    parser.add_argument("mode", nargs="?", default=None,
                        choices=["truth", "dare", "random"],
                        help="抽题类型：truth=真心话，dare=大冒险，random=随机（缺省即随机）")
    parser.add_argument("-n", "--count", type=int, default=1, help="抽题数量（默认 1）")
    parser.add_argument("--add-truth", action="append", default=[], metavar="题目",
                        help="向题库追加一条自定义真心话（可多次使用）")
    parser.add_argument("--add-dare", action="append", default=[], metavar="题目",
                        help="向题库追加一条自定义大冒险（可多次使用）")
    parser.add_argument("--bank", default=DEFAULT_BANK, metavar="文件",
                        help=f"自定义题库 JSON 文件（默认 {DEFAULT_BANK}）")
    parser.add_argument("--list", action="store_true", help="只显示题库规模，不抽题")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，结果可复现")
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    args = build_parser().parse_args(argv)

    try:
        bank = load_bank(args.bank)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    # 追加自定义题目
    if args.add_truth or args.add_dare:
        changed = []
        for text in args.add_truth:
            text = text.strip()
            if not text:
                continue
            if text in TRUTHS + bank["truths"]:
                print(f"真心话已存在，跳过：{text}")
            else:
                bank["truths"].append(text)
                changed.append(("真心话", text))
        for text in args.add_dare:
            text = text.strip()
            if not text:
                continue
            if text in DARES + bank["dares"]:
                print(f"大冒险已存在，跳过：{text}")
            else:
                bank["dares"].append(text)
                changed.append(("大冒险", text))
        if changed:
            try:
                save_bank(args.bank, bank)
            except OSError as exc:
                print(f"错误：无法保存题库 {args.bank}：{exc}", file=sys.stderr)
                return 1
            for kind, text in changed:
                print(f"已追加{kind}：{text}")
            print(f"题库已保存到：{args.bank}")
        if args.mode is None:
            return 0  # 只追加不抽题

    truths = TRUTHS + bank["truths"]
    dares = DARES + bank["dares"]

    if args.list:
        print(f"题库规模：真心话 {len(truths)} 条（自定义 {len(bank['truths'])} 条），"
              f"大冒险 {len(dares)} 条（自定义 {len(bank['dares'])} 条），题库文件：{args.bank}")
        return 0

    if args.count < 1:
        print("错误：-n/--count 至少为 1。", file=sys.stderr)
        return 1

    mode = args.mode or "random"
    if mode == "truth":
        pool = [("真心话", t) for t in truths]
    elif mode == "dare":
        pool = [("大冒险", d) for d in dares]
    else:
        pool = [("真心话", t) for t in truths] + [("大冒险", d) for d in dares]

    rng = random.Random(args.seed)
    try:
        picked = draw_questions(pool, args.count, rng)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"本轮抽题（{'随机' if mode == 'random' else '真心话' if mode == 'truth' else '大冒险'}"
          f" × {len(picked)}）：")
    for i, (kind, question) in enumerate(picked, 1):
        print(f"  [{i}] 【{kind}】{question}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
