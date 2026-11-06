#!/usr/bin/env python3
"""Unicode 归一化转换 —— 对文件正文做 NFC/NFD/NFKC/NFKD 归一化。

与文件名归一化工具不同，本工具处理文件内容（正文文本）：
  NFC  组合等价，输出预组合字符（如 é 单码点）
  NFD  组合等价，输出分解字符（如 e + 组合变音符）
  NFKC 兼容等价 + 预组合（如 ﬁ → fi，全角→半角）
  NFKD 兼容等价 + 分解

用法：
  python nfc-nfd-convert.py NFC -i in.txt -o out.txt
  python nfc-nfd-convert.py NFKC -i in.txt            # 输出到 stdout
  python nfc-nfd-convert.py NFC --check -i in.txt     # 只检测是否已归一化
  echo "café" | python nfc-nfd-convert.py NFD         # stdin/stdout 流式

示例命令：
  python nfc-nfd-convert.py NFC -i nfd-sample.txt -o nfd-sample-nfc.txt
  python nfc-nfd-convert.py NFC --check -i nfd-sample.txt

位置参数：
  FORM              NFC | NFD | NFKC | NFKD（必填；--check 模式同样需要）
选项：
  -i, --input PATH    输入文件（默认 utf-8）；缺省读 stdin
  -o, --output PATH   输出文件；缺省写 stdout（utf-8）
  --encoding ENC      读写字符集（默认 utf-8）
  --errors MODE       读取错误处理（默认 replace）
  --check             不做转换，报告文件是否已是 FORM（退出码：0=是，1=否）
"""

import argparse
import sys
import unicodedata

FORMS = ("NFC", "NFD", "NFKC", "NFKD")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="nfc-nfd-convert",
        description="对文本文件正文做 Unicode NFC/NFD/NFKC/NFKD 归一化")
    p.add_argument("form", nargs="?", default=None,
                   help="归一化形式: NFC/NFD/NFKC/NFKD")
    p.add_argument("-i", "--input", help="输入文件，缺省读 stdin")
    p.add_argument("-o", "--output", help="输出文件，缺省写 stdout")
    p.add_argument("--encoding", default="utf-8", metavar="ENC")
    p.add_argument("--errors", default="replace",
                   choices=["strict", "replace", "ignore"])
    p.add_argument("--check", action="store_true",
                   help="只检测是否已归一化（退出码 0=已归一化，1=未归一化）")
    a = p.parse_args(argv)

    if a.check:
        if a.form is None:
            p.error("--check 需要指定 FORM")
        form = a.form.upper()
        if form not in FORMS:
            p.error(f"无效的归一化形式: {a.form}")
    else:
        if a.form is None:
            p.error("缺少位置参数 FORM（或使用 --check）")
        form = a.form.upper()
        if form not in FORMS:
            p.error(f"无效的归一化形式: {a.form}（可选 {'/'.join(FORMS)}）")

    if a.input is None:
        data = sys.stdin.buffer.read()
    else:
        with open(a.input, "rb") as f:
            data = f.read()
    text = data.decode(a.encoding, a.errors)

    if a.check:
        is_norm = unicodedata.is_normalized(form, text)
        normalized = unicodedata.normalize(form, text)
        label = "已" if is_norm else "未"
        sys.stdout.buffer.write(
            f"[{label}] {a.input or '<stdin>'}: 归一化形式 {form}, "
            f"整串长度 {len(text)} → {len(normalized)} 字符"
            f"（长度相同不代表已归一化，以[已/未]为准）\n".encode("utf-8"))
        return 0 if is_norm else 1

    out = unicodedata.normalize(form, text)
    payload = out.encode("utf-8" if a.output is None else a.encoding, a.errors)
    if a.output is None:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    else:
        with open(a.output, "wb") as f:
            f.write(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
