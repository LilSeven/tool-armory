#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""日志脱敏 — 用正则替换日志中的手机号、邮箱、身份证号、IPv4 等敏感字段。

逐行扫描输入(文件或 stdin), 把命中的敏感片段替换成打码文本后输出,
适合在把日志贴到 issue / 群里之前快速脱敏。仅依赖 Python 标准库。

用法:
  python log-anonymize.py access.log                     # 脱敏结果打到 stdout
  python log-anonymize.py access.log -o clean.log        # 结果写入文件
  python log-anonymize.py app.log --no-ipv4              # 关闭某一类规则
  python log-anonymize.py app.log --rule '工号(\d{4})\d{2}=工号\1**' --stats
  cat app.log | python log-anonymize.py > clean.log      # 从 stdin 读

默认规则(按顺序应用, 先长后短, 避免相互误伤):
  idcard  18 位身份证(末位可为 X)   -> 1101**********4512   保留前4后4
  phone   大陆手机号 1[3-9]\d{9}    -> 138****5678          保留前3后4
  email   邮箱                      -> z***@example.com     保留首字符与域名
  ipv4    IPv4 地址                 -> 10.20.*.*            保留前两段
选项:
  --no-phone / --no-email / --no-idcard / --no-ipv4  逐类关闭规则
  --rule REGEX=REPL  追加自定义规则: 首个 = 右侧为替换模板, 支持 \1 反向引用, 可重复
  --stats            结束时在 stderr 汇报各类替换次数
输入输出均按 UTF-8 处理(无法解码的字节以占位符替代, 不中断)。
退出码: 0 成功; 2 参数或文件错误。
"""

import argparse
import os
import re
import sys

IDCARD_RE = r"(?<!\d)\d{17}[\dXx](?!\d)"
PHONE_RE = r"(?<!\d)1[3-9]\d{9}(?!\d)"
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
_IPV4_OCT = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
IPV4_RE = r"(?<!\d)(?:%s\.){3}%s(?!\d)" % (_IPV4_OCT, _IPV4_OCT)


def _force_utf8():
    """Windows 控制台/管道下强制 UTF-8, 避免中文输出乱码或编码报错。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def mask_idcard(m):
    s = m.group(0)
    return s[:4] + "*" * 10 + s[-4:]


def mask_phone(m):
    s = m.group(0)
    return s[:3] + "****" + s[-4:]


def mask_email(m):
    addr = m.group(0)
    local, sep, domain = addr.rpartition("@")
    if not sep:
        return "*" * len(addr)
    return (local[:1] if local else "") + "***" + sep + domain


def mask_ipv4(m):
    a, b = m.group(0).split(".")[:2]
    return "%s.%s.*.*" % (a, b)


def build_rules(args):
    """返回 [(规则名, 编译后的正则, 替换函数或替换模板), ...], 顺序即应用顺序。"""
    rules = []
    if not args.no_idcard:
        rules.append(("idcard", re.compile(IDCARD_RE), mask_idcard))
    if not args.no_phone:
        rules.append(("phone", re.compile(PHONE_RE), mask_phone))
    if not args.no_email:
        rules.append(("email", re.compile(EMAIL_RE), mask_email))
    if not args.no_ipv4:
        rules.append(("ipv4", re.compile(IPV4_RE), mask_ipv4))
    for spec in args.rule or []:
        pat, sep, repl = spec.partition("=")
        if not sep or not pat:
            raise ValueError("自定义规则需形如 REGEX=REPL, 实际得到: %r" % spec)
        rules.append(("custom", re.compile(pat), repl))
    return rules


def main(argv=None):
    _force_utf8()
    p = argparse.ArgumentParser(
        prog="log-anonymize.py",
        description="日志脱敏: 正则打码手机号/邮箱/身份证号/IPv4 等敏感字段")
    p.add_argument("input", nargs="?", default="-",
                   help="输入日志文件, 缺省或 '-' 表示 stdin")
    p.add_argument("-o", "--output", help="输出文件, 缺省为 stdout")
    p.add_argument("--no-phone", action="store_true", help="关闭手机号规则")
    p.add_argument("--no-email", action="store_true", help="关闭邮箱规则")
    p.add_argument("--no-idcard", action="store_true", help="关闭身份证规则")
    p.add_argument("--no-ipv4", action="store_true", help="关闭 IPv4 规则")
    p.add_argument("--rule", action="append", default=[], metavar="REGEX=REPL",
                   help="追加自定义规则, 可重复")
    p.add_argument("--stats", action="store_true", help="结束时在 stderr 汇报替换次数")
    args = p.parse_args(argv)

    try:
        rules = build_rules(args)
    except (ValueError, re.error) as e:
        print("[log-anonymize] 参数错误: %s" % e, file=sys.stderr)
        return 2

    try:
        if args.input == "-":
            fin = sys.stdin
        else:
            fin = open(args.input, "r", encoding="utf-8", errors="replace", newline="")
    except OSError as e:
        print("[log-anonymize] 无法打开输入文件: %s" % e, file=sys.stderr)
        return 2

    counts = {}
    fout = None
    try:
        if args.output is None:
            fout = sys.stdout
        else:
            fout = open(args.output, "w", encoding="utf-8", newline="")
        with fin:
            for line in fin:
                for name, rx, rep in rules:
                    line, n = rx.subn(rep, line)
                    if n:
                        counts[name] = counts.get(name, 0) + n
                fout.write(line)
    except BrokenPipeError:
        try:  # 下游提前关闭管道(如 | head)时静默退出
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except OSError:
            pass
        return 0
    except (OSError, re.error) as e:
        print("[log-anonymize] 读写失败: %s" % e, file=sys.stderr)
        return 2
    finally:
        if fout is not None and fout is not sys.stdout:
            fout.close()

    if args.stats:
        if counts:
            detail = ", ".join("%s=%d" % (k, counts[k]) for k in sorted(counts))
            print("[log-anonymize] 替换统计: %s, 合计=%d"
                  % (detail, sum(counts.values())), file=sys.stderr)
        else:
            print("[log-anonymize] 未命中任何敏感字段", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
