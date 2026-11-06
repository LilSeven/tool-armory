#!/usr/bin/env python3
"""人民币大写金额反解析器（大写文本 → 阿拉伯数字金额）。

用途：
    把人民币大写金额解析回数字（两位小数、十进制精确无浮点误差），
    支持财会规范写法与常见实际写法：
      * 标准写法：壹仟贰佰叁拾肆元伍角陆分 / 壹拾元整 / 负伍元伍角
      * 中间零位：壹仟零贰（1002）、壹佰万零伍仟元整、壹元零贰分（1.02）
      * 缺省单位：壹贰叁（123）、拾贰元（12）、一千二（1200）、
                  一万二（12000）、一亿二（1.2 亿）、一块五（1.50）
      * 省略“元”：肆角贰分（0.42）、贰分（0.02）、壹拾贰角（1.20，按 12 角折算）
      * 大小写与异体字混用：一百二十三元四角五分；贰/貳、陆/陸、万/萬、
                  圆/圓、毛（=角）、块（=元）；支持“人民币…整”等前后缀
    尾随缺省单位的数字按口语习惯推断：元后无零 → 角（壹元贰=1.20）；
    元后出现过“零” → 分（壹元零贰=1.02）。

示例命令：
    python rmb-parse.py --selftest
    python rmb-parse.py 壹仟贰佰叁拾肆元伍角陆分         # 1234.56
    python rmb-parse.py "壹佰万零伍仟元整" 肆角贰分       # 1005000.00 / 0.42
    python rmb-uppercase.py 1234.56 | python rmb-parse.py   # 往返校验（stdin）

退出码：0 成功；1 selftest 失败；2 文本无法解析。
"""

import argparse
import sys

_FW = str.maketrans("０１２３４５６７８９", "0123456789")

_DIGIT = {
    "零": 0, "〇": 0, "○": 0, "O": 0, "o": 0,
    "壹": 1, "一": 1,
    "贰": 2, "貳": 2, "二": 2, "两": 2, "兩": 2, "俩": 2,
    "叁": 3, "參": 3, "三": 3,
    "肆": 4, "四": 4,
    "伍": 5, "五": 5,
    "陆": 6, "陸": 6, "六": 6,
    "柒": 7, "七": 7, "漆": 7,
    "捌": 8, "八": 8,
    "玖": 9, "九": 9,
}
for _i, _c in enumerate("0123456789"):
    _DIGIT.setdefault(_c, _i)

_UNIT = {"拾": 10, "十": 10, "佰": 100, "百": 100, "仟": 1000, "千": 1000}
_MARK = {"万": 10 ** 4, "萬": 10 ** 4, "亿": 10 ** 8, "億": 10 ** 8}
_MARK2 = ("万亿", "萬億")            # 10^12
_YUAN = set("元圆圓块")
_JIAO = set("角毛")
_SKIP = set("整正人民币大寫写幣币，、（）()·．.")
# “缺省单位”时悬空数字的推断权重：紧跟某单位后省略了低一位单位
_NEXT_UNIT = {10: 1, 100: 10, 1000: 100,
              10 ** 4: 1000, 10 ** 8: 10 ** 7, 10 ** 12: 10 ** 11}
_MAX_YUAN = 10 ** 16


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _tokenize(s: str):
    tokens = []
    i, n = 0, len(s)
    started = False
    while i < n:
        c = s[i]
        if c.isspace() or c in _SKIP:
            i += 1
            continue
        if not started and c in "负負-":
            tokens.append(("neg", None))
            started = True
            i += 1
            continue
        if s.startswith("万亿", i) or s.startswith("萬億", i):
            tokens.append(("mark", 10 ** 12))
            started = True
            i += 2
            continue
        if c in _DIGIT:
            tokens.append(("digit", _DIGIT[c]))
        elif c in _UNIT:
            tokens.append(("unit", _UNIT[c]))
        elif c in _MARK:
            tokens.append(("mark", _MARK[c]))
        elif c in _YUAN:
            tokens.append(("yuan", None))
        elif c in _JIAO:
            tokens.append(("jiao", None))
        elif c == "分":
            tokens.append(("fen", None))
        else:
            raise ValueError(f"无法识别的字符 {c!r}（第 {i + 1} 个字符）")
        started = True
        i += 1
    return tokens


def parse_to_cents(text: str) -> int:
    """解析为大写金额，返回总分数（精确整数）；负金额返回负值。"""
    tokens = _tokenize(text.translate(_FW))
    if not tokens:
        raise ValueError(f"未识别到任何金额内容：{text!r}")
    negative = False
    if tokens[0][0] == "neg":
        negative = True
        tokens = tokens[1:]
    total = section = num = 0
    yuan = jiao = fen = None
    saw_yuan = saw_jiao = saw_fen = False
    last_w = None          # 最近一次出现的单位权重
    zero_flag = False      # 整数部分：自最近单位以来是否出现过“零”
    frac_zero = False      # 元/角之后是否出现过“零”

    def flush_dangling():
        # “缺省单位”的悬空数字：按最近单位的低一位并入；出现过零则按个位
        nonlocal num, section
        if num == 0:
            return
        w = 1 if (zero_flag or last_w is None) else _NEXT_UNIT.get(last_w, 1)
        section += num * w
        num = 0

    for kind, v in tokens:
        if kind == "digit":
            num = num * 10 + v
            if v == 0:
                if saw_yuan or saw_jiao:
                    frac_zero = True
                else:
                    zero_flag = True
        elif kind == "unit":
            if saw_yuan or saw_jiao:
                raise ValueError("“角/分”之后不应再出现位数单位")
            section += (num if num else 1) * v
            num, last_w, zero_flag = 0, v, False
        elif kind == "mark":
            if saw_yuan or saw_jiao:
                raise ValueError("“角/分”之后不应再出现万/亿")
            if num == 0 and section == 0 and total == 0:
                raise ValueError("“万/亿”之前缺少数字")
            if v == 10 ** 4:
                section = (section + num) * v
            else:
                # 亿/万亿：把当前“亿组”的值提到高位，已入 total 的万亿部分不动
                total += (section + num) * v
                section = 0
            num, last_w, zero_flag = 0, v, False
        elif kind == "yuan":
            if saw_yuan or saw_jiao or saw_fen:
                raise ValueError("“元”重复或位置错误")
            flush_dangling()
            yuan = total + section
            total = section = 0
            last_w, zero_flag = None, False
            saw_yuan = True
        elif kind == "jiao":
            if saw_fen or saw_jiao:
                raise ValueError("“角”重复或位于“分”之后")
            if saw_yuan:
                jiao = num
            else:
                flush_dangling()
                jiao = total + section
            num = total = section = 0
            saw_jiao = True
        elif kind == "fen":
            if saw_fen:
                raise ValueError("“分”重复")
            if saw_yuan or saw_jiao:
                fen = num
            else:
                flush_dangling()
                fen = total + section
            num = total = section = 0
            saw_fen = True

    if not (saw_yuan or saw_jiao or saw_fen):
        flush_dangling()
        yuan = total + section
    elif num:
        if saw_fen:
            raise ValueError("“分”之后不应再有数字")
        if saw_jiao:
            if num >= 10:
                raise ValueError("“角”后的缺省单位数字至多一位（表示分）")
            fen = num
        elif saw_yuan:
            if frac_zero:
                if num >= 10:
                    raise ValueError("“元零”后的缺省单位数字至多一位（表示分）")
                fen = num
            else:
                if num >= 100:
                    raise ValueError("“元”后的缺省单位数字至多两位")
                if num < 10:
                    jiao = num
                else:
                    jiao, fen = divmod(num, 10)

    cents = (yuan or 0) * 100 + (jiao or 0) * 10 + (fen or 0)
    if cents // 100 >= _MAX_YUAN:
        raise ValueError("金额超出可表示范围（整数部分需 < 10^16 元）")
    return -cents if negative else cents


def cents_to_str(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}{c // 100}.{c % 100:02d}"


def parse(text: str) -> str:
    return cents_to_str(parse_to_cents(text))


def selftest() -> int:
    cases = [
        ("壹仟贰佰叁拾肆元伍角陆分", "1234.56"),
        ("壹拾元整", "10.00"),
        ("壹佰万零伍仟元整", "1005000.00"),
        ("壹元零贰分", "1.02"),
        ("壹元零贰", "1.02"),
        ("肆角贰分", "0.42"),
        ("贰分", "0.02"),
        ("拾贰元", "12.00"),
        ("壹贰叁", "123.00"),
        ("壹亿零壹万元整", "100010000.00"),
        ("负伍元伍角", "-5.50"),
        ("一百二十三元四角五分", "123.45"),
        ("一千零一", "1001.00"),
        ("壹仟零贰", "1002.00"),
        ("一万二", "12000.00"),
        ("一千二", "1200.00"),
        ("一亿二", "120000000.00"),
        ("壹元贰角叁", "1.23"),
        ("壹元贰", "1.20"),
        ("一块五", "1.50"),
        ("壹拾贰万亿零壹元整", "12000000000001.00"),
        ("人民币壹佰元整", "100.00"),
        ("壹佰零伍元整", "105.00"),
        ("壹拾贰角", "1.20"),
        ("玖仟玖佰玖拾玖万亿玖仟玖佰玖拾玖亿玖仟玖佰玖拾玖万玖仟玖佰玖拾玖元玖角玖分",
         "9999999999999999.99"),
        ("壹万贰仟亿", "1200000000000.00"),
    ]
    ok = True
    for text, want in cases:
        try:
            got = parse(text)
        except ValueError as exc:
            ok = ok and False
            print(f"[FAIL] {text} -> 异常：{exc}")
            continue
        passed = got == want
        ok = ok and passed
        print(f"[{'PASS' if passed else 'FAIL'}] {text} -> {got}"
              + ("" if passed else f"（期望 {want}）"))
    for bad in ("壹角贰角", "壹元贰角叁分肆", "万", "hello", ""):
        try:
            parse(bad)
            ok = ok and False
            print(f"[FAIL] 非法输入被拒绝：{bad!r}")
        except ValueError:
            print(f"[PASS] 非法输入被拒绝：{bad!r}")
    print("selftest:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


def main(argv=None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(description="人民币大写金额反解析器")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("texts", nargs="*", metavar="大写文本",
                    help="一段或多段大写金额；缺省时从 stdin 逐行读取")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    texts = args.texts
    if not texts:
        if sys.stdin.isatty():
            ap.error("请提供至少一段大写文本（或使用 --selftest / 通过 stdin 传入）")
        data = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        texts = [line.strip() for line in data.splitlines() if line.strip()]
    rc = 0
    for text in texts:
        try:
            print(parse(text))
        except ValueError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            rc = 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
