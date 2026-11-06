#!/usr/bin/env python3
"""摊桌表情包 —— (╯°□°）╯︵ ┻━┻ 翻桌颜文字大全与随机翻桌。

用途:
    内置一组经典「翻桌/扶桌」颜文字。无参数时随机翻一次桌;
    也可以列出全部、按编号取用、连翻多次, 或把桌子扶回去。

示例命令:
    python table-flip.py                  # 随机翻桌
    python table-flip.py --list           # 列出全部(带编号)
    python table-flip.py -n 3             # 打印第 3 个
    python table-flip.py --count 5        # 连续随机翻 5 次
    python table-flip.py --restore        # 扶回桌子
    python table-flip.py --seed 42        # 固定随机种子, 便于复现

退出码: 0 = 正常; 2 = 参数错误(如 -n 超出范围、--count 小于 1)。
"""

import argparse
import random
import sys

FLIPS = [
    "(╯°□°）╯︵ ┻━┻",
    "(ノಠ益ಠ)ノ彡┻━┻",
    "┻━┻ ︵ ヽ(`Д´)ノ︵ ┻━┻",
    "┻━┻︵ \\(°□°)/ ︵ ┻━┻",
    "(╯°Д°)╯︵ ┻━┻",
    "(╯‵□′)╯︵┻━┻",
    "(ﾉ≧∇≦)ﾉ ﾐ ┸━┸",
    "ヽ(`⌒´メ)ノ ┻━┻",
    "(┛◉Д◉)┛彡┻━┻",
    "(┛ಧ_ಧ)┛彡┻━┻",
    "(ﾉಥ益ಥ)ﾉ彡┻━┻",
    "(╯ರ~ರ）╯︵ ┻━┻",
    "(-°□°)-°□°)-°□°)- ┻━┻",
    "(ノ°□°)ノ︵ ┻━┻",
    "(ﾉ´ヮ`)ﾉ*: ･ﾟ ┻━┻",
    "ヽ(｀Д´)ﾉ︵ ┻━┻",
]

RESTORES = [
    "┬─┬ ノ( ゜-゜ノ)",
    "┬─┬ ﾉ( ゜-゜ﾉ)",
    "┬──┬ ノ(^_^ノ)",
]


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        if not sys.stdin.isatty():      # 管道输入按 UTF-8 读, 避免 GBK 误码
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="摊桌表情包: 翻桌颜文字大全与随机翻桌")
    ap.add_argument("--list", action="store_true", help="列出全部颜文字(带编号)")
    ap.add_argument("-n", "--pick", type=int, default=None, metavar="N",
                    help="打印第 N 个(从 1 开始)")
    ap.add_argument("-c", "--count", type=int, default=1,
                    help="随机翻桌次数, 默认 1")
    ap.add_argument("--restore", action="store_true", help="把桌子扶回去")
    ap.add_argument("--seed", type=int, default=None, help="随机种子(复现用)")
    ns = ap.parse_args(argv)

    if ns.seed is not None:
        random.seed(ns.seed)
    if ns.list:
        for i, f in enumerate(FLIPS, 1):
            print("%2d. %s" % (i, f))
        return 0
    if ns.pick is not None:
        if not 1 <= ns.pick <= len(FLIPS):
            print("编号超出范围: 有效范围 1..%d" % len(FLIPS), file=sys.stderr)
            return 2
        print(FLIPS[ns.pick - 1])
        return 0
    if ns.restore:
        print(random.choice(RESTORES))
        return 0
    if ns.count < 1:
        print("--count 至少为 1", file=sys.stderr)
        return 2
    for _ in range(ns.count):
        print(random.choice(FLIPS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
