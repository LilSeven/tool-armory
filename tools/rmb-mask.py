#!/usr/bin/env python3
"""rmb-mask —— 金额脱敏打码。

对文本中的金额按规则打码：数字部分保留首尾各 N 位，中间逐字符以 * 替代；
货币前缀（人民币/￥/¥/RMB）与单位（亿元/万元/元/圆）原样保留。
适用于截图、公示材料等对外场景。

示例命令：
  python rmb-mask.py contract.txt
  python rmb-mask.py contract.txt -o masked.txt --keep-first 2 --keep-last 2
  python rmb-mask.py contract.txt --list      # 只打印打码明细，不输出全文
  cat notice.txt | python rmb-mask.py -

规则：
  * 金额识别口径与 rmb-extract-text 相同（数字须带货币前缀或元级单位后缀）；
  * 默认 人民币1,234,567.89元 -> 人民币1**********9元（首尾各保留 1 位）；
  * 中间的千分位逗号与小数点也一并打码；--keep-dot 可保留小数点明文；
  * 数字长度 ≤ 首尾保留位数之和（没有可打码的中段）时，整体替换为等长 *，
    防止“看起来打码了其实没打”的漏码；
  * 未匹配到金额的文本原样输出，退出码 0。
"""

import argparse
import re
import sys

NUM_PART = r"(?:[0-9０-９]{1,3}(?:[,，][0-9０-９]{3})+|[0-9０-９]+)(?:[.．][0-9０-９]+)?"
AMOUNT_RE = re.compile(
    r"(?P<pre>(?:人民币|(?<![A-Za-z])[Rr][Mm][Bb]|￥|¥)\s*)"
    r"(?P<num>" + NUM_PART + r")"
    r"(?P<unit>\s*(?:亿元|万元|元|圆))?"
    r"|(?P<num2>" + NUM_PART + r")"
    r"(?P<unit2>\s*(?:亿元|万元|元|圆))"
)


class CliError(Exception):
    """用户可修正的错误（文件、参数等），退出码 2。"""


def mask_numeral(num: str, keep_first: int, keep_last: int, keep_dot: bool) -> str:
    if keep_first + keep_last >= len(num):
        return "*" * len(num)
    mid = num[keep_first:len(num) - keep_last]
    if keep_dot:
        mid = "".join(ch if ch == "." else "*" for ch in mid)
    else:
        mid = "*" * len(mid)
    return num[:keep_first] + mid + num[len(num) - keep_last:]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="rmb-mask",
        description="对文本中的金额打码：保留首尾、中间以 * 替代。",
    )
    ap.add_argument("input", help="输入文本文件路径；- 表示从 stdin 读取")
    ap.add_argument("-o", "--output", help="输出文件路径（缺省 stdout，UTF-8）")
    ap.add_argument("--keep-first", type=int, default=1, help="保留数字前 N 位（默认 1）")
    ap.add_argument("--keep-last", type=int, default=1, help="保留数字后 N 位（默认 1）")
    ap.add_argument("--keep-dot", action="store_true",
                    help="保留小数点明文（默认与中间字符一并打码）")
    ap.add_argument("--list", action="store_true",
                    help="只打印打码明细（行号/原文/打码后），不输出全文")
    ap.add_argument("--encoding", default="utf-8",
                    help="输入文件编码（默认 utf-8，GBK 文档可给 gbk）")
    args = ap.parse_args(argv)

    if args.keep_first < 0 or args.keep_last < 0:
        raise CliError("--keep-first/--keep-last 不能为负数")

    try:
        if args.input == "-":
            text = sys.stdin.read()
        else:
            with open(args.input, "r", encoding=args.encoding) as fh:
                text = fh.read()
    except OSError as exc:
        raise CliError(f"无法读取输入文件：{exc}") from exc
    except UnicodeDecodeError as exc:
        raise CliError(f"按 {args.encoding} 解码失败：{exc}（可尝试 --encoding gbk）") from exc

    records = []

    def repl(m):
        num = m.group("num") if m.group("num") is not None else m.group("num2")
        pre = m.group("pre") or ""
        unit = m.group("unit") or m.group("unit2") or ""
        masked = mask_numeral(num, args.keep_first, args.keep_last, args.keep_dot)
        line = text.count("\n", 0, m.start()) + 1
        records.append((line, num, masked))
        return pre + masked + unit

    masked_text = AMOUNT_RE.sub(repl, text)

    if args.list:
        out = "".join(f"第{ln}行\t{num} -> {mk}\n" for ln, num, mk in records)
    else:
        out = masked_text

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(out)
        except OSError as exc:
            raise CliError(f"无法写入输出文件：{exc}") from exc
    else:
        sys.stdout.write(out)

    print(f"[rmb-mask] 打码 {len(records)} 处金额", file=sys.stderr)
    return 0


def run(argv=None) -> int:
    try:
        return main(argv)
    except CliError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(run())
