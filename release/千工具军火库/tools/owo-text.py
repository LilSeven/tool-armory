#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""owo 萌文转换器（owo-text）。

用途：
    把输入文本转换成 owo 萌系风格文字：
    - 中文：做「我→窝、的→滴、了→惹、吗→喵」等萌化替换，
      开头随机加叠词口癖（"你好"→"你、你好"），句末随机补颜文字；
    - 纯英文：做经典 r/l→w 变换（"hello world"→"hewwo wowwd"）；
    - 中英混合：按中文规则处理。
    文本可来自命令行参数或 stdin 管道。

示例命令：
    python owo-text.py "今天天气真好，你想我吗？"    # 转换一句话
    printf 'hello world' | python owo-text.py       # 从管道读取
    python owo-text.py -n 2 "好想你"                # 生成两份不同版本
    python owo-text.py --no-faces "谢谢"            # 不加颜文字
    python owo-text.py --seed 42 "晚安"             # 固定随机种子，方便复现
"""

import argparse
import random
import re
import sys

# 颜文字库（输出统一走 UTF-8，避免 Windows 控制台 GBK 报错）
FACES = [
    "(o^▽^o)", "(＾▽＾)", "(owo)", "(uwu)", "(>ω<)",
    "ヾ(≧▽≦*)o", "(๑•̀ㅂ•́)و✧", "(｡•ᴗ•｡)♡",
]

# 中文萌化规则：(匹配串, 替换串, 触发概率)
ZH_RULES = [
    ("你们", "泥萌", 1.0),
    ("什么", "神马", 0.8),
    ("我", "窝", 0.6),
    ("的", "滴", 0.7),
    ("了", "惹", 0.7),
    ("吗", "喵", 0.8),
    ("么", "喵", 0.5),
    ("是", "素", 0.3),
]

# 纯英文经典 owo 规则：r/l → w
EN_TABLE = str.maketrans({"r": "w", "l": "w", "R": "W", "L": "W"})

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
SENT_END_RE = re.compile(r"([。！？!?~]+)")


def add_faces(text: str) -> str:
    """在句末标点后补颜文字；没有句末标点就在结尾补一个。"""
    out = SENT_END_RE.sub(
        lambda m: m.group(1) + " " + random.choice(FACES), text
    )
    if not re.search(r"[。！？!?~]$", text):
        out += " " + random.choice(FACES)
    return out


def convert_zh(text: str, faces: bool = True) -> str:
    """中文萌化：概率替换 + 开头叠词口癖 + 颜文字。"""
    for pat, rep, prob in ZH_RULES:
        text = re.sub(
            pat, lambda m, r=rep, p=prob: r if random.random() < p else m.group(0),
            text,
        )
    m = CJK_RE.search(text)
    if m and random.random() < 0.6:  # 口癖：把第一个汉字叠一遍
        i = m.start()
        text = text[:i] + text[i] + "、" + text[i:]
    if faces:
        text = add_faces(text)
    return text


def convert_en(text: str, faces: bool = True) -> str:
    """纯英文萌化：r/l→w + 结尾颜文字。"""
    text = text.translate(EN_TABLE)
    if faces:
        text += " " + random.choice(FACES)
    return text


def convert(text: str, faces: bool = True) -> str:
    if CJK_RE.search(text):
        return convert_zh(text, faces)
    return convert_en(text, faces)


def main() -> int:
    try:  # Windows 控制台默认 GBK，切到 UTF-8 避免输出报错
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        prog="owo-text",
        description="owo 萌文转换器：把输入文本转换成 owo 萌系风格文字。",
    )
    parser.add_argument(
        "text", nargs="?", default=None,
        help="要转换的文本；省略则从 stdin 读取",
    )
    parser.add_argument("-n", "--count", type=int, default=1, help="生成版本数（默认 1）")
    parser.add_argument("--no-faces", action="store_true", help="不在结尾加颜文字")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（用于复现）")
    args = parser.parse_args()

    if args.count < 1:
        parser.error("-n/--count 必须 >= 1")
    if args.seed is not None:
        random.seed(args.seed)

    if args.text is None:
        if sys.stdin.isatty():
            parser.error("请提供要转换的文本，或用管道喂给 stdin")
        text = sys.stdin.read()
    else:
        text = args.text
    text = text.strip()
    if not text:
        parser.error("输入文本为空")

    for _ in range(args.count):
        print(convert(text, faces=not args.no_faces))
    return 0


if __name__ == "__main__":
    sys.exit(main())
