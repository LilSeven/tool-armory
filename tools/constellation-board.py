#!/usr/bin/env python3
"""星座连线 —— 在终端打印十二星座的星点连线图。

星图为手工绘制的示意坐标（非精确星表）：
  @ 亮星   * 一般恒星   . 连线
图下附主要恒星的中文名。支持中文名（可只写前几个字，如“天蝎”）、
俗称（处女/射手/水瓶）或英文名（不分大小写）查询。

示例命令:
  python constellation-board.py              # 列出十二星座与日期
  python constellation-board.py 天蝎         # 查询天蝎座
  python constellation-board.py 白羊 金牛    # 一次查询多个
  python constellation-board.py Scorpio      # 英文名查询
  python constellation-board.py --all        # 依次打印全部十二张星图

退出码: 0 成功；1 有查询无结果。
"""
import argparse
import sys

W, H = 40, 13  # 画布宽高（字符数）

# 每颗星: (x, y, 拜耳字母, 中文名, 是否亮星)
CONSTELLATIONS = [
    dict(name="白羊座", en="Aries", dates="3/21 - 4/19",
         stars=[(4, 9, "γ", "", 0), (11, 6, "β", "", 0),
                (18, 3, "α", "娄宿三", 0), (26, 2, "41", "", 0),
                (31, 6, "δ", "", 0)],
         edges=[(0, 1), (1, 2), (2, 3), (3, 4)]),
    dict(name="金牛座", en="Taurus", dates="4/20 - 5/20",
         stars=[(20, 8, "α", "毕宿五", 1), (18, 7, "γ", "", 0),
                (16, 5, "δ", "", 0), (14, 4, "ε", "", 0),
                (10, 2, "ζ", "天关", 0), (22, 7, "θ", "", 0),
                (25, 5, "", "", 0), (29, 2, "β", "五车五", 0)],
         edges=[(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7)]),
    dict(name="双子座", en="Gemini", dates="5/21 - 6/21",
         stars=[(14, 2, "α", "北河二", 0), (14, 5, "δ", "", 0),
                (13, 8, "", "", 0), (12, 11, "", "", 0),
                (22, 3, "β", "北河三", 1), (22, 6, "", "", 0),
                (23, 9, "", "", 0), (25, 11, "", "", 0)],
         edges=[(0, 1), (1, 2), (2, 3), (4, 5), (5, 6), (6, 7), (1, 5), (3, 7)]),
    dict(name="巨蟹座", en="Cancer", dates="6/22 - 7/22",
         stars=[(13, 2, "ι", "", 0), (19, 5, "γ", "", 0),
                (12, 9, "δ", "", 0), (26, 9, "β", "", 0),
                (26, 3, "α", "", 0)],
         edges=[(0, 1), (1, 2), (1, 3), (1, 4)]),
    dict(name="狮子座", en="Leo", dates="7/23 - 8/22",
         stars=[(12, 9, "α", "轩辕十四", 1), (11, 6, "η", "", 0),
                (13, 4, "γ", "轩辕十二", 0), (11, 2, "ζ", "", 0),
                (14, 1, "μ", "", 0), (17, 2, "ε", "", 0),
                (22, 6, "δ", "", 0), (29, 7, "β", "五帝座一", 0),
                (21, 9, "θ", "", 0)],
         edges=[(0, 1), (1, 2), (2, 3), (3, 4), (4, 5),
                (1, 6), (6, 7), (7, 8), (8, 0)]),
    dict(name="室女座", en="Virgo", alias=("处女座",), dates="8/23 - 9/22",
         stars=[(15, 11, "α", "角宿一", 1), (13, 8, "γ", "东上相", 0),
                (9, 6, "η", "左执法", 0), (12, 4, "β", "右执法", 0),
                (17, 6, "ζ", "", 0), (21, 4, "δ", "", 0),
                (25, 2, "ε", "东次相", 0)],
         edges=[(0, 1), (1, 2), (1, 3), (1, 4), (4, 5), (5, 6)]),
    dict(name="天秤座", en="Libra", dates="9/23 - 10/23",
         stars=[(7, 2, "β", "", 0), (26, 3, "υ", "", 0),
                (10, 9, "α", "氐宿一", 0), (24, 10, "γ", "", 0)],
         edges=[(0, 1), (0, 2), (1, 3), (2, 3)]),
    dict(name="天蝎座", en="Scorpius (Scorpio)", dates="10/24 - 11/22",
         stars=[(6, 2, "β", "", 0), (9, 1, "δ", "", 0), (12, 2, "π", "", 0),
                (10, 5, "α", "心宿二", 1), (13, 7, "τ", "", 0),
                (16, 9, "ε", "", 0), (20, 10, "μ", "", 0),
                (24, 11, "ζ", "", 0), (28, 11, "η", "", 0),
                (31, 10, "θ", "", 0), (34, 8, "ι", "", 0),
                (35, 5, "κ", "", 0), (36, 2, "λ", "尾宿八", 0)],
         edges=[(0, 1), (1, 2), (0, 3), (1, 3), (3, 4), (4, 5), (5, 6), (6, 7),
                (7, 8), (8, 9), (9, 10), (10, 11), (11, 12)]),
    dict(name="人马座", en="Sagittarius", alias=("射手座",), dates="11/23 - 12/21",
         stars=[(7, 5, "γ", "", 0), (8, 9, "δ", "", 0), (12, 10, "ε", "", 0),
                (18, 10, "η", "", 0), (23, 9, "ζ", "", 0), (25, 5, "τ", "", 0),
                (16, 4, "φ", "", 0), (27, 7, "σ", "", 0)],
         edges=[(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 0),
                (4, 7), (7, 5)]),
    dict(name="摩羯座", en="Capricornus (Capricorn)", dates="12/22 - 1/19",
         stars=[(5, 4, "β", "", 0), (6, 8, "α", "", 0), (20, 2, "θ", "", 0),
                (33, 4, "γ", "", 0), (34, 7, "δ", "", 0), (24, 8, "ψ", "", 0)],
         edges=[(0, 2), (2, 3), (3, 4), (4, 5), (5, 1), (1, 0)]),
    dict(name="宝瓶座", en="Aquarius", alias=("水瓶座",), dates="1/20 - 2/18",
         stars=[(5, 3, "ε", "", 0), (8, 6, "δ", "", 0), (11, 3, "", "", 0),
                (8, 11, "", "", 0), (20, 6, "α", "危宿一", 0),
                (17, 2, "ζ", "", 0), (24, 3, "β", "虚宿一", 0),
                (26, 8, "γ", "", 0), (21, 10, "η", "", 0),
                (13, 9, "", "", 0), (16, 12, "", "", 0)],
         edges=[(0, 1), (1, 2), (1, 3), (5, 4), (6, 4), (7, 4), (4, 8),
                (3, 9), (9, 10), (8, 10)]),
    dict(name="双鱼座", en="Pisces", dates="2/19 - 3/20",
         stars=[(4, 3, "", "", 0), (6, 2, "", "", 0), (7, 4, "γ", "", 0),
                (5, 5, "", "", 0), (6, 7, "ω", "", 0), (12, 9, "", "", 0),
                (19, 11, "", "", 0), (26, 10, "", "", 0),
                (32, 8, "α", "右更二", 0), (35, 4, "η", "", 0),
                (37, 2, "", "", 0), (33, 1, "", "", 0)],
         edges=[(0, 1), (1, 2), (2, 3), (3, 0), (3, 4), (4, 5), (5, 6), (6, 7),
                (7, 8), (8, 9), (9, 10), (10, 11), (11, 9)]),
]


def _setup_streams():
    """管道/重定向时强制 UTF-8 输入输出，避免 Windows 默认 GBK 报错。"""
    for s in (sys.stdout, sys.stderr):
        try:
            if s is not None and not s.isatty():
                s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def draw_line(grid, x0, y0, x1, y1):
    """Bresenham 直线，只在空白处画点，避免覆盖星星。"""
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if 0 <= y0 < H and 0 <= x0 < W and grid[y0][x0] == " ":
            grid[y0][x0] = "."
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def render(c):
    grid = [[" "] * W for _ in range(H)]
    for i, j in c["edges"]:
        x0, y0 = c["stars"][i][:2]
        x1, y1 = c["stars"][j][:2]
        draw_line(grid, x0, y0, x1, y1)
    for x, y, _label, _name, bright in c["stars"]:
        grid[y][x] = "@" if bright else "*"
    out = ["+" + "-" * W + "+"]
    out += ["|" + "".join(row) + "|" for row in grid]
    out += ["+" + "-" * W + "+"]
    return "\n".join(out)


def show(c):
    print(f"{c['name']}（{c['en']}）  日期 {c['dates']}")
    print(render(c))
    print(f"图例: @ 亮星  * 恒星  . 连线   |   星点 {len(c['stars'])} 个 · "
          f"连线 {len(c['edges'])} 条")
    legend = [f"{label} {name}".strip()
              for x, y, label, name, b in c["stars"] if label or name]
    if legend:
        print("主要星: " + "、".join(legend))
    print()


def find(query):
    q = query.strip().lower()
    if not q:
        return []
    hits = []
    for c in CONSTELLATIONS:
        names = [c["name"], c["en"]] + list(c.get("alias", ()))
        if any(q in n.lower() for n in names):
            hits.append(c)
    return hits


def main(argv=None):
    _setup_streams()
    ap = argparse.ArgumentParser(description="打印十二星座的星点连线示意图")
    ap.add_argument("queries", nargs="*",
                    help="星座中文名/俗称/英文名，可只写前几个字")
    ap.add_argument("--all", action="store_true", help="打印全部十二张星图")
    a = ap.parse_args(argv)

    if not a.queries and not a.all:
        print("十二星座一览（查询示例: python constellation-board.py 天蝎）:")
        for c in CONSTELLATIONS:
            alias = ("（俗称 " + "/".join(c.get("alias", ())) + "）") \
                if c.get("alias") else ""
            print(f"  {c['name']}  {c['en']:<24} {c['dates']}{alias}")
        return 0

    targets, missing = [], []
    if a.all:
        targets = list(CONSTELLATIONS)
    else:
        for q in a.queries:
            hits = find(q)
            if hits:
                targets.extend(hits)
            else:
                missing.append(q)
    for c in targets:
        show(c)
    if missing:
        print("没有找到: " + "、".join(missing) +
              "（可用名称见: python constellation-board.py）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
