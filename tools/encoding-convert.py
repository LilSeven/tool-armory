#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文编码互转（encoding-convert）

自动检测 GBK / GB18030 / Big5 / UTF-8（含 UTF-8/16/32 BOM），并转换到
目标编码，解决中文文本乱码打开问题。检测策略：先识别 BOM，再严格校验
UTF-8，最后在 Big5 / GB18030（GBK 超集）之间按启发式评分——「常用汉字
命中率 − 私有区字符（U+E000–U+F8FF）惩罚」——挑选最可能的编码。文件
检测本质上有歧义，--report 会给出评分与提示；必要时用 --from 强制指定。

用法：
    python -I encoding-convert.py <文件> --report               # 只检测
    python -I encoding-convert.py <文件> -o out.txt             # 转 UTF-8
    python -I encoding-convert.py <文件> -o out.txt --to gbk
    python -I encoding-convert.py <文件> --from big5 -o out.txt
    python -I encoding-convert.py <文件> --in-place             # 原地转 UTF-8
    python -I encoding-convert.py --self-test

选项：
    -o, --output FILE   转换结果写入文件（缺省打印到标准输出）
    --to ENC            目标编码（默认 utf-8，可用 utf-8-sig/gbk/big5/gb18030）
    --from ENC          强制指定源编码（跳过自动检测）
    --report            只报告检测结果，不转换
    --in-place          原地转换（覆盖原文件，请先备份）
    --errors MODE       编码错误处理 strict|replace|ignore（默认 strict）
    --self-test         运行内置自测并退出

示例：
    python -I encoding-convert.py 乱码.txt --report
    python -I encoding-convert.py 乱码.txt -o 修复.txt
    python -I encoding-convert.py 修复.txt --to gbk -o 给老系统.txt
"""

import argparse
import codecs
import os
import shutil
import sys
import tempfile

CANDIDATES = ("big5", "gb18030")   # GBK/GB2312 由 gb18030 超集覆盖

# 高频简体汉字 + 若干高频繁体字，用于区分 Big5 与 GB 系误判
COMMON_CHARS = set(
    "的一是了我不人在他有这个上们来到时大地为子中你说生国年着就那和要她出也得里后自以会家"
    "可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第样道想作种开美总从无情"
    "己面最女但现前些所同日手又行意动方期它头经长儿回位分爱老因很给名法间斯知世什两次使身"
    "者被高已亲其进此话常与活正感见问力学气和们時來說學國會後這裡請辦公廳務員認證碼檔案"
)


def score_text(text):
    """返回 (评分, 私有区字符数)；评分 = 常用字命中率 − 私有区惩罚。"""
    cjk = common = pua = 0
    for ch in text:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF:
            cjk += 1
            if ch in COMMON_CHARS:
                common += 1
        elif 0xE000 <= o <= 0xF8FF:
            pua += 1
    if cjk == 0:
        return ((1.0, 0) if pua == 0 else (-1.0, pua))
    return (common / cjk - pua / (cjk + pua), pua)


def detect_encoding(data):
    """返回 (编码名, 信息字典)；编码名为 None 表示所有候选都失败。"""
    for bom, enc in (
        (codecs.BOM_UTF32_LE, "utf-32-le"),
        (codecs.BOM_UTF32_BE, "utf-32-be"),
        (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"),
        (codecs.BOM_UTF8, "utf-8-sig"),
    ):
        if data.startswith(bom):
            return enc, {"method": "BOM 识别", "score": None, "pua": None, "note": ""}
    try:
        data.decode("utf-8")
        return "utf-8", {"method": "严格 UTF-8 校验通过", "score": None,
                         "pua": None, "note": ""}
    except UnicodeDecodeError:
        pass
    scored = []
    for enc in CANDIDATES:
        try:
            text = data.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
        sc, pua = score_text(text)
        scored.append((sc, pua, enc, text))
    if not scored:
        return None, {"method": "所有候选编码均无法解码", "score": None,
                      "pua": None, "note": "可尝试 --from gbk/gb2312/utf-16 等手动指定"}
    scored.sort(key=lambda t: t[0], reverse=True)
    best = scored[0]
    note = ""
    if len(scored) > 1 and best[0] - scored[1][0] < 0.05:
        note = "（与 {} 评分接近，建议人工确认或 --from 强制指定）".format(scored[1][2])
    return best[2], {"method": "启发式评分", "score": best[0],
                     "pua": best[1], "note": note}


def convert_bytes(data, source=None, target="utf-8", errors="strict"):
    """按检测/指定编码解码后转目标编码；返回 (目标字节串, 源编码, 信息)。"""
    if source:
        enc, info = source, {"method": "手动指定", "score": None, "pua": None, "note": ""}
    else:
        enc, info = detect_encoding(data)
    if enc is None:
        raise UnicodeDecodeError(info["method"], b"", 0, 0, info["note"])
    text = data.decode(enc)
    return text.encode(target, errors=errors), enc, info


def self_test():
    tmp = tempfile.mkdtemp(prefix="encconv_selftest_")
    try:
        utf8_text = "你好世界，中文编码测试。Encoding check."
        big5_text = "你好世界測試檔案讀寫"
        p_u8 = os.path.join(tmp, "u8.txt")
        p_sig = os.path.join(tmp, "sig.txt")
        p_gbk = os.path.join(tmp, "gbk.txt")
        p_big5 = os.path.join(tmp, "big5.txt")
        with open(p_u8, "wb") as f:
            f.write(utf8_text.encode("utf-8"))
        with open(p_sig, "wb") as f:
            f.write(utf8_text.encode("utf-8-sig"))
        with open(p_gbk, "wb") as f:
            f.write(utf8_text.encode("gbk"))
        with open(p_big5, "wb") as f:
            f.write(big5_text.encode("big5"))
        # 检测
        assert detect_encoding(open(p_sig, "rb").read())[0] == "utf-8-sig"
        assert detect_encoding(open(p_u8, "rb").read())[0] == "utf-8"
        assert detect_encoding(open(p_gbk, "rb").read())[0] in ("gb18030", "gbk")
        assert detect_encoding(open(p_big5, "rb").read())[0] == "big5"
        # GBK -> UTF-8
        out1, enc1, _ = convert_bytes(open(p_gbk, "rb").read(), target="utf-8")
        assert enc1 in ("gb18030", "gbk")
        assert out1.decode("utf-8") == utf8_text
        # Big5 -> UTF-8
        out2, enc2, _ = convert_bytes(open(p_big5, "rb").read(), target="utf-8")
        assert enc2 == "big5"
        assert out2.decode("utf-8") == big5_text
        # UTF-8 -> GBK 再读回
        out3, _, _ = convert_bytes(open(p_u8, "rb").read(), source="utf-8", target="gbk")
        assert out3.decode("gbk") == utf8_text
        print("encoding-convert 自测通过：BOM/UTF-8/GBK(GB18030)/Big5 检测与互转 OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="自动检测 GBK/GB18030/Big5/UTF-8 并转换编码")
    parser.add_argument("input", nargs="?", help="输入文件")
    parser.add_argument("-o", "--output", help="输出文件（缺省打印到标准输出）")
    parser.add_argument("--to", default="utf-8", help="目标编码（默认 utf-8）")
    parser.add_argument("--from", dest="from_enc", help="强制指定源编码")
    parser.add_argument("--report", action="store_true", help="只报告检测结果")
    parser.add_argument("--in-place", action="store_true", help="原地转换（覆盖原文件）")
    parser.add_argument("--errors", default="strict",
                        choices=("strict", "replace", "ignore"),
                        help="编码错误处理方式（默认 strict）")
    parser.add_argument("--self-test", action="store_true", help="运行内置自测后退出")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.input:
        parser.error("请提供输入文件")
        return 2
    try:
        codecs.lookup(args.to)
        if args.from_enc:
            codecs.lookup(args.from_enc)
    except LookupError as e:
        print("未知编码: {}".format(e), file=sys.stderr)
        return 1
    try:
        with open(args.input, "rb") as f:
            data = f.read()
    except OSError as e:
        print("读取失败: {}".format(e), file=sys.stderr)
        return 1

    try:
        out_bytes, enc, info = convert_bytes(
            data, source=args.from_enc, target=args.to, errors=args.errors)
    except UnicodeDecodeError:
        print("无法解码：{}".format(info.get("note") or "所有候选编码均失败"),
              file=sys.stderr)
        return 1
    except UnicodeEncodeError as e:
        print("编码到 {} 失败: {}（可加 --errors replace 跳过）".format(args.to, e),
              file=sys.stderr)
        return 1

    score = ("{:.1%}".format(info["score"]) if isinstance(info.get("score"), float)
             else "-")
    line = "源编码: {}（{}，常用字评分 {}，私有区 {} 字符）{} -> 目标: {}".format(
        enc, info["method"], score,
        info["pua"] if info.get("pua") is not None else 0,
        info.get("note", ""), args.to)

    if args.report:
        try:
            text = data.decode(enc)
            preview = ascii(text[:24])
        except Exception:
            preview = "-"
        print(line)
        print("预览: {}".format(preview))
        return 0

    if args.in_place:
        dst = args.input
    elif args.output:
        dst = args.output
    else:
        dst = None
    if dst is not None:
        try:
            with open(dst, "wb") as f:
                f.write(out_bytes)
        except OSError as e:
            print("写入失败: {}".format(e), file=sys.stderr)
            return 1
        print(line)
        print("已写入: {}".format(dst))
    else:
        print(line, file=sys.stderr)
        sys.stdout.buffer.write(out_bytes)
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
