#!/usr/bin/env python3
"""t2s-convert.py — 繁体转简体转换器。

基于内置单字与常用词表做繁体→简体转换（单字表由 s2t-convert.py 的
简→繁表镜像派生并补充）。重点处理「一繁对多简」的上下文判断：

  於/于  「於」默认转为「于」；但前一字为「姓」时保留「於」（姓氏），
         复姓「淳於」靠词表整体保留。
  餘/余  繁体「餘」（剩余义）一律转为「余」；原文中的「余」（第一人称、
         姓氏）本就是简体字形，不入映射表，自然原样保留。
  乾/干  「乾」默认转「干」（乾淨→干净、乾杯→干杯）；「乾坤」「乾隆」
         靠词表保留为「乾」。
  著/着  「著」默认转「着」（拿著→拿着）；「著作」「著名」「顯著」等
         靠词表保留为「著」。
  發/髮  两者都对应简体「发」；词表保证 頭髮→头发、發展→发展 各归其位。

示例命令：
  python t2s-convert.py --text "他們的頭髮很長，屋裡打掃得乾乾淨淨。"
  echo "從臺北出發，一隻貓在皇后大道看手錶。" | python t2s-convert.py
  python t2s-convert.py -i input.txt -o output.txt

说明：
  依赖同目录的 s2t-convert.py（复用其映射表与转换引擎）。
  输入优先级：--text > --input 文件 > stdin（管道）。
"""

import argparse
import importlib.util
import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parent / "s2t-convert.py"
_spec = importlib.util.spec_from_file_location("_s2t_core_t2s", _CORE)
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)

_pairs = _core._pairs
_worddict = _core._worddict

# ---------------------------------------------------------------------------
# 补充单字（s2t 表镜像之外的繁体字/异体字，均无歧义地对应唯一简体）
# ---------------------------------------------------------------------------
T2S_EXTRA_CHARS = _pairs("""
髮发 麵面 錶表 臺台 隻只 裏里 沖冲 籤签 誌志 彙汇 繫系 捲卷 捨舍 採采
穀谷 劃划 製制 曆历 遊游 鬍胡 鬚须 僱雇 複复 於于 餘余 乾干 幹干
準准 註注 徵征 黴霉 慾欲 籲吁 囉啰 儘尽 瀋沈 唸念 僞伪 讚赞 宮宫 丟丢
""")

# ---------------------------------------------------------------------------
# 词级例外：覆盖镜像词表，避免多义字被错误简化
# ---------------------------------------------------------------------------
T2S_OVERRIDES = _worddict("""
乾坤=乾坤
乾隆=乾隆
淳於=淳於
乾清=乾清
著作=著作
著名=著名
著稱=著稱
著述=著述
原著=原著
名著=名著
編著=編著
顯著=顯著
卓著=卓著
土著=土著
昭著=昭著
專著=專著
論著=論著
譯著=譯著
""")

# 港台地区词回转（繁体地区用词 -> 大陆简体用词；注意「資料」「影片」
# 这类简繁同形词不回转，避免把普通词义误改）
T2S_REGIONAL = _worddict("""
光碟=光盘
軟體=软件
硬體=硬件
網路=网络
網際網路=互联网
資訊=信息
滑鼠=鼠标
硬碟=硬盘
記憶體=内存
伺服器=服务器
晶片=芯片
程式碼=代码
程式=程序
的士=出租车
雪櫃=冰箱
電單車=摩托车
網誌=博客
短訊=短信
鐳射=激光
部落格=博客
列印=打印
印表機=打印机
螢幕=屏幕
""")


def _reverse_words(words: dict) -> dict:
    """由简→繁词表反推繁→简词表；同一繁体词若指向不同简体词则报错。"""
    rev = {}
    for k, v in words.items():
        old = rev.get(v)
        if old is not None and old != k:
            raise ValueError("繁→简词表冲突: %r -> %r / %r" % (v, old, k))
        rev[v] = k
    return rev


def _build():
    chars = {v: k for k, v in _core.CHARS.items()}
    chars.update(T2S_EXTRA_CHARS)
    words = _reverse_words(_core.WORDS)
    words.update(T2S_OVERRIDES)
    words.update(T2S_REGIONAL)
    return chars, words


def char_rule(ch: str, prev: str, nxt: str) -> str:
    """单字级上下文规则：处理「一繁对多简」的保留场景。"""
    if ch == "於":
        # 「姓於」：姓氏用法保留；其余（含句首连词「於是」）转为「于」
        if prev == "姓":
            return "於"
        return "于"
    if ch == "餘":
        # 繁体「餘」（剩余义）一律作「余」；原文「余」（第一人称/姓氏）
        # 是简体字形，不在映射表中，自动原样保留——即安全侧。
        return "余"
    return None


CHARS, WORDS = _build()


def convert(text: str) -> str:
    return _core.convert(text, words=WORDS, chars=CHARS, rule=char_rule)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _core.build_argparser(
        "繁体转简体转换器（处理「於/于」「餘/余」等一繁对多简的上下文判断）"
    ).parse_args(argv)
    _core.write_result(args, convert(_core.read_source(args)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
