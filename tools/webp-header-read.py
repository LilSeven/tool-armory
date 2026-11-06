#!/usr/bin/env python3
"""WebP 头读取 —— 解析 WebP（RIFF 容器）的 VP8/VP8L/VP8X 块。

遍历 RIFF/WEBP 容器中的块，输出画布宽高、编码类型（lossy / lossless /
extended），以及 Alpha、动画（ANIM）、ICC/EXIF/XMP 等标志。

示例命令:
    python webp-header-read.py IMAGE.webp            # 人类可读输出
    python webp-header-read.py --json IMAGE.webp     # JSON 输出
    python webp-header-read.py --self-test           # 内置自测（临时目录构造样例输入）

仅依赖 Python 标准库。格式依据 Google《WebP 容器规范》与 RFC 9649（VP8L）。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import sys
import tempfile

# Windows 控制台编码兜底，保证中文输出不报 UnicodeEncodeError
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# --------------------------------------------------------------- 解析函数 --

def parse_vp8_keyframe(payload: bytes) -> tuple[int, int, int, int]:
    """有损 VP8 关键帧头 -> (width, height, h_scale, v_scale)。"""
    if len(payload) < 10:
        raise ValueError("VP8 块载荷不足 10 字节，读不到关键帧头")
    if payload[3:6] != b"\x9d\x01\x2a":
        raise ValueError("VP8 关键帧起始码缺失（应为 9D 01 2A）")
    w, h = struct.unpack_from("<HH", payload, 6)
    return w & 0x3FFF, h & 0x3FFF, (w >> 14) & 3, (h >> 14) & 3


def parse_vp8l_header(payload: bytes) -> tuple[int, int, bool, int]:
    """无损 VP8L 头 -> (width, height, alpha_hint, version)。"""
    if len(payload) < 5 or payload[0] != 0x2F:
        raise ValueError("VP8L 载荷过短或签名字节（0x2F）缺失")
    bits = struct.unpack_from("<I", payload, 1)[0]
    return (
        (bits & 0x3FFF) + 1,
        ((bits >> 14) & 0x3FFF) + 1,
        bool((bits >> 28) & 1),
        (bits >> 29) & 7,
    )


def parse_vp8x_header(payload: bytes) -> dict:
    """扩展格式 VP8X 头 -> 画布尺寸与特性标志。"""
    if len(payload) < 10:
        raise ValueError("VP8X 载荷不足 10 字节")
    flags = payload[0]
    return {
        "width": int.from_bytes(payload[4:7], "little") + 1,
        "height": int.from_bytes(payload[7:10], "little") + 1,
        "icc": bool(flags & 0x20),
        "alpha": bool(flags & 0x10),
        "exif": bool(flags & 0x08),
        "xmp": bool(flags & 0x04),
        "animation": bool(flags & 0x02),
    }


def parse_webp(data: bytes, name: str = "<bytes>") -> dict:
    """解析 WebP 字节流 -> 信息字典；解析失败抛 ValueError。"""
    if len(data) < 12:
        raise ValueError("文件不足 12 字节，放不下 RIFF/WEBP 头")
    if data[0:4] != b"RIFF":
        raise ValueError("RIFF 魔数缺失（前 4 字节应为 'RIFF'）")
    if data[8:12] != b"WEBP":
        raise ValueError("WEBP 标识缺失（偏移 8 处应为 'WEBP'）")

    riff_size = struct.unpack_from("<I", data, 4)[0]
    info = {
        "file": name,
        "file_size": len(data),
        "riff_declared_size": riff_size + 8,
        "format": None,
        "codec_chunk": None,
        "width": None,
        "height": None,
        "alpha": False,
        "animation": False,
        "icc_profile": False,
        "exif": False,
        "xmp": False,
        "vp8_h_scale": None,
        "vp8_v_scale": None,
        "vp8l_version": None,
        "chunks": [],
        "warnings": [],
    }

    limit = len(data)
    if riff_size >= 4:
        declared_end = 8 + riff_size
        if declared_end < limit:
            info["warnings"].append(
                f"RIFF 声明大小 {riff_size + 8} 小于实际文件 {len(data)}（尾部有多余数据）")
            limit = declared_end
        elif declared_end > limit:
            info["warnings"].append(
                f"RIFF 声明大小 {riff_size + 8} 大于实际文件 {len(data)}（文件可能被截断）")

    pos = 12
    saw_anim = saw_alph = False
    while pos + 8 <= limit:
        fourcc = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body_at = pos + 8
        payload = data[body_at:body_at + size]
        cc = fourcc.decode("ascii", "replace")
        info["chunks"].append(
            {"fourcc": cc, "declared_size": size, "payload_read": len(payload)})
        if len(payload) < size:
            info["warnings"].append(
                f"块 {cc} 声明 {size} 字节，但只剩 {len(payload)} 字节可读（截断）")

        if fourcc == b"VP8 " and info["codec_chunk"] is None:
            w, h, hs, vs = parse_vp8_keyframe(payload)
            info.update(codec_chunk="VP8", format="lossy", width=w, height=h,
                        vp8_h_scale=hs, vp8_v_scale=vs)
        elif fourcc == b"VP8L" and info["codec_chunk"] is None:
            w, h, alpha_hint, ver = parse_vp8l_header(payload)
            info.update(codec_chunk="VP8L", format="lossless", width=w, height=h,
                        vp8l_version=ver)
            if alpha_hint:
                info["alpha"] = True
        elif fourcc == b"VP8X" and info["codec_chunk"] is None:
            x = parse_vp8x_header(payload)
            info.update(codec_chunk="VP8X", format="extended",
                        width=x["width"], height=x["height"],
                        icc_profile=x["icc"], exif=x["exif"], xmp=x["xmp"],
                        alpha=info["alpha"] or x["alpha"],
                        animation=info["animation"] or x["animation"])
        elif fourcc == b"ANIM":
            saw_anim = True
        elif fourcc == b"ALPH":
            saw_alph = True

        pos = body_at + size + (size & 1)  # 块载荷按 2 字节对齐

    if saw_anim:
        info["animation"] = True
    if saw_alph:
        info["alpha"] = True
    if info["codec_chunk"] is None:
        raise ValueError("未找到图像块（VP8 / VP8L / VP8X 之一）")
    return info


# --------------------------------------------------------------- 输出 ------

def render(info: dict) -> str:
    yn = lambda b: "yes" if b else "no"
    lines = [
        f"file: {info['file']}",
        f"file_size: {info['file_size']} bytes (RIFF 声明 {info['riff_declared_size']})",
        f"format: {info['format']} ({info['codec_chunk']})",
        f"width: {info['width']}",
        f"height: {info['height']}",
        f"alpha: {yn(info['alpha'])}",
        f"animation: {yn(info['animation'])}",
        f"icc_profile: {yn(info['icc_profile'])}",
        f"exif: {yn(info['exif'])}",
        f"xmp: {yn(info['xmp'])}",
    ]
    if info["vp8_h_scale"] is not None:
        lines.append(f"vp8_scale: h={info['vp8_h_scale']} v={info['vp8_v_scale']}")
    if info["vp8l_version"] is not None:
        lines.append(f"vp8l_version: {info['vp8l_version']}")
    lines.append("chunks: " + " ".join(c["fourcc"] for c in info["chunks"]))
    lines += [f"warning: {w}" for w in info["warnings"]]
    return "\n".join(lines)


# --------------------------------------------------------------- 自测 ------

def _riff(chunks) -> bytes:
    """把 (fourcc, payload) 列表打包成完整 RIFF/WEBP 文件字节。"""
    body = b"WEBP"
    for cc, pl in chunks:
        body += cc + struct.pack("<I", len(pl)) + pl + (b"\x00" if len(pl) & 1 else b"")
    return b"RIFF" + struct.pack("<I", len(body)) + body


def self_test() -> bool:
    """在临时目录构造样例 WebP，逐项断言解析结果。"""
    tmp = tempfile.mkdtemp(prefix="webp-selftest-")
    try:
        # 1) 有损 VP8：66x36
        vp8_payload = b"\xa0\x00\x00" + b"\x9d\x01\x2a" + struct.pack("<HH", 66, 36)
        f1 = os.path.join(tmp, "lossy.webp")
        with open(f1, "wb") as f:
            f.write(_riff([(b"VP8 ", vp8_payload)]))
        with open(f1, "rb") as f:
            i1 = parse_webp(f.read(), f1)
        assert (i1["format"], i1["width"], i1["height"], i1["alpha"], i1["animation"]) \
            == ("lossy", 66, 36, False, False), i1
        print("self-test 1/4 有损 VP8: 66x36, alpha=no, animation=no  OK")

        # 2) 无损 VP8L：66x36，带 alpha 提示位
        vp8l_payload = b"\x2f" + struct.pack("<I", 65 | (35 << 14) | (1 << 28))
        f2 = os.path.join(tmp, "lossless.webp")
        with open(f2, "wb") as f:
            f.write(_riff([(b"VP8L", vp8l_payload)]))
        with open(f2, "rb") as f:
            i2 = parse_webp(f.read(), f2)
        assert (i2["format"], i2["width"], i2["height"], i2["alpha"]) \
            == ("lossless", 66, 36, True), i2
        print("self-test 2/4 无损 VP8L: 66x36, alpha 提示=yes  OK")

        # 3) 扩展 VP8X：100x50，动画 + alpha，含 ANIM/ALPH 块
        vp8x_payload = bytes([0x12, 0, 0, 0]) + struct.pack("<I", 99)[:3] + struct.pack("<I", 49)[:3]
        anim_payload = b"\x00\x00\x00\x00" + struct.pack("<H", 0)
        f3 = os.path.join(tmp, "animated.webp")
        with open(f3, "wb") as f:
            f.write(_riff([(b"VP8X", vp8x_payload), (b"ALPH", b"\x00"),
                           (b"ANIM", anim_payload)]))
        with open(f3, "rb") as f:
            i3 = parse_webp(f.read(), f3)
        assert (i3["format"], i3["width"], i3["height"], i3["alpha"], i3["animation"]) \
            == ("extended", 100, 50, True, True), i3
        print("self-test 3/4 扩展 VP8X: 100x50, alpha=yes, animation=yes  OK")

        # 4) 坏输入应报 ValueError 而非崩溃
        bad_inputs = [b"", b"RIFF\x00\x00", b"RIFF" + struct.pack("<I", 4) + b"PNGX",
                      b"RIFF" + struct.pack("<I", 4) + b"WEBP"]
        for bad in bad_inputs:
            try:
                parse_webp(bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f"坏输入未被拒绝: {bad!r}")
        print("self-test 4/4 坏输入全部正确拒绝  OK")
        return True
    except AssertionError as e:
        print(f"SELF-TEST FAILED: {e}", file=sys.stderr)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="解析 WebP 头：宽高、编码类型（VP8/VP8L/VP8X）、动画与 Alpha 标志")
    ap.add_argument("file", nargs="?", help="WebP 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ap.add_argument("--self-test", action="store_true", help="构造样例输入运行自测")
    args = ap.parse_args(argv)

    if args.self_test:
        return 0 if self_test() else 1
    if not args.file:
        ap.error("需要提供一个 WebP 文件路径（或用 --self-test）")
    try:
        with open(args.file, "rb") as f:
            info = parse_webp(f.read(), args.file)
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
