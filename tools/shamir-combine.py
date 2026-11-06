#!/usr/bin/env python3
"""秘密恢复器 (shamir-combine) —— 与 shamir-split.py 分割器配套.

用途:
    收集至少 k 份分割片段, 在 GF(2^8) (本原多项式 0x11D, 与 shamir-split
    一致) 上做拉格朗日插值, 于 x=0 处精确恢复原秘密。片段格式与分割器
    相同: 每行一份 "X:HEX" (X=分享编号 1..255, HEX=该份的字节序列),
    '#' 开头为注释行。

行为:
    - --k 指定门限时, 提供的互不相同片段必须 >= k, 取编号 x 最小的前 k 份
      插值; 省略 --k 时按提供的片段数插值 (与 shamir-split combine 一致)。
    - 输出: 缺省打印 hex; --text 按 UTF-8 文本打印; --out FILE 写原始字节。
    - 片段文件缺省为 stdin, 可同时给多个文件。

退出码: 0=成功, 2=参数或数据错误。

示例:
    python -I shamir-split.py split --secret "opensesame" --n 5 --k 3 > shares.txt
    python -I shamir-combine.py --k 3 --text shares.txt
    head -n 3 shares.txt | python -I shamir-combine.py --k 3 --out secret.bin
    python -I shamir-combine.py --k 3 --out rec.bin s1.txt s2.txt s3.txt
    python -I shamir-combine.py --selftest
"""
import argparse
import secrets
import sys

_PRIME_POLY = 0x11D  # GF(2^8) 本原多项式, 与 shamir-split.py 保持一致

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


def lagrange_zero_at(shares, pos: int) -> int:
    """用 shares [(x, bytes)] 在字节位置 pos 上插值出 f(0)。"""
    acc = 0
    for j, (xj, yj) in enumerate(shares):
        num = 1
        den = 1
        for m, (xm, _) in enumerate(shares):
            if m == j:
                continue
            num = gf_mul(num, xm)
            den = gf_mul(den, xj ^ xm)
        acc ^= gf_mul(yj[pos], gf_div(num, den))
    return acc


def combine_shares(shares, k=None):
    """shares: [(x, bytes)], x 互不相同; 返回 (secret, used_k)。"""
    xs = [x for x, _ in shares]
    if len(set(xs)) != len(xs):
        raise ValueError("分享编号 X 重复")
    length = len(shares[0][1])
    if any(len(data) != length for _, data in shares):
        raise ValueError("各分享字节长度不一致")
    if k is None:
        k = len(shares)
    if k < 1:
        raise ValueError("--k 必须 >= 1")
    if len(shares) < k:
        raise ValueError(f"片段不足: 门限 k={k}, 实际只提供 {len(shares)} 份互不相同片段")
    chosen = sorted(shares, key=lambda t: t[0])[:k]
    secret = bytearray(length)
    for pos in range(length):
        secret[pos] = lagrange_zero_at(chosen, pos)
    return bytes(secret), k


def parse_shares_text(text: str, source: str = "<stdin>"):
    shares = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head = None
        for sep in (":", "-", ","):
            if sep in line:
                xs, hexs = line.split(sep, 1)
                head = (xs.strip(), hexs.strip())
                break
        if head is None:
            parts = line.split(None, 1)
            if len(parts) == 2:
                head = (parts[0], parts[1].strip())
        if head is None:
            raise ValueError(f"{source}: 第 {lineno} 行格式应为 X:HEX: {raw!r}")
        xs, hexs = head
        try:
            x = int(xs)
            data = bytes.fromhex(hexs)
        except ValueError:
            raise ValueError(f"{source}: 第 {lineno} 行无法解析: {raw!r}") from None
        if not 1 <= x <= 255:
            raise ValueError(f"{source}: 第 {lineno} 行分享编号越界(1..255): {x}")
        if not data:
            raise ValueError(f"{source}: 第 {lineno} 行分享内容为空")
        shares.append((x, data))
    if not shares:
        raise ValueError("没有读到任何片段 (格式: 每行 X:HEX)")
    return shares


def selftest() -> int:
    """内置随机 (3,5) 门限往返自测: 故意用非连续编号 x=2,4,5 恢复。"""
    secret = secrets.token_bytes(16)
    n, k = 5, 3
    coefs = [[secrets.randbelow(256) for _ in range(k - 1)] for _ in range(len(secret))]
    shares = []
    for x in range(1, n + 1):
        buf = bytearray(len(secret))
        for pos, b in enumerate(secret):
            y, xp = b, 1
            for c in coefs[pos]:
                xp = gf_mul(xp, x)
                y ^= gf_mul(c, xp)
            buf[pos] = y
        shares.append((x, bytes(buf)))
    subset = [shares[i] for i in (1, 3, 4)]
    rec, used = combine_shares(subset, k)
    ok = rec == secret
    print(f"[selftest] secret (16 随机字节) 按 k={k}/n={n} 分割, 用编号 x={[x for x, _ in subset]} 插值")
    print(f"[selftest] secret   = {secret.hex()}")
    print(f"[selftest] recovered= {rec.hex()}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 2


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="shamir-combine",
        description="收集至少 k 份分割片段, 经 GF(256) 拉格朗日插值恢复原秘密 (与 shamir-split.py 配套)。",
    )
    parser.add_argument("shares", nargs="*",
                        help="片段文件 (每行 X:HEX, 支持 # 注释); 缺省读 stdin")
    parser.add_argument("--k", type=int, default=None,
                        help="恢复门限 k: 提供的片段必须 >= k (缺省按提供的片段数)")
    parser.add_argument("--text", action="store_true", help="按 UTF-8 文本输出秘密")
    parser.add_argument("--out", help="把恢复的原始字节写入文件")
    parser.add_argument("--selftest", action="store_true", help="内置随机 (3,5) 往返自测")
    args = parser.parse_args(argv)
    try:
        if args.selftest:
            return selftest()
        if args.shares:
            texts = []
            for path in args.shares:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    texts.append(fh.read())
            text = "\n".join(texts)
            source = ", ".join(args.shares)
        else:
            text = sys.stdin.read()
            source = "<stdin>"
        shares = parse_shares_text(text, source)
        secret, used = combine_shares(shares, args.k)
        if args.out:
            with open(args.out, "wb") as fh:
                fh.write(secret)
            print(f"[shamir-combine] 已写入 {args.out} ({len(secret)} 字节, "
                  f"用 {used}/{len(shares)} 份片段插值)", file=sys.stderr)
        elif args.text:
            try:
                print(secret.decode("utf-8"))
            except UnicodeDecodeError:
                print("错误: 秘密不是有效 UTF-8 文本, 请改用 --out 或缺省 hex 输出",
                      file=sys.stderr)
                return 2
        else:
            print(secret.hex())
        return 0
    except (ValueError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
