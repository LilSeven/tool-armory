#!/usr/bin/env python3
"""秘密分割器 (shamir-split)。

用途:
    在 GF(2^8) (本原多项式 0x11D) 上实现 Shamir (k,n) 门限秘密分割:
    把秘密拆成 n 份, 任意 k 份可精确恢复原秘密, 少于 k 份在信息论上
    不泄露任何内容。每个秘密字节独立取 k-1 个随机系数 (secrets 模块),
    每份格式为一行 "X:HEX", X=分享编号(1..255), HEX=该份的字节序列。

退出码: 0=成功, 2=参数或数据错误。

示例:
    python -I shamir-split.py split --secret "opensesame" --n 5 --k 3
    python -I shamir-split.py split --in secret.bin --n 5 --k 3 > shares.txt
    head -n 3 shares.txt | python -I shamir-split.py combine --text
    python -I shamir-split.py combine --out recovered.bin shares.txt
"""
import argparse
import secrets
import sys

_PRIME_POLY = 0x11D  # GF(2^8) 本原多项式 x^8 + x^4 + x^3 + x^2 + 1

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= _PRIME_POLY
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def gf_div(a: int, b: int) -> int:
    """a / b, 要求 b != 0。"""
    if a == 0:
        return 0
    return _EXP[(_LOG[a] - _LOG[b]) % 255]


def make_shares(secret: bytes, k: int, n: int):
    """返回 [(x, bytes), ...], x 取 1..n, 每份长度与 secret 相同。"""
    bufs = [(x, bytearray()) for x in range(1, n + 1)]
    for byte in secret:
        coeffs = [byte] + [secrets.randbelow(256) for _ in range(k - 1)]
        for x, buf in bufs:
            y = 0
            for c in reversed(coeffs):
                y = gf_mul(y, x) ^ c
            buf.append(y)
    return [(x, bytes(buf)) for x, buf in bufs]


def combine_shares(shares):
    """Lagrange 插值于 x=0 恢复秘密。shares: [(x, bytes), ...], 需 >= k 份。"""
    xs = [x for x, _ in shares]
    if len(set(xs)) != len(xs):
        raise ValueError("分享编号 X 重复")
    length = len(shares[0][1])
    if any(len(data) != length for _, data in shares):
        raise ValueError("各分享字节长度不一致")
    secret = bytearray(length)
    for i in range(length):
        acc = 0
        for j, (xj, yj) in enumerate(shares):
            num = 1
            den = 1
            for m, (xm, _) in enumerate(shares):
                if m == j:
                    continue
                num = gf_mul(num, xm)
                den = gf_mul(den, xj ^ xm)
            acc ^= gf_mul(yj[i], gf_div(num, den))
        secret[i] = acc
    return bytes(secret)


def parse_shares_text(text: str):
    shares = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for sep in (":", "-"):
            if sep in line:
                xs, hexs = line.split(sep, 1)
                try:
                    x = int(xs.strip())
                    data = bytes.fromhex(hexs.strip())
                except ValueError:
                    raise ValueError(f"第 {lineno} 行无法解析: {raw!r}") from None
                break
        else:
            raise ValueError(f"第 {lineno} 行格式应为 X:HEX: {raw!r}")
        if not 1 <= x <= 255:
            raise ValueError(f"第 {lineno} 行分享编号越界(1..255): {x}")
        if not data:
            raise ValueError(f"第 {lineno} 行分享内容为空")
        shares.append((x, data))
    if not shares:
        raise ValueError("没有读到任何分享 (格式: 每行 X:HEX)")
    return shares


def cmd_split(args) -> int:
    if (args.secret is None) == (args.infile is None):
        raise ValueError("--secret 与 --in 必须二选一")
    if args.infile:
        with open(args.infile, "rb") as fh:
            data = fh.read()
    else:
        data = args.secret.encode("utf-8")
    if not data:
        raise ValueError("秘密为空")
    if not 1 <= args.n <= 255:
        raise ValueError("--n 必须在 1..255")
    if not 1 <= args.k <= args.n:
        raise ValueError("--k 必须在 1..n")
    shares = make_shares(data, args.k, args.n)
    print(f"# shamir-split: k={args.k} n={args.n} bytes={len(data)}",
          file=sys.stderr)
    for x, buf in shares:
        print(f"{x}:{buf.hex()}")
    return 0


def cmd_combine(args) -> int:
    if args.shares:
        texts = []
        for path in args.shares:
            with open(path, encoding="utf-8") as fh:
                texts.append(fh.read())
        text = "\n".join(texts)
    else:
        text = sys.stdin.read()
    shares = parse_shares_text(text)
    secret = combine_shares(shares)
    if args.out:
        with open(args.out, "wb") as fh:
            fh.write(secret)
        print(f"已写入 {args.out} ({len(secret)} 字节, 由 {len(shares)} 份恢复)")
    elif args.text:
        try:
            print(secret.decode("utf-8"))
        except UnicodeDecodeError:
            print("错误: 秘密不是有效 UTF-8 文本, 请改用 --out 或默认 hex 输出",
                  file=sys.stderr)
            return 2
    else:
        print(secret.hex())
    return 0


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="shamir-split",
        description="GF(256) 上的 Shamir (k,n) 门限秘密分割与恢复。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_split = sub.add_parser("split", help="把秘密拆成 n 份 (每行输出 X:HEX)")
    p_split.add_argument("--secret", help="秘密文本 (UTF-8)")
    p_split.add_argument("--in", dest="infile", help="从文件读取秘密 (原始字节)")
    p_split.add_argument("--n", type=int, required=True, help="分享总数 n (1..255)")
    p_split.add_argument("--k", type=int, required=True, help="恢复门限 k (1..n)")

    p_comb = sub.add_parser("combine", help="从至少 k 份恢复秘密")
    p_comb.add_argument("shares", nargs="*",
                        help="分享文件 (每行 X:HEX, 支持 # 注释); 缺省读 stdin")
    p_comb.add_argument("--text", action="store_true", help="按 UTF-8 文本输出秘密")
    p_comb.add_argument("--out", help="把恢复的原始字节写入文件")

    args = parser.parse_args(argv)
    try:
        if args.command == "split":
            return cmd_split(args)
        return cmd_combine(args)
    except (ValueError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
