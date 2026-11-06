#!/usr/bin/env python3
"""rmb-fill-template —— 合同金额双写填充。

向合同/公文模板中的金额占位符同时填入数字与大写人民币，避免手抄错漏。
支持的占位符（大小写敏感，允许花括号内侧留空格）：
  {{amount}}       千分位 + 两位小数，如 1,234,567.89
  {{amount_plain}} 无千分位 + 两位小数，如 1234567.89
  {{amount_cn}}    人民币大写，如 壹佰贰拾叁万肆仟伍佰陆拾柒元捌角玖分

示例命令：
  python rmb-fill-template.py contract_template.txt --value 1234567.89 -o contract.txt
  python rmb-fill-template.py template.txt --value '1,234,567.89'
  cat template.txt | python rmb-fill-template.py - --value 5000

说明：
  * 金额四舍五入到分（ROUND_HALF_UP）后填充三种写法，保证双写一致；
  * 未识别的 {{xxx}} 占位符原样保留并在 stderr 提示；
  * 模板中没有金额占位符时照常输出并在 stderr 提示；
  * 输出固定为 UTF-8；模板输入编码可用 --encoding 指定（默认 utf-8）。
"""

import argparse
import re
import sys
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, getcontext

getcontext().prec = 60

CN_DIGITS = "零壹贰叁肆伍陆柒捌玖"
CN_PLACES = ("", "拾", "佰", "仟")
CN_SECTIONS = ("", "万", "亿", "兆", "京")
MAX_YUAN = 10 ** 20

# 全角数字/小数点/逗号/正负号 -> 半角
_FW = str.maketrans("０１２３４５６７８９．，－＋", "0123456789.,-+")
_PLAIN_NUM_RE = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")

PH_RE = re.compile(r"\{\{\s*(amount(?:_plain|_cn)?)\s*\}\}")
ANY_PH_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
KNOWN = {"amount", "amount_plain", "amount_cn"}


class CliError(Exception):
    """用户可修正的错误（文件、参数等），退出码 2。"""


def _clean_amount_str(value) -> str:
    s = str(value).strip().translate(_FW)
    for ch in (",", "'", " ", "¥", "￥"):
        s = s.replace(ch, "")
    if s.endswith("元"):
        s = s[:-1].strip()
    return s


def _read_group(n: int) -> str:
    """把 1..9999 的四位组读成大写，如 3050 -> 叁仟零伍拾。"""
    parts, pending = [], False
    for pos in (3, 2, 1, 0):
        d = (n // 10 ** pos) % 10
        if d == 0:
            if parts:
                pending = True
        else:
            if pending:
                parts.append("零")
            parts.append(CN_DIGITS[d] + CN_PLACES[pos])
            pending = False
    return "".join(parts)


def int_to_cn(n: int) -> str:
    if n == 0:
        return "零"
    if n < 0 or n >= MAX_YUAN:
        raise ValueError(f"整数部分超出可表示范围: {n}")
    groups = []
    while n:
        groups.append(n % 10000)
        n //= 10000
    out, pending_zero = [], False
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            if out and any(groups[j] for j in range(i)):
                pending_zero = True
            continue
        if out and (pending_zero or g < 1000):
            out.append("零")
        out.append(_read_group(g))
        out.append(CN_SECTIONS[i])
        pending_zero = False
    return "".join(out)


def parse_amount(value) -> Decimal:
    """'1,234.56' / '¥12' / '12元' / 1234 / 12.5 -> Decimal；失败抛 ValueError。"""
    if isinstance(value, Decimal):
        d = value
    else:
        s = _clean_amount_str(value)
        if not s:
            raise ValueError("空金额")
        if not _PLAIN_NUM_RE.fullmatch(s):
            raise ValueError(f"不支持的金额写法: {value!r}")
        try:
            d = Decimal(s)
        except InvalidOperation as exc:
            raise ValueError(f"无法解析金额: {value!r}") from exc
    if not d.is_finite():
        raise ValueError(f"金额必须为有限数: {value!r}")
    return d


def to_rmb_upper(value) -> str:
    """金额 -> 人民币大写。1234567.89 -> 壹佰贰拾叁万肆仟伍佰陆拾柒元捌角玖分"""
    d = parse_amount(value)
    neg = d < 0
    q = d.copy_abs().quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if q == 0:
        return "零元整"
    yuan = int(q)
    jiao, fen = divmod(int((q - yuan) * 100), 10)
    if yuan >= MAX_YUAN:
        raise ValueError(f"金额过大（≥ {MAX_YUAN} 元）")
    out = []
    if yuan > 0:
        out.append(int_to_cn(yuan))
        out.append("元")
    if jiao == 0 and fen == 0:
        out.append("整")
    else:
        if yuan > 0 and jiao == 0:
            out.append("零")
        if jiao > 0:
            out.append(CN_DIGITS[jiao] + "角")
        if fen > 0:
            out.append(CN_DIGITS[fen] + "分")
    if neg:
        out.insert(0, "负")
    return "".join(out)


def build_replacements(q: Decimal):
    return {
        "amount": f"{q:,.2f}",
        "amount_plain": f"{q:.2f}",
        "amount_cn": to_rmb_upper(q),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="rmb-fill-template",
        description="向模板的 {{amount}}/{{amount_cn}} 占位符同时填入数字与大写金额。",
    )
    ap.add_argument("template", help="模板文件路径；- 表示从 stdin 读取")
    ap.add_argument("--value", required=True,
                    help="金额数值，如 1234567.89 或 '1,234,567.89'")
    ap.add_argument("-o", "--output", help="输出文件路径（缺省 stdout，UTF-8）")
    ap.add_argument("--encoding", default="utf-8",
                    help="模板文件编码（默认 utf-8，GBK 模板可给 gbk）")
    args = ap.parse_args(argv)

    try:
        q = parse_amount(args.value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        repl = build_replacements(q)
    except (ValueError, InvalidOperation) as exc:
        raise CliError(str(exc)) from exc

    try:
        if args.template == "-":
            template = sys.stdin.read()
        else:
            with open(args.template, "r", encoding=args.encoding) as fh:
                template = fh.read()
    except OSError as exc:
        raise CliError(f"无法读取模板：{exc}") from exc
    except UnicodeDecodeError as exc:
        raise CliError(f"按 {args.encoding} 解码失败：{exc}（可尝试 --encoding gbk）") from exc

    rendered = PH_RE.sub(lambda m: repl[m.group(1)], template)

    unknown = sorted({m.group(1) for m in ANY_PH_RE.finditer(rendered)} - KNOWN)
    if unknown:
        print("[rmb-fill-template] 警告：未识别的占位符保持原样："
              + ", ".join("{{%s}}" % u for u in unknown), file=sys.stderr)
    if not PH_RE.search(template):
        print("[rmb-fill-template] 警告：模板中未发现金额占位符"
              "（{{amount}} / {{amount_plain}} / {{amount_cn}}）", file=sys.stderr)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(rendered)
        except OSError as exc:
            raise CliError(f"无法写入输出文件：{exc}") from exc
    else:
        sys.stdout.write(rendered)

    print(f"[rmb-fill-template] amount={repl['amount']} "
          f"plain={repl['amount_plain']} cn={repl['amount_cn']}", file=sys.stderr)
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
