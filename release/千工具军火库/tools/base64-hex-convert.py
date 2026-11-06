"""Base64 与十六进制互转 —— 同一串二进制在 Base64 与 hex 两种表示之间转换并展示。

用途:
    把输入(Base64、十六进制或原始二进制)解成同一份二进制数据, 再展示它的
    hex 表示与 Base64 表示及字节数。输入格式用 --from 指定(auto/hex/b64/raw,
    默认 auto); --to 选择输出哪些表示(hex/b64/both, 默认 both)。
    自动识别规则: 内容无法按 UTF-8 解码视为 raw 二进制; 去除空白后全为
    十六进制字符且长度为偶数视为 hex(全 hex 字符且不带填充的 Base64 有被
    误判为 hex 的风险, 请显式用 --from b64); 其余按 Base64 解析(支持 URL
    安全字符 '-' '_', 支持 data:...;base64, 与 base64:// 前缀)。

示例命令:
    python base64-hex-convert.py --string "SGVsbG8sIHdvcmxkIQ=="
    python base64-hex-convert.py --from hex --string "48 65 6C 6C 6F" --to b64
    python base64-hex-convert.py --in blob.bin --from raw
    echo "AAECAwQFBgcICQoLDA0PEA8=" | python base64-hex-convert.py

退出码: 0 成功; 1 输入无法解析或读取失败; 2 参数错误。

仅依赖 Python 标准库。
"""

import argparse
import base64
import binascii
import pathlib
import re
import sys

HEX_RE = re.compile(r"[0-9a-fA-F]+")
FMT_NAME = {"raw": "raw(原始二进制)", "hex": "hex(十六进制)", "b64": "base64"}


def read_bytes(args):
    if args.string is not None:
        return args.string.encode("utf-8")
    path = args.in_file or args.file
    if path:
        return pathlib.Path(path).read_bytes()
    if sys.stdin.isatty():
        raise ValueError("没有输入: 请用 --string、--in/位置参数文件或 stdin 提供内容")
    return sys.stdin.buffer.read()


def parse_hex(text):
    s = "".join(text.split())
    if s.lower().startswith("0x"):
        s = s[2:]
    s = s.replace(":", "").replace(",", "")
    if not s:
        raise ValueError("hex 输入为空")
    if not HEX_RE.fullmatch(s):
        raise ValueError("hex 输入含非十六进制字符")
    if len(s) % 2 != 0:
        raise ValueError("hex 长度为奇数(%d 位), 无法按字节解析" % len(s))
    return bytes.fromhex(s)


def parse_b64(text):
    s = "".join(text.split())
    m = re.match(r"data:[^;,]{0,200};base64\s*,", s, re.IGNORECASE)
    if m:
        s = s[m.end():]
    elif s.lower().startswith("base64://"):
        s = s[9:]
    s = s.replace("-", "+").replace("_", "/")
    if not s:
        raise ValueError("Base64 输入为空")
    if len(s) % 4 != 0:
        raise ValueError("Base64 长度 %d 不是 4 的倍数(缺 padding?)" % len(s))
    try:
        return base64.b64decode(s, validate=True)
    except binascii.Error as exc:
        raise ValueError("Base64 解码失败: %s" % exc)


def decode_input(raw, forced):
    """返回 (识别出的格式, 解码后的二进制)。"""
    if forced == "raw":
        return "raw", raw
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        if forced == "auto":
            return "raw", raw
        raise ValueError("输入不是 UTF-8 文本, 无法按 %s 解析(试试 --from raw)" % forced)
    compact = "".join(text.split())
    if forced == "hex":
        return "hex", parse_hex(text)
    if forced == "b64":
        return "b64", parse_b64(text)
    # auto: 先试 hex, 再试 base64
    if compact and all(c in "0123456789abcdefABCDEF" for c in compact) \
            and len(compact) % 2 == 0:
        return "hex", parse_hex(text)
    return "b64", parse_b64(text)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Base64 与十六进制(hex)互转, 同时展示同一份二进制的两种表示")
    parser.add_argument("file", nargs="?",
                        help="输入文件(Base64/hex 文本, 或 --from raw 的二进制)")
    parser.add_argument("--in", dest="in_file", help="输入文件路径(优先于位置参数)")
    parser.add_argument("--string", help="直接传入文本内容")
    parser.add_argument("--from", dest="src_fmt", choices=("auto", "hex", "b64", "raw"),
                        default="auto", help="输入格式(默认 auto 自动识别)")
    parser.add_argument("--to", choices=("hex", "b64", "both"), default="both",
                        help="输出哪些表示(默认 both)")
    parser.add_argument("--upper", action="store_true", help="hex 用大写输出")
    parser.add_argument("--group", type=int, default=0,
                        help="hex 按 N 字节一组以空格分组(默认 0=连续)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if args.group < 0:
        parser.error("--group 不能为负数")

    try:
        raw = read_bytes(args)
        fmt, blob = decode_input(raw, args.src_fmt)
    except (ValueError, OSError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1

    print("输入格式: %s | 字节数: %d" % (FMT_NAME[fmt], len(blob)))
    if args.to in ("hex", "both"):
        h = blob.hex()
        if args.upper:
            h = h.upper()
        if args.group > 0:
            step = 2 * args.group
            h = " ".join(h[i:i + step] for i in range(0, len(h), step))
        print("hex    : %s" % h)
    if args.to in ("b64", "both"):
        print("base64 : %s" % base64.b64encode(blob).decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
