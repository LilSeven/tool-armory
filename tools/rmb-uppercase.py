#!/usr/bin/env python3
"""人民币大写金额转换器（阿拉伯数字 → 财会规范大写）。

用途：
    把数字金额转成规范的人民币大写，零与整的处理遵循财会惯例：
      * 整数部分四位一组，按 万/亿/万亿 进位，组内零合并、组尾零省略；
      * 10~19 写“壹拾…”（不省略“壹”）；
      * “元”后无角有分时补“零”（壹元零贰分）；分位为零时以“整”收尾；
      * 无整数部分时省略“元”（肆角贰分）；角分按 ROUND_HALF_UP 舍入到两位。

示例命令：
    python rmb-uppercase.py --selftest
    python rmb-uppercase.py 1234.56              # 壹仟贰佰叁拾肆元伍角陆分
    python rmb-uppercase.py 0.02 1.4 1005000     # 贰分 / 壹元肆角整 / 壹佰万零伍仟元整
    python rmb-uppercase.py "1,234,567.89"       # 支持千分位逗号与 ￥ 前缀

退出码：0 成功；1 selftest 失败；2 金额无法识别或超出范围（< 10^16 元）。
"""

import argparse
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

DIGITS = "零壹贰叁肆伍陆柒捌玖"
GROUP_MARKS = ("", "万", "亿", "万亿")
MAX_YUAN = 10 ** 16          # 整数部分上限：9999 万亿


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def four_group(v: int) -> str:
    """把 0~9999 转成组内大写（不含万/亿标记），如 105 → 壹佰零伍。"""
    s = f"{v:04d}"
    units = ("仟", "佰", "拾", "")
    out = []
    for i, ch in enumerate(s):
        d = int(ch)
        if d == 0:
            # 仅当后面还有非零数字时才补一个“零”，连续零只补一个
            if out and out[-1] != "零" and any(c != "0" for c in s[i:]):
                out.append("零")
        else:
            out.append(DIGITS[d] + units[i])
    return "".join(out)


def int_to_cn(x: int) -> str:
    if x < 0:
        raise ValueError("整数部分不应为负")
    if x >= MAX_YUAN:
        raise ValueError(f"金额超出可表示范围（整数部分需 < {MAX_YUAN}）")
    if x == 0:
        return "零"
    groups = []
    while x:
        groups.append(x % 10000)
        x //= 10000
    out = []
    for idx in range(len(groups) - 1, -1, -1):
        val = groups[idx]
        if val == 0:
            continue
        # 与上一组之间隔着零位（本组不足千位，或上一组个位为 0）时补“零”
        if out and (val < 1000 or groups[idx + 1] % 10 == 0):
            out.append("零")
        out.append(four_group(val) + GROUP_MARKS[idx])
    return "".join(out)


def parse_amount(text: str) -> Decimal:
    t = text.strip().translate(str.maketrans("", "", "，, ￥¥\t"))
    if not t:
        raise ValueError(f"空金额：{text!r}")
    try:
        d = Decimal(t)
    except (InvalidOperation, ValueError):
        raise ValueError(f"无法识别的金额：{text!r}") from None
    if not d.is_finite():
        raise ValueError("金额必须是有限数字")
    if abs(d) >= MAX_YUAN:
        raise ValueError(f"金额超出范围：整数部分需小于 {MAX_YUAN}（10^16）元")
    return d


def to_upper(text: str) -> str:
    d = parse_amount(text)
    cents = int((abs(d) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    yuan, rem = divmod(cents, 100)
    jiao, fen = divmod(rem, 10)
    if yuan == jiao == fen == 0:
        return "零元整"
    parts = []
    if d < 0:
        parts.append("负")
    if yuan:
        parts.append(int_to_cn(yuan) + "元")
    if jiao:
        parts.append(DIGITS[jiao] + "角")
    elif fen and yuan:
        parts.append("零")
    if fen:
        parts.append(DIGITS[fen] + "分")
    if fen == 0:
        parts.append("整")
    return "".join(parts)


def selftest() -> int:
    cases = [
        ("0", "零元整"),
        ("0.02", "贰分"),
        ("0.2", "贰角整"),
        ("0.42", "肆角贰分"),
        ("1", "壹元整"),
        ("1.02", "壹元零贰分"),
        ("1.4", "壹元肆角整"),
        ("1.23", "壹元贰角叁分"),
        ("10", "壹拾元整"),
        ("15.06", "壹拾伍元零陆分"),
        ("110", "壹佰壹拾元整"),
        ("105", "壹佰零伍元整"),
        ("1002", "壹仟零贰元整"),
        ("1234.56", "壹仟贰佰叁拾肆元伍角陆分"),
        ("1005000", "壹佰万零伍仟元整"),
        ("100000000", "壹亿元整"),
        ("100010000", "壹亿零壹万元整"),
        ("1100000000000", "壹万亿壹仟亿元整"),
        ("100000000000001", "壹佰万亿零壹元整"),
        ("9999999999999999.99",
         "玖仟玖佰玖拾玖万亿玖仟玖佰玖拾玖亿玖仟玖佰玖拾玖万玖仟玖佰玖拾玖元玖角玖分"),
        ("-3.14", "负叁元壹角肆分"),
        ("1.239", "壹元贰角肆分"),          # ROUND_HALF_UP 舍入
        ("1,234.56", "壹仟贰佰叁拾肆元伍角陆分"),
    ]
    ok = True
    for text, want in cases:
        got = to_upper(text)
        passed = got == want
        ok = ok and passed
        print(f"[{'PASS' if passed else 'FAIL'}] {text} -> {got}"
              + ("" if passed else f"（期望 {want}）"))
    for bad in ("abc", "1.2.3", "", "nan"):
        try:
            to_upper(bad)
            ok = ok and False
            print(f"[FAIL] 非法输入被拒绝：{bad!r}")
        except ValueError:
            print(f"[PASS] 非法输入被拒绝：{bad!r}")
    print("selftest:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


def main(argv=None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(description="人民币大写金额转换器")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("amounts", nargs="*", metavar="金额",
                    help="一个或多个数字金额")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.amounts:
        ap.error("请提供至少一个金额，或使用 --selftest")
    rc = 0
    for text in args.amounts:
        try:
            print(to_upper(text))
        except ValueError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            rc = 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
