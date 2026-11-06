#!/usr/bin/env python3
"""敏感信息脱敏(pii-mask)

用正则识别文本中的手机号、18 位身份证号、邮箱、银行卡号(13-19 位数字,
Luhn 校验)并部分打码。

打码规则:
  手机号   保留前 3 后 4:  138****5678
  身份证   保留前 4 后 2:  1101**********3X
  邮箱     用户名保留首字符与 @ 后域名:  a***@example.com
  银行卡   保留后 4 位:  ************1234

用法:
  python pii-mask.py <输入文件> [--types phone,id,email,bank] [-o 输出文件]
  cat in.txt | python pii-mask.py

示例:
  python pii-mask.py users.txt -o masked.txt
  python pii-mask.py users.txt --types phone,email
"""
import argparse
import re
import sys

# Windows 控制台/管道默认 GBK,强制 UTF-8
for _s in (sys.stdout, sys.stderr, sys.stdin):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", newline="")

RE_PHONE = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')
RE_ID = re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)')
RE_EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
RE_BANK = re.compile(r'(?<!\d)\d{13,19}(?!\d)')


def _luhn_ok(num):
    s = 0
    for i, d in enumerate(reversed(num)):
        d = int(d)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return s % 10 == 0


def _mask_phone(m):
    n = m.group()
    return n[:3] + '*' * 4 + n[7:]


def _mask_id(m):
    n = m.group()
    return n[:4] + '*' * 12 + n[16:]


def _mask_email(m):
    e = m.group()
    user, _, domain = e.partition('@')
    if not user:
        return e
    return user[0] + '***@' + domain


def _mask_bank(m):
    n = m.group()
    # 身份证也是 18 位数字——先被 ID 处理;此处只处理通过 Luhn 的纯数字
    if _luhn_ok(n):
        return '*' * (len(n) - 4) + n[-4:]
    return n


def process(text, types):
    active = set(t.strip() for t in types.split(',') if t.strip())
    if 'email' in active:
        text = RE_EMAIL.sub(_mask_email, text)
    if 'id' in active:
        text = RE_ID.sub(_mask_id, text)
    if 'phone' in active:
        text = RE_PHONE.sub(_mask_phone, text)
    if 'bank' in active:
        text = RE_BANK.sub(_mask_bank, text)
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description="PII 脱敏工具")
    ap.add_argument("input", nargs="?", help="输入文件,缺省读 stdin")
    ap.add_argument("--types", default="phone,id,email,bank",
                    help="逗号分隔: phone,id,email,bank")
    ap.add_argument("-o", "--output", help="输出文件,缺省 stdout")
    args = ap.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = process(text, args.types)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(result)
        print("已写入: %s" % args.output, file=sys.stderr)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
