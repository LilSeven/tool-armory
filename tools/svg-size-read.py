#!/usr/bin/env python3
"""SVG 尺寸读取 —— 用 ElementTree 解析 SVG 根元素的 width/height/viewBox。

输出根元素的 width、height（带单位解析；缺单位按 SVG 用户单位，等同 px）
与 viewBox；当 width/height 缺失时回退用 viewBox 数值（用户单位）补齐，
并给出宽高比。

示例命令:
    python svg-size-read.py IMAGE.svg                # 人类可读输出
    python svg-size-read.py --json IMAGE.svg         # JSON 输出
    python svg-size-read.py --self-test              # 内置自测（临时目录构造样例输入）

仅依赖 Python 标准库。长度语义依据 SVG 1.1 §7 / CSS <length> 单位。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

# Windows 控制台编码兜底
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LENGTH_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z%]*)$")
KNOWN_UNITS = {"px", "pt", "pc", "mm", "cm", "in", "em", "ex", "q", "%"}


def parse_length(text):
    """'12px' -> (12.0, 'px')；'512' -> (512.0, None)（None = 缺单位，按用户单位）。"""
    if not isinstance(text, str):
        return None
    m = LENGTH_RE.match(text.strip())
    if not m:
        return None
    unit = m.group(2)
    if unit and unit not in KNOWN_UNITS:
        return None
    return float(m.group(1)), (unit or None)


def _get_attr(root, name: str):
    """取根元素属性，兼容属性名被记入命名空间的少见情况。"""
    if name in root.attrib:
        return root.attrib[name]
    for k, v in root.attrib.items():
        if k.rsplit("}", 1)[-1] == name:
            return v
    return None


def parse_svg(path: str) -> dict:
    """解析 SVG 根元素尺寸信息 -> 信息字典；失败抛 ValueError/ParseError。"""
    tree = ET.parse(path)
    root = tree.getroot()
    local = root.tag.rsplit("}", 1)[-1].lower()
    if local != "svg":
        raise ValueError(f"根元素不是 svg（实际是 {root.tag!r}）")

    warnings = []
    w_raw = _get_attr(root, "width")
    h_raw = _get_attr(root, "height")
    vb_raw = _get_attr(root, "viewBox")

    vb = None
    if vb_raw is not None:
        parts = vb_raw.replace(",", " ").split()
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            nums = []
        if len(nums) == 4:
            vb = nums
        else:
            warnings.append(f"viewBox 无法解析为 4 个数字: {vb_raw!r}")

    def dim(raw, vb_val, label):
        """解析一个维度；缺失时回退 viewBox（用户单位）。"""
        if raw is not None:
            parsed = parse_length(raw)
            if parsed is None:
                warnings.append(f"{label}={raw!r} 不是可识别的长度（如 512 / 10mm / 100%）")
                parsed = (None, None)
            value, unit = parsed
        else:
            value, unit = None, None
        if value is None and vb_val is not None:
            value, unit = vb_val, None
            warnings.append(f"{label} 缺失，按 viewBox 给出 {vb_val:g} 用户单位")
        return value, unit

    w_val, w_unit = dim(w_raw, vb[2] if vb else None, "width")
    h_val, h_unit = dim(h_raw, vb[3] if vb else None, "height")

    aspect = round(w_val / h_val, 4) if (w_val and h_val) else None

    return {
        "file": path,
        "root_tag": root.tag,
        "width": w_val,
        "height": h_val,
        "width_unit": w_unit,
        "height_unit": h_unit,
        "width_raw": w_raw,
        "height_raw": h_raw,
        "unit_note": "unit 为 null 表示原值缺单位，按 SVG 用户单位（等同 px）",
        "view_box": {"x": vb[0], "y": vb[1], "width": vb[2], "height": vb[3]} if vb else None,
        "view_box_raw": vb_raw,
        "aspect_ratio": aspect,
        "warnings": warnings,
    }


def render(info: dict) -> str:
    def fmt(value, unit):
        if value is None:
            return "未知"
        return f"{value:g} {unit}" if unit else f"{value:g}（无单位，按用户单位）"

    lines = [
        f"file: {info['file']}",
        f"root: {info['root_tag']}",
        f"width: {fmt(info['width'], info['width_unit'])}",
        f"height: {fmt(info['height'], info['height_unit'])}",
        f"viewBox: {info['view_box_raw'] if info['view_box_raw'] is not None else '（无）'}",
        f"aspect_ratio: {info['aspect_ratio'] if info['aspect_ratio'] is not None else '未知'}",
    ]
    lines += [f"warning: {w}" for w in info["warnings"]]
    return "\n".join(lines)


def self_test() -> bool:
    """在临时目录构造样例 SVG，逐项断言解析结果。"""
    tmp = tempfile.mkdtemp(prefix="svg-selftest-")
    ns = 'xmlns="http://www.w3.org/2000/svg"'
    try:
        # 1) 有 width/height（缺单位 -> 用户单位）+ viewBox
        f1 = os.path.join(tmp, "a.svg")
        with open(f1, "w", encoding="utf-8") as f:
            f.write(f'<?xml version="1.0"?>\n<svg {ns} width="800" height="600" '
                    f'viewBox="0 0 400 300"><rect width="400" height="300"/></svg>')
        i1 = parse_svg(f1)
        assert (i1["width"], i1["height"], i1["width_unit"], i1["height_unit"]) \
            == (800.0, 600.0, None, None), i1
        assert i1["view_box"]["width"] == 400.0 and i1["aspect_ratio"] == 1.3333, i1
        print("self-test 1/4 width=800 height=600（缺单位 -> 用户单位）, "
              "viewBox 400x300, 宽高比 1.3333  OK")

        # 2) 只有 viewBox：宽高从 viewBox 补齐并提示
        f2 = os.path.join(tmp, "b.svg")
        with open(f2, "w", encoding="utf-8") as f:
            f.write(f'<svg {ns} viewBox="0 0 100 50"/>')
        i2 = parse_svg(f2)
        assert (i2["width"], i2["height"]) == (100.0, 50.0), i2
        assert any("width 缺失" in w for w in i2["warnings"]), i2["warnings"]
        print("self-test 2/4 仅 viewBox: 100x50 用户单位（自动补齐并提示）  OK")

        # 3) 带单位与百分比；无命名空间的 svg 也能解析
        f3 = os.path.join(tmp, "c.svg")
        with open(f3, "w", encoding="utf-8") as f:
            f.write(f'<svg {ns} width="10mm" height="25.4mm" viewBox="0 0 10 25.4"/>')
        i3 = parse_svg(f3)
        assert (i3["width"], i3["width_unit"], i3["height"], i3["height_unit"]) \
            == (10.0, "mm", 25.4, "mm"), i3
        f4 = os.path.join(tmp, "d.svg")
        with open(f4, "w", encoding="utf-8") as f:
            f.write('<svg width="100%" height="50%"/>')
        i4 = parse_svg(f4)
        assert (i4["width"], i4["width_unit"], i4["height"], i4["height_unit"]) \
            == (100.0, "%", 50.0, "%"), i4
        print("self-test 3/4 带单位: 10mm × 25.4mm；百分比: 100% × 50%（无命名空间前缀也可解析）  OK")

        # 4) 非 svg 根元素应报 ValueError
        f5 = os.path.join(tmp, "e.svg")
        with open(f5, "w", encoding="utf-8") as f:
            f.write("<html><body/></html>")
        try:
            parse_svg(f5)
        except ValueError:
            pass
        else:
            raise AssertionError("非 svg 根元素未被拒绝")
        print("self-test 4/4 非 svg 根元素正确拒绝  OK")
        return True
    except AssertionError as e:
        print(f"SELF-TEST FAILED: {e}", file=sys.stderr)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="解析 SVG 根元素的 width/height/viewBox（缺单位按用户单位）")
    ap.add_argument("file", nargs="?", help="SVG 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ap.add_argument("--self-test", action="store_true", help="构造样例输入运行自测")
    args = ap.parse_args(argv)

    if args.self_test:
        return 0 if self_test() else 1
    if not args.file:
        ap.error("需要提供一个 SVG 文件路径（或用 --self-test）")
    try:
        info = parse_svg(args.file)
    except ET.ParseError as e:
        print(f"error: XML 解析失败: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"error: 无法读取文件: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(info, ensure_ascii=False, indent=2) if args.json else render(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
