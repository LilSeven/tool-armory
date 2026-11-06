#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量密码开表 —— 为账号清单批量生成密码并导出 CSV, 附强度评分列。

用途:
    账号来源二选一:
      1) -i 账号清单.csv : 从 CSV 读账号, 默认取第一列(--column 可指定列名),
         首行含 account/user/账号 等字样时自动按表头跳过(--no-header 强制全按数据行);
      2) -n 数量 : 无清单时自动编号 user001..userN(--prefix 改前缀), 缺省 10 行。
    输出 CSV 列: account,password,score,strength,length
      score    = min(100, 估算熵比特数), 再按"字符重复度高/字符池单一/长度不足"扣分
      strength = 极强(>=80) / 强(>=60) / 中(>=40) / 弱(<40)
    密码默认 16 位, 四类字符(小写/大写/数字/符号)各至少 1 个, 默认剔除易混
    字符(l/1/I、o/0/O); 随机源为 secrets 模块; 输出文件用 UTF-8-SIG 编码,
    Windows Excel 可直接打开不乱码。

示例命令:
    python password-batch-csv.py -n 10 -o out.csv               # 生成 10 行账号密码表
    python password-batch-csv.py -i accounts.csv -o out.csv     # 按清单逐行配密码
    python password-batch-csv.py -i accounts.csv --column user -l 20 -o out.csv
    python password-batch-csv.py -n 3                           # 不带 -o 时打印到 stdout
"""

import argparse
import csv
import math
import secrets
import sys

LOWER = "abcdefghijkmnpqrstuvwxyz"      # 24 个, 剔除易混 l o
UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"      # 24 个, 剔除易混 I O
DIGITS = "23456789"                     # 8 个, 剔除易混 0 1
SYMBOLS = "!@#$%^&*-_=+"

HEADER_WORDS = {"account", "name", "user", "username", "id",
                "账号", "账户", "用户", "用户名"}


def gen_password(length, allow_ambiguous=False):
    """生成保证四类字符各至少 1 个的随机密码(secrets 版 Fisher-Yates 洗牌)。"""
    if allow_ambiguous:
        lower, upper, digits = "abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "0123456789"
    else:
        lower, upper, digits = LOWER, UPPER, DIGITS
    pools = [lower, upper, digits, SYMBOLS]
    chars = [secrets.choice(p) for p in pools]
    all_chars = "".join(pools)
    chars += [secrets.choice(all_chars) for _ in range(length - len(pools))]
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def score_password(pw):
    """返回 (0-100 整数分, 估算熵比特数, 强度标签)。"""
    pool = 0
    if any(c.islower() for c in pw):
        pool += 26
    if any(c.isupper() for c in pw):
        pool += 26
    if any(c.isdigit() for c in pw):
        pool += 10
    if any(not c.isalnum() for c in pw):
        pool += len(SYMBOLS) + 6        # 符号池按常见可见符号规模估算
    bits = len(pw) * math.log2(pool) if pool > 1 else 0.0
    score = min(100, int(bits))
    if len(set(pw)) / max(len(pw), 1) < 0.6:
        score -= 10                     # 字符重复度过高
    if pool < 30:
        score -= 15                     # 字符池单一(如纯数字)
    if len(pw) < 8:
        score -= 10                     # 长度不足
    score = max(0, min(100, score))
    if score >= 80:
        label = "极强"
    elif score >= 60:
        label = "强"
    elif score >= 40:
        label = "中"
    else:
        label = "弱"
    return score, bits, label


def read_accounts(path, column=None, no_header=False):
    """从 CSV 读取账号列, 返回账号列表。编码自动尝试 UTF-8(-SIG) 再 GBK。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        sys.exit("错误: 读取 %s 失败: %s" % (path, exc))
    text = None
    for enc in ("utf-8-sig", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        sys.exit("错误: 无法解码 %s(请用 UTF-8 或 GBK 编码保存)" % path)
    rows = [r for r in csv.reader(text.splitlines()) if any(c.strip() for c in r)]
    if not rows:
        return []
    idx = 0
    if not no_header:
        cand = [c.strip().lower() for c in rows[0]]
        if column:
            if column.strip().lower() in cand:
                idx = cand.index(column.strip().lower())
                rows = rows[1:]
            else:
                sys.exit("错误: 首行表头中没有列 %r(现有列: %s)"
                         % (column, ", ".join(rows[0])))
        elif any(c in HEADER_WORDS for c in cand):
            rows = rows[1:]
    elif column:
        sys.exit("错误: --no-header 模式下无法按列名取列, 请去掉 --column 或 --no-header")
    return [r[idx].strip() for r in rows if len(r) > idx and r[idx].strip()]


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="为账号清单批量生成密码并导出 CSV(附强度评分列)。")
    src = parser.add_mutually_exclusive_group()
    src.add_argument("-i", "--input", help="账号清单 CSV(默认取第一列, --column 可指定)")
    src.add_argument("-n", "--count", type=int, help="自动生成账号数量(配合 --prefix)")
    parser.add_argument("--column", help="账号所在列名(需清单首行为表头)")
    parser.add_argument("--no-header", action="store_true", help="清单无表头, 每行都是数据")
    parser.add_argument("--prefix", default="user", help="自动编号账号前缀(默认 user)")
    parser.add_argument("-l", "--length", type=int, default=16, help="密码长度(默认 16, 范围 8-128)")
    parser.add_argument("-o", "--output", help="输出 CSV 路径(缺省打印到 stdout)")
    parser.add_argument("--allow-ambiguous", action="store_true", help="不剔除易混字符")
    args = parser.parse_args(argv)

    if args.count is not None and not 1 <= args.count <= 100000:
        parser.error("--count 取值范围 1-100000")
    if not 8 <= args.length <= 128:
        parser.error("--length 取值范围 8-128")

    if args.input:
        accounts = read_accounts(args.input, args.column, args.no_header)
        if not accounts:
            sys.exit("错误: 清单 %s 中没有读到任何账号" % args.input)
    else:
        n = args.count if args.count is not None else 10
        accounts = ["%s%03d" % (args.prefix, i) for i in range(1, n + 1)]

    out = None
    if args.output:
        out = open(args.output, "w", encoding="utf-8-sig", newline="")
    else:
        out = sys.stdout
    try:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["account", "password", "score", "strength", "length"])
        for account in accounts:
            pw = gen_password(args.length, args.allow_ambiguous)
            score, _bits, label = score_password(pw)
            writer.writerow([account, pw, score, label, len(pw)])
    finally:
        if args.output:
            out.close()
    if args.output:
        print("已生成 %d 条 -> %s" % (len(accounts), args.output), file=sys.stderr)
    return 0


if __name__ == "__main__":
    _utf8_stdio()
    sys.exit(main())
