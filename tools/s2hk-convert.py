#!/usr/bin/env python3
"""s2hk-convert.py — 简体转香港繁体转换器。

先用内置简→繁引擎（s2t-convert.py）做基础繁化（含头发→頭髮、
干净→乾淨等词级消歧），再叠加香港惯用用词替换：
出租车→的士、光盘→光碟、软件→軟件、网络→網絡、数据→數據、
冰箱→雪櫃、空调→冷氣、自行车→單車、摩托车→電單車、
公交车→巴士、在线→網上、短信→短訊、博客→網誌、激光→鐳射 等。
地区词在合并词表后优先级最高（同键覆盖、更长词优先匹配）。

示例命令：
  python s2hk-convert.py --text "我坐出租车去买了一张光盘。"
  echo "冰箱和空调都是新的，他用手机上网看视频。" | python s2hk-convert.py
  python s2hk-convert.py -i input.txt -o output.txt

说明：
  依赖同目录的 s2t-convert.py（复用映射表与转换引擎）。
  港式用词只覆盖常见词汇，未收录词按通用繁体处理。
"""

import importlib.util
import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parent / "s2t-convert.py"
_spec = importlib.util.spec_from_file_location("_s2t_core_s2hk", _CORE)
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)

# 香港惯用与大陆用词对照（简→香港繁体；长词优先于其子词）
HK_WORDS = _core._worddict("""
# 交通
出租车=的士
摩托车=電單車
自行车=單車
公交车=巴士
# 生活
冰箱=雪櫃
空调=冷氣
光盘=光碟
软件=軟件
信息=資訊
视频=影片
音频=音訊
博客=網誌
在线=網上
短信=短訊
激光=鐳射
# IT
网络=網絡
服务器=伺服器
内存=記憶體
硬盘=硬碟
鼠标=滑鼠
屏幕=螢幕
大数据=大數據
数据库=數據庫
数据=數據
源代码=原始碼
代码=程式碼
程序=程式
文件夹=資料夾
文件=檔案
芯片=晶片
""")

WORDS_HK = dict(_core.WORDS)
WORDS_HK.update(HK_WORDS)


def convert(text: str) -> str:
    return _core.convert(text, words=WORDS_HK)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _core.build_argparser(
        "简体转香港繁体（繁化 + 港式用词：出租车→的士、光盘→光碟、冰箱→雪櫃）"
    ).parse_args(argv)
    _core.write_result(args, convert(_core.read_source(args)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
