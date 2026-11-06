#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""神秘圣诞老人（secret-santa）：名单洗牌生成互送配对，为每人输出一张防剧透的小纸条文件。

用法示例：
    python secret-santa.py 阿明 小红 阿强 小美               # 在 ./secret-santa-notes/ 生成小纸条
    python secret-santa.py -o D:/gifts 阿明 小红 阿强 小美    # 指定输出目录
    python secret-santa.py -f names.txt -o ./notes           # 从文件读名单（每行一人，# 注释）
    python secret-santa.py --organizer --seed 123 阿明 小红  # 额外打印组织者总表（剧透！）
    python secret-santa.py --seed 123 阿明 小红 阿强          # 固定种子可复现，便于组织者回看

说明：
    - 仅依赖 Python 标准库；配对保证没有人抽到自己（derangement）；
    - 每人一张小纸条（UTF-8 文本文件），只写「你要给谁送礼」，不含其他人的配对；
    - 未指定 --seed 时会随机生成一个种子并打印，配合 --organizer 可复现同一份配对；
    - 退出码：0 成功；输入/用法错误为非 0（校验错误 1，命令行用法错误 2）。
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path

UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def setup_stdio() -> None:
    """统一按 UTF-8 输出，避免 Windows 终端/重定向场景下的乱码或编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def read_text_file(path: str) -> str:
    """读取文本文件，依次尝试 utf-8(-sig) / gbk 编码，失败则抛 ValueError。"""
    last_err: Exception | None = None
    for enc in ("utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except UnicodeDecodeError as exc:
            last_err = exc
    raise ValueError(f"无法解码文件（已尝试 utf-8/gbk）：{last_err}")


def load_names(args: argparse.Namespace) -> list[str]:
    """合并文件名单与命令行名单；检查重复与空白。"""
    names: list[str] = []
    if args.file:
        for lineno, raw in enumerate(read_text_file(args.file).splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            names.append(line)
    names.extend(args.people)
    names = [n.strip() for n in names if n.strip()]
    seen: set[str] = set()
    for n in names:
        if n in seen:
            raise ValueError(f"名单里有重复的名字：{n}")
        seen.add(n)
    return names


def make_assignment(names: list[str], rng: random.Random) -> list[str]:
    """洗牌出一份「没有人抽到自己」的送礼对象列表（与 names 一一对应）。"""
    if len(names) < 2:
        raise ValueError(f"神秘圣诞老人至少需要 2 人，现在只有 {len(names)} 人。")
    while True:
        receivers = list(names)
        rng.shuffle(receivers)
        if all(g != r for g, r in zip(names, receivers)):
            return receivers


def note_text(giver: str, receiver: str) -> str:
    bar = "=" * 36
    lines = [
        bar,
        "神秘圣诞老人 · 小纸条",
        bar,
        f"致：{giver}",
        "",
        f"你抽到的送礼对象是 ——【 {receiver} 】",
        "",
        "请悄悄为 TA 准备一份礼物，",
        "别告诉任何人，交换日见分晓！",
        bar,
    ]
    return "\n".join(lines) + "\n"


def safe_filename(name: str) -> str:
    base = UNSAFE_FILENAME_CHARS.sub("_", name).strip(". ")
    return base or "未命名"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="secret-santa",
        description="神秘圣诞老人：洗牌生成互送配对，输出防剧透的小纸条文件。",
    )
    parser.add_argument("people", nargs="*", metavar="名字", help="参与名单（至少 2 人，不得重复）")
    parser.add_argument("-f", "--file", metavar="文件", help="从文件读取名单，每行一人，# 为注释")
    parser.add_argument("-o", "--out-dir", default="secret-santa-notes", metavar="目录",
                        help="小纸条输出目录（默认 ./secret-santa-notes）")
    parser.add_argument("--organizer", action="store_true",
                        help="额外打印完整配对总表（会剧透，仅组织者使用）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，结果可复现")
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    args = build_parser().parse_args(argv)

    try:
        names = load_names(args)
        seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2 ** 32)
        rng = random.Random(seed)
        receivers = make_assignment(names, rng)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        used: set[str] = set()
        for giver, receiver in zip(names, receivers):
            base = safe_filename(giver)
            filename = f"{base}.txt"
            i = 2
            while filename in used:  # 名字被清洗后可能撞名
                filename = f"{base}-{i}.txt"
                i += 1
            used.add(filename)
            path = out_dir / filename
            path.write_text(note_text(giver, receiver), encoding="utf-8")
            written.append(path)
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"名单共 {len(names)} 人，抽签种子：{seed}")
    print(f"已生成 {len(written)} 张防剧透小纸条，目录：{out_dir.resolve()}")
    for path in written:
        print(f"  {path.name}")
    print("每人只许看自己的那张；如需完整配对表，请用同样参数加 --organizer 重新运行。")
    if args.organizer:
        print("—— 组织者总表（剧透警告）——")
        for giver, receiver in zip(names, receivers):
            print(f"  {giver} → {receiver}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
