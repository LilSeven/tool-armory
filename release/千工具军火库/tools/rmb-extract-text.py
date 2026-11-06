#!/usr/bin/env python3
"""rmb-extract-text —— 文本金额抽取转大写。

从合同、公文等纯文本中用正则抽取金额表述，逐条给出「行号 | 原文 |
数值（元）| 人民币大写」，供人工复核；不对原文做任何改写。

示例命令：
  python rmb-extract-text.py contract.txt
  python rmb-extract-text.py contract.txt --sum
  python rmb-extract-text.py contract.txt --json -o hits.json
  cat contract.txt | python rmb-extract-text.py -

识别口径：
  * 阿拉伯数字金额（允许千分位逗号，如 1,234,567.89）；
  * 带货币前缀（人民币 / ￥ / ¥ / RMB，大小写不限）
    或货币单位后缀（亿元 / 万元 / 元 / 圆）二者至少其一；
  * 万元、亿元分别按 ×10^4、×10^8 换算为元后再转大写；
  * 不识别纯汉字金额（如“壹万元整”），也不识别“角/分”后缀（请用小数表达）；
  * 数值四舍五入到分后转大写；超过 10^20 元的金额该条大写记为空并告警。
"""

import argparse
import json
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

NUM_PART = r"(?:[0-9０-９]{1,3}(?:[,，][0-9０-９]{3})+|[0-9０-９]+)(?:[.．][0-9０-９]+)?"
AMOUNT_RE = re.compile(
    r"(?P<pre>(?:人民币|(?<![A-Za-z])[Rr][Mm][Bb]|￥|¥)\s*)"
    r"(?P<num>" + NUM_PART + r")"
    r"(?P<unit>\s*(?:亿元|万元|元|圆))?"
    r"|(?P<num2>" + NUM_PART + r")"
    r"(?P<unit2>\s*(?:亿元|万元|元|圆))"
)
UNIT_MULT = {"亿元": Decimal(10) ** 8, "万元": Decimal(10) ** 4,
             "元": Decimal(1), "圆": Decimal(1)}


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


def extract_hits(text):
    hits, warnings = [], []
    for m in AMOUNT_RE.finditer(text):
        num = m.group("num") if m.group("num") is not None else m.group("num2")
        unit = (m.group("unit") or m.group("unit2") or "").strip()
        pre = (m.group("pre") or "").strip()
        line = text.count("\n", 0, m.start()) + 1
        norm = num.translate(_FW).replace(",", "")
        try:
            value = Decimal(norm) * UNIT_MULT.get(unit, Decimal(1))
        except InvalidOperation:
            warnings.append(f"第{line}行：无法解析 {m.group(0)!r}")
            continue
        try:
            cn = to_rmb_upper(value)
        except ValueError as exc:
            cn = ""
            warnings.append(f"第{line}行：{m.group(0).strip()!r} {exc}")
        hits.append({"line": line, "text": m.group(0).strip(), "prefix": pre or None,
                     "unit": unit or None, "value_yuan": str(value), "cn": cn or None})
    return hits, warnings


def _total_cn(hits):
    total = Decimal(0)
    for h in hits:
        total += Decimal(h["value_yuan"])
    try:
        return str(total), to_rmb_upper(total)
    except ValueError:
        return str(total), "（超出可表示范围）"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="rmb-extract-text",
        description="从文本抽取金额表述并给出人民币大写，供人工复核。",
    )
    ap.add_argument("input", help="输入文本文件路径；- 表示从 stdin 读取")
    ap.add_argument("-o", "--output", help="结果写入文件（缺省 stdout，UTF-8）")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ap.add_argument("--sum", action="store_true", help="追加合计（全部换算为元后汇总）")
    ap.add_argument("--encoding", default="utf-8",
                    help="输入文件编码（默认 utf-8，GBK 文档可给 gbk）")
    args = ap.parse_args(argv)

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

    hits, warnings = extract_hits(text)

    if args.json:
        payload = {"count": len(hits), "items": hits}
        if args.sum:
            total_yuan, total_cn = _total_cn(hits)
            payload["total_yuan"] = total_yuan
            payload["total_cn"] = total_cn
        out = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    else:
        lines = [f"第{h['line']}行\t{h['text']}\t= {h['value_yuan']} 元\t{h['cn'] or '（无法转大写）'}"
                 for h in hits]
        if args.sum and hits:
            total_yuan, total_cn = _total_cn(hits)
            lines.append(f"合计\t{len(hits)} 笔\t= {total_yuan} 元\t{total_cn}")
        out = "".join(l + "\n" for l in lines)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(out)
        except OSError as exc:
            raise CliError(f"无法写入输出文件：{exc}") from exc
    else:
        sys.stdout.write(out)

    for w in warnings:
        print(f"[rmb-extract-text] 警告：{w}", file=sys.stderr)
    if not hits:
        print("[rmb-extract-text] 未识别到金额表述", file=sys.stderr)
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
