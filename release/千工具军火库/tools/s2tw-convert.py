#!/usr/bin/env python3
"""s2tw-convert.py — 简体转台湾正体转换器。

先用内置简→繁引擎（s2t-convert.py）做基础繁化（含头发→頭髮、
干净→乾淨等词级消歧），再叠加台湾惯用地区词替换：
软件→軟體、信息→資訊、视频→影片、网络→網路、数据→資料、
出租车→計程車、地铁→捷運、鼠标→滑鼠、激光→雷射 等。
地区词在合并词表后优先级最高（同键覆盖、更长词优先匹配）。

示例命令：
  python s2tw-convert.py --text "这款软件免费，信息量大，视频清晰。"
  echo "用鼠标打开文件夹，数据存在服务器硬盘里。" | python s2tw-convert.py
  python s2tw-convert.py -i input.txt -o output.txt

说明：
  依赖同目录的 s2t-convert.py（复用映射表与转换引擎）。
  地区词只覆盖常见 IT 与生活词汇，未收录词按通用繁体处理。
"""

import importlib.util
import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parent / "s2t-convert.py"
_spec = importlib.util.spec_from_file_location("_s2t_core_s2tw", _CORE)
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)

# 台湾惯用与大陆用词对照（简→台湾正体；长词优先于其子词）
TW_WORDS = _core._worddict("""
# IT / 通用
软件=軟體
硬件=硬體
信息=資訊
音频=音訊
视频=影片
网络=網路
互联网=網際網路
网站=網站
服务器=伺服器
内存=記憶體
硬盘=硬碟
光盘=光碟
鼠标=滑鼠
屏幕=螢幕
打印机=印表機
打印=列印
大数据=大數據
数据库=資料庫
数据=資料
源代码=原始碼
代码=程式碼
程序=程式
操作系统=作業系統
文件夹=資料夾
文件=檔案
字体=字型
芯片=晶片
录像=錄影
# 生活 / 交通
出租车=計程車
摩托车=機車
自行车=腳踏車
公交车=公車
地铁=捷運
博客=部落格
在线=線上
短信=簡訊
人工智能=人工智慧
智能=智慧
激光=雷射
质量=品質
""")

WORDS_TW = dict(_core.WORDS)
WORDS_TW.update(TW_WORDS)


def convert(text: str) -> str:
    return _core.convert(text, words=WORDS_TW)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _core.build_argparser(
        "简体转台湾正体（繁化 + 台湾用词：软件→軟體、信息→資訊、视频→影片）"
    ).parse_args(argv)
    _core.write_result(args, convert(_core.read_source(args)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
