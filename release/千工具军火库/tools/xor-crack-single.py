#!/usr/bin/env python3
"""单字节 XOR 分析 (xor-crack-single) —— CTF 教学.

用途:
    对单字节密钥 XOR 的密文, 枚举全部 256 个候选密钥, 按"英文字符频率
    对数似然 + 非英文可打印字符惩罚"打分, 报告最可能的密钥与明文, 并按
    分数列出前 N 个候选。

打分:
    a-z 按英文字母频率取 log10; 空格按高频处理; 常见标点轻微惩罚;
    数字与其它可打印字符中等惩罚; 控制字节与非 ASCII 重罚。
    分数越高越像英文。

退出码: 0=成功 (总会给出最优候选, 无论得分高低), 2=参数或数据错误。

示例:
    python -I xor-crack-single.py --hex 1b37373331363f78151b7f2b783431333d78397828372d363c78373e783a393b3736
    python -I xor-crack-single.py --input ct.bin --input-format raw --top 5
    python -I xor-crack-single.py --input ct.hex --input-format hex --json
    cat ct.hex | python -I xor-crack-single.py --input-format hex
"""
import argparse
import json
import math
import sys


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_FREQ_PCT = {
    "e": 12.702, "t": 9.056, "a": 8.167, "o": 7.507, "i": 6.966,
    "n": 6.749, "s": 6.327, "h": 6.094, "r": 5.987, "d": 4.253,
    "l": 4.025, "c": 2.782, "u": 2.758, "m": 2.406, "w": 2.360,
    "f": 2.228, "g": 2.015, "y": 1.974, "p": 1.929, "b": 1.492,
    "v": 0.978, "k": 0.772, "j": 0.153, "x": 0.150, "q": 0.095, "z": 0.074,
}
_FREQ_LOG = {ch: math.log10(p / 100.0) for ch, p in _FREQ_PCT.items()}
_SPACE_LOG = math.log10(0.16)
_PUNCT = b".,'\"!?;:-()"
_WS = b"\t\n\r"


def score_text(data: bytes) -> float:
    total = 0.0
    for b in data:
        if 97 <= b <= 122:
            total += _FREQ_LOG[chr(b)]
        elif 65 <= b <= 90:
            total += _FREQ_LOG[chr(b).lower()]
        elif b == 0x20:
            total += _SPACE_LOG
        elif b in _PUNCT:
            total += -2.5
        elif b in _WS:
            total += -3.0
        elif 48 <= b <= 57:
            total += -3.0
        elif 32 <= b <= 126:
            total += -3.5
        else:
            total += -8.0
    return total


def xor_all(data: bytes, key: int) -> bytes:
    return bytes(b ^ key for b in data)


def crack(data: bytes):
    """返回 [(score, key), ...], 按分数降序。"""
    scored = [(score_text(xor_all(data, key)), key) for key in range(256)]
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored


def key_char(key: int) -> str:
    return chr(key) if 32 <= key <= 126 else "?"


def render(data: bytes, limit: int = 0) -> str:
    shown = data[:limit] if limit else data
    parts = []
    for b in shown:
        if b == 0x0A:
            parts.append("\\n")
        elif b == 0x09:
            parts.append("\\t")
        elif 32 <= b <= 126:
            parts.append(chr(b))
        else:
            parts.append(f"\\x{b:02x}")
    tail = "..." if limit and len(data) > limit else ""
    return "".join(parts) + tail


def _hex_to_bytes(text: str) -> bytes:
    clean = "".join(text.split())
    try:
        return bytes.fromhex(clean)
    except ValueError:
        raise ValueError(f"密文不是合法的十六进制: {clean[:64]!r}") from None


def _load_ciphertext(args) -> bytes:
    if args.hex_text is not None:
        return _hex_to_bytes(args.hex_text)
    if args.input is not None:
        if args.input == "-":
            raw = sys.stdin.buffer.read()
        else:
            with open(args.input, "rb") as fh:
                raw = fh.read()
        if args.input_format == "hex":
            return _hex_to_bytes(raw.decode("ascii", "replace"))
        return raw
    raw = sys.stdin.buffer.read()
    if args.input_format == "hex":
        return _hex_to_bytes(raw.decode("ascii", "replace"))
    return raw


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="xor-crack-single",
        description="单字节 XOR 密文按英文频率打分, 还原最可能的密钥与明文。",
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--hex", dest="hex_text", help="密文 (hex 字符串, 可含空白)")
    src.add_argument("--input", help="密文文件 ('-' 读 stdin); 两者都缺省时读 stdin")
    parser.add_argument("--input-format", choices=["raw", "hex"], default="raw",
                        help="输入格式, 缺省 raw")
    parser.add_argument("--top", type=int, default=5, help="展示前 N 个候选, 缺省 5")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)
    try:
        data = _load_ciphertext(args)
        if not data:
            raise ValueError("密文为空")
        top = max(1, min(args.top, 256))
        cands = crack(data)
        if args.json:
            def cand(score, key):
                return {"key": key, "key_hex": f"{key:02x}", "key_char": key_char(key),
                        "score": round(score, 4), "plaintext": render(xor_all(data, key))}
            print(json.dumps({"n": len(data), "best": cand(*cands[0]),
                              "top": [cand(s, k) for s, k in cands[:top]]}, indent=2))
        else:
            print(f"密文: {len(data)} 字节; 按英文可读度打分, 前 {top} 个候选:")
            for rank, (score, key) in enumerate(cands[:top], 1):
                mark = "*" if rank == 1 else " "
                disp = render(xor_all(data, key), 100)
                print(f"{mark} {rank:>2}. key=0x{key:02x} ({key_char(key)}) "
                      f"score={score:9.2f}  {disp}")
            best_score, best_key = cands[0]
            print(f"最可能: key=0x{best_key:02x} ('{key_char(best_key)}') score={best_score:.2f}")
            print(f"明文: {render(xor_all(data, best_key))}")
        return 0
    except (ValueError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
