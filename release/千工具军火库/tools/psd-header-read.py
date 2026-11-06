#!/usr/bin/env python3
"""PSD 头读取 —— 解析 PSD/PSB 文件头（8BPS）。

读取 Photoshop 文档头（26 字节），输出版本（PSD/PSB）、通道数、宽高、
位深与颜色模式（Bitmap/Grayscale/Indexed/RGB/CMYK/Multichannel/Duotone/Lab）。

示例命令:
    python psd-header-read.py IMAGE.psd              # 人类可读输出
    python psd-header-read.py --json IMAGE.psb       # JSON 输出
    python psd-header-read.py --self-test            # 内置自测（临时目录构造样例输入）

仅依赖 Python 标准库。格式依据 Adobe《Photoshop File Formats Specification》。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import sys
import tempfile

# Windows 控制台编码兜底
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VERSION_NAMES = {1: "PSD", 2: "PSB"}
COLOR_MODES = {0: "Bitmap", 1: "Grayscale", 2: "Indexed", 3: "RGB", 4: "CMYK",
               7: "Multichannel", 8: "Duotone", 9: "Lab"}
VALID_DEPTHS = (1, 8, 16, 32)
MAX_CHANNELS = 56


def parse_psd(data: bytes, name: str = "<bytes>") -> dict:
    """解析 PSD/PSB 文件头 -> 信息字典；失败抛 ValueError。"""
    if len(data) < 26:
        raise ValueError("文件不足 26 字节，放不下 PSD/PSB 头")
    sig, version = struct.unpack_from(">4sH", data, 0)
    if sig != b"8BPS":
        raise ValueError(f"签名不是 '8BPS'（实际为 {sig!r}），不像 PSD/PSB 文件")
    if version not in VERSION_NAMES:
        raise ValueError(f"版本号异常: {version}（应为 1=PSD 或 2=PSB）")
    reserved = data[6:12]
    channels, height, width, depth, mode = struct.unpack_from(">HIIHH", data, 12)

    info = {
        "file": name,
        "signature": "8BPS",
        "version": version,
        "version_name": VERSION_NAMES[version],
        "reserved_zero": reserved == b"\x00" * 6,
        "channels": channels,
        "width": width,
        "height": height,
        "depth": depth,
        "color_mode": mode,
        "color_mode_name": COLOR_MODES.get(mode, f"未知模式 {mode}"),
        "warnings": [],
    }
    if not info["reserved_zero"]:
        info["warnings"].append("头中 6 字节保留位不全为 0（规范要求为 0）")
    if not 1 <= channels <= MAX_CHANNELS:
        info["warnings"].append(f"通道数 {channels} 超出规范范围 1-{MAX_CHANNELS}")
    if depth not in VALID_DEPTHS:
        info["warnings"].append(f"位深 {depth} 不是规范值（1/8/16/32）")
    limit = 300000 if version == 2 else 30000
    if width > limit or height > limit:
        info["warnings"].append(
            f"宽/高超过 {VERSION_NAMES[version]} 规范上限 {limit} 像素")
    return info


def render(info: dict) -> str:
    lines = [
        f"file: {info['file']}",
        f"signature: {info['signature']}",
        f"version: {info['version']} ({info['version_name']})",
        f"channels: {info['channels']}",
        f"width: {info['width']}",
        f"height: {info['height']}",
        f"depth: {info['depth']} bits/channel",
        f"color_mode: {info['color_mode']} ({info['color_mode_name']})",
        f"reserved_zero: {'yes' if info['reserved_zero'] else 'no'}",
    ]
    lines += [f"warning: {w}" for w in info["warnings"]]
    return "\n".join(lines)


def self_test() -> bool:
    """在临时目录构造样例 PSD/PSB，逐项断言解析结果。"""
    tmp = tempfile.mkdtemp(prefix="psd-selftest-")
    try:
        # 1) 8 位 RGB PSD（版本 1）
        f1 = os.path.join(tmp, "rgb.psd")
        with open(f1, "wb") as f:
            f.write(b"8BPS" + struct.pack(">H", 1) + b"\x00" * 6
                    + struct.pack(">HIIHH", 3, 1080, 1920, 8, 3) + b"\x00" * 4)
        with open(f1, "rb") as f:
            i1 = parse_psd(f.read(), f1)
        assert (i1["version_name"], i1["width"], i1["height"], i1["channels"],
                i1["depth"]) == ("PSD", 1920, 1080, 3, 8), i1
        assert i1["color_mode_name"] == "RGB" and i1["reserved_zero"], i1
        assert not i1["warnings"], i1["warnings"]
        print("self-test 1/3 PSD v1: 1920x1080, 3 通道, 8 位, RGB  OK")

        # 2) 16 位 CMYK PSB（版本 2）
        f2 = os.path.join(tmp, "cmyk.psb")
        with open(f2, "wb") as f:
            f.write(b"8BPS" + struct.pack(">H", 2) + b"\x00" * 6
                    + struct.pack(">HIIHH", 4, 3000, 2000, 16, 4) + b"\x00" * 4)
        with open(f2, "rb") as f:
            i2 = parse_psd(f.read(), f2)
        assert (i2["version_name"], i2["width"], i2["height"], i2["channels"],
                i2["depth"], i2["color_mode_name"]) == ("PSB", 2000, 3000, 4, 16, "CMYK"), i2
        print("self-test 2/3 PSB v2: 2000x3000, 4 通道, 16 位, CMYK  OK")

        # 3) 坏签名与超短文件应报 ValueError
        try:
            parse_psd(b"XXXX" + b"\x00" * 22)
        except ValueError:
            pass
        else:
            raise AssertionError("坏签名未被拒绝")
        try:
            parse_psd(b"8BPS")
        except ValueError:
            pass
        else:
            raise AssertionError("超短文件未被拒绝")
        print("self-test 3/3 坏签名/超短文件正确拒绝  OK")
        return True
    except AssertionError as e:
        print(f"SELF-TEST FAILED: {e}", file=sys.stderr)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="解析 PSD/PSB 文件头：宽高、通道数、位深与颜色模式")
    ap.add_argument("file", nargs="?", help="PSD/PSB 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ap.add_argument("--self-test", action="store_true", help="构造样例输入运行自测")
    args = ap.parse_args(argv)

    if args.self_test:
        return 0 if self_test() else 1
    if not args.file:
        ap.error("需要提供一个 PSD/PSB 文件路径（或用 --self-test）")
    try:
        with open(args.file, "rb") as f:
            info = parse_psd(f.read(), args.file)
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
