#!/usr/bin/env python3
"""rmb-json-transform —— JSON 金额字段大写化。

遍历 JSON 文档，按「字段名」或「JSON 路径」匹配金额值（数字，或可解析为
数字的字符串，如 "1,234.56"），在该字段紧随其后的位置插入对应的人民币
大写字段（键名 = 原键名 + 后缀，默认 _cn），文档其余内容原样保留。

示例命令：
  python rmb-json-transform.py invoice.json                          # 用内置默认字段名匹配
  python rmb-json-transform.py invoice.json -o out.json --keys amount,total
  python rmb-json-transform.py invoice.json --paths '$..amount' '$.invoice.total'
  cat invoice.json | python rmb-json-transform.py -

约定与说明：
  * 金额按「元」理解，四舍五入到分（ROUND_HALF_UP）后转大写；
    以万元/亿元计价的字段请先换算，或匹配后人工复核；
  * 已存在的 <键><后缀> 字段会被重新计算覆盖；
  * 输出按 --indent 重新缩进（默认 2；0 表示单行），不保留原文件空白格式；
  * JSON float 经 str() 转十进制再计算，常规两位小数金额无损；
    对精度敏感建议用字符串存放金额；科学计数法写法（如 1e20）不识别；
  * 一个金额都没匹配到时照常输出，退出码仍为 0；出错退出码为 2。

路径模式（--paths，可重复给出、每处可给多个）支持三种写法：
  $.a.b          精确路径；数组下标写 [0]、[1]…，[*] 匹配任意下标
  $..name        任意层级中键名为 name 的标量
  $              根节点本身（仅为完备性保留）
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

DEFAULT_KEYS = ("amount,total,total_amount,subtotal,price,unit_price,"
                "money,sum,fee,cost,tax,premium,deposit,payment")

# 全角数字/小数点/逗号/正负号 -> 半角
_FW = str.maketrans("０１２３４５６７８９．，－＋", "0123456789.,-+")
_PLAIN_NUM_RE = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")


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


def as_decimal(v):
    """v 为数字或数字字符串时返回 Decimal，否则 None。bool 不算数字。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float, str)):
        try:
            return parse_amount(v)
        except ValueError:
            return None
    return None


def compile_path_pattern(pattern: str):
    pat = pattern.strip()
    if pat == "$":
        return lambda path: path == "$"
    if pat.startswith("$.."):
        name = pat[3:]
        if not name or any(c in name for c in ".[]*$"):
            raise CliError(f"不支持的路径模式 {pattern!r}：$..name 的 name 须为普通键名")
        tail = "." + name
        return lambda path: path.endswith(tail)
    if pat.startswith("$."):
        tokens = re.findall(r"\.([^.\[\]]+)|\[(\*|\d+)\]", pat[1:])
        rebuilt = "$" + "".join("." + a if a else "[" + b + "]" for a, b in tokens)
        if not tokens or rebuilt != pat:
            raise CliError(f"不支持的路径模式 {pattern!r}")
        rx = "^"
        for a, b in tokens:
            if a:
                rx += re.escape("." + a)
            else:
                rx += r"\[\d+\]" if b == "*" else re.escape("[" + b + "]")
        return re.compile(rx + "$").match
    raise CliError(f"路径模式必须以 $ 开头: {pattern!r}")


def transform(node, path, keyset, matchers, suffix, stats):
    if isinstance(node, dict):
        children = {}
        plan = {}
        skip = set()
        for k, v in node.items():
            child = f"{path}.{k}"
            children[k] = transform(v, child, keyset, matchers, suffix, stats)
            d = as_decimal(v)
            if d is not None and (k in keyset or any(m(child) for m in matchers)):
                try:
                    plan[k] = (to_rmb_upper(d), child, v)
                except ValueError as exc:
                    print(f"[rmb-json-transform] 警告：跳过 {child}：{exc}", file=sys.stderr)
                    continue
                skip.add(k + suffix)
        result = {}
        for k in node:
            if k in skip:  # 原文档中与本批插入重名的后缀键，让位给重新计算的值
                continue
            result[k] = children[k]
            if k in plan:
                cn, child, orig = plan[k]
                result[k + suffix] = cn
                stats.append((child, orig, cn))
        return result
    if isinstance(node, list):
        return [transform(v, f"{path}[{i}]", keyset, matchers, suffix, stats)
                for i, v in enumerate(node)]
    return node


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="rmb-json-transform",
        description="JSON 金额字段大写化：按字段名/路径匹配金额并插入大写字段。",
    )
    ap.add_argument("input", help="输入 JSON 文件路径；- 表示从 stdin 读取")
    ap.add_argument("-o", "--output", help="输出文件路径（缺省写到 stdout）")
    ap.add_argument("--keys", default=DEFAULT_KEYS,
                    help="逗号分隔的金额字段名；传空字符串 '' 禁用按键名匹配")
    ap.add_argument("--paths", action="append", nargs="+", default=[],
                    metavar="PATTERN", help="路径模式，可重复给出，如 --paths '$..amount'")
    ap.add_argument("--suffix", default="_cn", help="插入字段的后缀（默认 _cn，不能为空）")
    ap.add_argument("--indent", type=int, default=2,
                    help="输出缩进空格数（默认 2；0 表示单行）")
    args = ap.parse_args(argv)

    if not args.suffix:
        raise CliError("--suffix 不能为空字符串")
    keyset = {s.strip() for s in args.keys.split(",") if s.strip()}
    patterns = [p for group in args.paths for p in group]
    matchers = [compile_path_pattern(p) for p in patterns]

    try:
        if args.input == "-":
            data = json.load(sys.stdin)
        else:
            with open(args.input, "r", encoding="utf-8") as fh:
                data = json.load(fh)
    except OSError as exc:
        raise CliError(f"无法读取输入文件：{exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CliError(f"输入不是合法的 UTF-8 JSON：{exc}") from exc

    stats = []
    result = transform(data, "$", keyset, matchers, args.suffix, stats)

    text = json.dumps(result, ensure_ascii=False,
                      indent=args.indent if args.indent and args.indent > 0 else None)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except OSError as exc:
            raise CliError(f"无法写入输出文件：{exc}") from exc
    else:
        sys.stdout.write(text + "\n")

    print(f"[rmb-json-transform] 插入 {len(stats)} 个大写字段"
          + (f" -> {args.output}" if args.output else ""), file=sys.stderr)
    for path, orig, cn in stats:
        print(f"  {path} = {orig} -> {cn}", file=sys.stderr)
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
