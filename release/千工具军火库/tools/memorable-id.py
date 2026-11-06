#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可读 ID 生成 —— 生成 形容词-名词-数字 形式的非敏感可读标识符, 带反查碰撞计数。

用途:
    生成形如 brave-falcon-42 的可读 ID(48 形容词 × 48 名词 × 数字区间),
    词表全是常见英文词, 不含任何敏感信息。批内保证互异; 每次运行向 stderr
    输出统计: 组合空间、批内碰撞重试次数、与 --used 历史清单的碰撞命中数
    (碰撞计数); --check 可对任意 ID 做反查: 验证词表归属并给出词表序号与
    全局唯一序号。随机源为 secrets 模块。

示例命令:
    python memorable-id.py                        # 1 个, 如 brave-falcon-42
    python memorable-id.py -n 5                   # 一次 5 个
    python memorable-id.py -n 5 --num-max 9       # 数字部分限制在 1-9(空间变小)
    python memorable-id.py --check brave-falcon-42   # 反查: 词表序号/全局序号/空间
    python memorable-id.py -n 3 --used used.txt   # 避开历史已用 ID 并统计命中
    python memorable-id.py -n 5 --quiet           # 不输出 stderr 统计
"""

import argparse
import secrets
import sys

ADJECTIVES = (
    "amber", "bold", "brave", "bright", "calm", "cedar", "clear", "clever",
    "cosmic", "crisp", "eager", "fresh", "gentle", "golden", "grand", "happy",
    "humble", "ivory", "jolly", "keen", "lively", "lucky", "lunar", "merry",
    "mild", "misty", "noble", "olive", "plucky", "quiet", "rapid", "royal",
    "rustic", "serene", "sharp", "silver", "solar", "spicy", "stellar", "sunny",
    "swift", "tender", "tidy", "urban", "velvet", "vivid", "warm", "wise",
)
NOUNS = (
    "anchor", "badger", "beacon", "birch", "blossom", "cactus", "canyon", "cliff",
    "comet", "coral", "daisy", "dolphin", "eagle", "falcon", "fern", "fjord",
    "glacier", "harbor", "heron", "island", "jaguar", "kite", "lagoon", "lantern",
    "maple", "meadow", "meteor", "nebula", "oak", "orbit", "otter", "panda",
    "penguin", "pine", "quail", "raven", "reef", "river", "robin", "sparrow",
    "summit", "tiger", "valley", "walnut", "whale", "willow", "wolf", "zebra",
)


def load_used(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return {line.strip() for line in f if line.strip()}
    except OSError as exc:
        sys.exit("错误: 读取历史清单 %s 失败: %s" % (path, exc))


def generate_ids(count, used, lo, hi, space):
    """生成 count 个互异且不在 used 中的 ID, 返回 (ID列表, 批内碰撞, 历史命中)。"""
    seen, out = set(), []
    in_batch = hist = 0
    attempts, limit = 0, space * 20 + 100000
    while len(out) < count:
        attempts += 1
        if attempts > limit:
            sys.exit("错误: 尝试 %d 次仍无法凑齐 %d 个互异 ID(组合空间近乎耗尽)"
                     % (attempts, count))
        cid = "%s-%s-%d" % (secrets.choice(ADJECTIVES), secrets.choice(NOUNS),
                            secrets.randbelow(hi - lo + 1) + lo)
        if cid in seen:
            in_batch += 1
            continue
        if cid in used:
            hist += 1
            continue
        seen.add(cid)
        out.append(cid)
    return out, in_batch, hist


def cmd_check(cid, lo, hi, space):
    """反查一个 ID: 验证词表并输出序号; 返回退出码。"""
    def fail(msg):
        print("无效 ID: %s (%s)" % (cid, msg), file=sys.stderr)
        return 1

    parts = cid.split("-")
    if len(parts) != 3:
        return fail("格式应为 形容词-名词-数字")
    a, n, num = parts
    if a not in ADJECTIVES:
        return fail("形容词 %r 不在词表" % a)
    if n not in NOUNS:
        return fail("名词 %r 不在词表" % n)
    if not num.isdigit():
        return fail("数字段 %r 不是纯数字" % num)
    v = int(num)
    if not lo <= v <= hi:
        return fail("数字 %d 超出范围 %d-%d" % (v, lo, hi))
    a_idx, n_idx = ADJECTIVES.index(a), NOUNS.index(n)
    span = hi - lo + 1
    rank = a_idx * len(NOUNS) * span + n_idx * span + (v - lo)
    print("有效 ID: %s" % cid)
    print("  反查: 形容词#%d/%d %s | 名词#%d/%d %s | 数字 %d(范围 %d-%d)"
          % (a_idx + 1, len(ADJECTIVES), a, n_idx + 1, len(NOUNS), n, v, lo, hi))
    print("  词表反查全局序号(0 基): %d | 总组合空间: %d" % (rank, space))
    return 0


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="生成 形容词-名词-数字 形式的可读 ID, 带反查与碰撞计数。")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="生成数量(默认 1, 上限 100000)")
    parser.add_argument("--num-min", type=int, default=1, help="数字部分下界(默认 1)")
    parser.add_argument("--num-max", type=int, default=99, help="数字部分上界(默认 99)")
    parser.add_argument("--used", help="历史已用 ID 清单文件(每行一条), 生成时避开")
    parser.add_argument("--check", metavar="ID",
                        help="反查一个 ID: 验证词表并给出序号/总空间")
    parser.add_argument("--quiet", action="store_true", help="不向 stderr 输出统计")
    args = parser.parse_args(argv)

    lo, hi = args.num_min, args.num_max
    if lo > hi:
        parser.error("--num-min 不能大于 --num-max")
    space = len(ADJECTIVES) * len(NOUNS) * (hi - lo + 1)

    if args.check:
        return cmd_check(args.check, lo, hi, space)

    if not 1 <= args.count <= 100000:
        parser.error("--count 取值范围 1-100000")
    if args.count > space:
        sys.exit("错误: 组合空间 %d 不足以生成 %d 个互异 ID" % (space, args.count))

    used = load_used(args.used) if args.used else set()
    ids, in_batch, hist = generate_ids(args.count, used, lo, hi, space)
    for cid in ids:
        print(cid)
    if not args.quiet:
        print("统计: 组合空间 %d(=%d形容词×%d名词×%d数字) | 生成 %d | "
              "批内碰撞重试 %d | 历史已用命中 %d"
              % (space, len(ADJECTIVES), len(NOUNS), hi - lo + 1,
                 len(ids), in_batch, hist), file=sys.stderr)
    return 0


if __name__ == "__main__":
    _utf8_stdio()
    sys.exit(main())
