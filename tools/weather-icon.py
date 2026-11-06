#!/usr/bin/env python3
"""天气字符画 (weather-icon) -- 按参数画出晴/雨/雪/雷的 ASCII 天气图标。

示例命令:
    python weather-icon.py sun
    python weather-icon.py rain --size large
    python weather-icon.py 雪            # 支持中文别名: 晴/雨/雪/雷
    python weather-icon.py --list

说明:
    * 条件: sun(晴) / rain(雨) / snow(雪) / thunder(雷),
      兼容英文别名 sunny / rainy / snowy / storm。
    * --size small|large, 默认 small; 未知条件退出码 2。
    * 单文件, 只依赖 Python 标准库; 输出强制 UTF-8。
"""

from __future__ import annotations

import argparse
import sys

ICONS: dict = {
    "sun": {
        "small": (
            "   \\ | /",
            "    .-.",
            " --(   )--",
            "    `-'",
            "   / | \\",
        ),
        "large": (
            "       \\ | /",
            "        .-.",
            "   -- -(   )- --",
            "        `-'",
            "       / | \\",
        ),
    },
    "rain": {
        "small": (
            "   .---.",
            "  ( ~~~ )",
            "   `---'",
            "   `  `  ",
            "  `  `  `",
        ),
        "large": (
            "     .------.",
            "    (  ~~~~  )",
            "     `------'",
            "     `   `   `",
            "    `   `   `",
            "     `   `   `",
            "    `   `   `",
        ),
    },
    "snow": {
        "small": (
            "   .---.",
            "  ( ~~~ )",
            "   `---'",
            "   *  *  ",
            "  *  *  *",
        ),
        "large": (
            "     .------.",
            "    (  ~~~~  )",
            "     `------'",
            "     *   *   *",
            "    *   *   *",
            "     *   *   *",
            "    *   *   *",
        ),
    },
    "thunder": {
        "small": (
            "   .---.",
            "  ( ~~~ )",
            "   `---'",
            "     //",
            "    //",
            "   //",
            " __//",
            "/___/",
        ),
        "large": (
            "     .------.",
            "    (  ~~~~  )",
            "     `------'",
            "         //",
            "        //",
            "       //",
            "    __//",
            "   /___/",
        ),
    },
}

ALIASES = {
    "sunny": "sun", "晴": "sun", "晴天": "sun", "太阳": "sun",
    "rainy": "rain", "雨": "rain", "下雨": "rain",
    "snowy": "snow", "雪": "snow", "下雪": "snow",
    "storm": "thunder", "雷": "thunder", "雷雨": "thunder",
    "打雷": "thunder", "thunderstorm": "thunder",
}


def force_utf8() -> None:
    """Windows 管道/Git Bash 下 stdout 默认是 ANSI 代码页 (如 gbk), 统一改成 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(
        prog="weather-icon.py",
        description="按参数画出晴/雨/雪/雷的 ASCII 天气图标",
    )
    parser.add_argument("condition", nargs="?", help="sun/晴 rain/雨 snow/雪 thunder/雷")
    parser.add_argument("--size", default="small", choices=("small", "large"), help="图标尺寸, 默认 small")
    parser.add_argument("--list", action="store_true", help="列出支持的条件后退出")
    args = parser.parse_args(argv)

    if args.list:
        print("支持的条件:")
        for key in sorted(ICONS):
            nick = " ".join(a for a, v in ALIASES.items() if v == key) or "-"
            print(f"  {key:<8} 别名: {nick}")
        return 0

    raw = (args.condition or "").strip().lower()
    key = ALIASES.get(raw, raw)
    if key not in ICONS:
        parser.error(f"未知天气条件: {args.condition!r} (可用: {', '.join(sorted(ICONS))}, 或 --list 查看)")

    for line in ICONS[key][args.size]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
