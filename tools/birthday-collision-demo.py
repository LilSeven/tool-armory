#!/usr/bin/env python3
"""生日碰撞演示：在截短哈希上做生日攻击（教学用途）。

用途：
    对完整哈希（默认 sha256）截取前 N 位（默认 24 位）作为“指纹”，
    持续生成随机消息并登记指纹，直到两条不同消息指纹相同。
    直观展示生日悖论：约 sqrt(2^N)（更精确为 sqrt(pi/2 · 2^N)）次尝试
    即可得到碰撞，远小于穷举 2^N；位数每增加 1，代价约乘 sqrt(2)。

示例命令：
    python birthday-collision-demo.py --selftest
    python birthday-collision-demo.py --bits 24 --algo sha256
    python birthday-collision-demo.py --bits 16 --algo sha1 --seed 2024
    python birthday-collision-demo.py --bits 8 --algo md5 --max-attempts 100000

退出码：0 找到碰撞（--selftest 全部通过时亦为 0）；
        1 达到尝试上限仍未找到；2 参数错误。
"""

import argparse
import hashlib
import math
import random
import secrets
import sys


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def truncated(digest: bytes, bits: int) -> int:
    """取摘要最高 bits 位作为指纹整数。"""
    return int.from_bytes(digest, "big") >> (len(digest) * 8 - bits)


def attack(bits: int, algo: str, max_attempts: int, seed=None):
    """返回 (msg1, msg2, attempts)；未找到碰撞时 msg1=msg2=None。"""
    algo = algo.lower().replace("-", "")
    try:
        full_bits = hashlib.new(algo).digest_size * 8
    except Exception:
        raise ValueError(f"未知哈希算法：{algo!r}")
    if not (4 <= bits <= full_bits):
        raise ValueError(f"bits 需在 4 ~ {full_bits} 之间")
    rng = random.Random(seed) if seed is not None else None
    seen = {}
    attempts = 0
    while attempts < max_attempts:
        msg = (rng.getrandbits(64).to_bytes(8, "big") if rng
               else secrets.token_bytes(8))
        attempts += 1
        digest = hashlib.new(algo, msg).digest()
        key = truncated(digest, bits)
        if key in seen:
            return seen[key], msg, attempts
        seen[key] = msg
    return None, None, attempts


def report(bits, algo, msg1, msg2, attempts, seed_used) -> int:
    space = 1 << bits
    expected = math.sqrt(math.pi / 2 * space)
    p50 = math.sqrt(2 * math.log(2)) * math.sqrt(space)
    print(f"算法={algo}  指纹位数={bits} bit  指纹空间=2^{bits}={space}")
    print(f"理论参考：首次碰撞期望 ≈ {expected:.0f} 次（sqrt(pi/2·N)），"
          f"50% 概率 ≈ {p50:.0f} 次")
    if msg1 is None:
        print(f"实际结果：尝试 {attempts} 次未找到碰撞（可加大 --max-attempts）")
        return 1
    d1 = hashlib.new(algo, msg1).hexdigest()
    d2 = hashlib.new(algo, msg2).hexdigest()
    fp = truncated(hashlib.new(algo, msg1).digest(), bits)
    print(f"实际结果：第 {attempts} 次尝试出现碰撞"
          f"（实际/期望 = {attempts / expected:.2f}）")
    origin = "（--seed 固定，可复现）" if seed_used is not None else ""
    print(f"碰撞消息：0x{msg1.hex()} 与 0x{msg2.hex()}{origin}")
    print(f"  完整 {algo}：{d1}")
    print(f"  完整 {algo}：{d2}")
    print(f"  前 {bits} 位指纹相同：0x{fp:x}；完整摘要不同 → 截短空间碰撞成立")
    return 0


def selftest() -> int:
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok = ok and cond
        print(f"[{'PASS' if cond else 'FAIL'}] {name}"
              + (f"：{detail}" if detail else ""))

    m1, m2, n = attack(12, "sha256", 200000, seed=2024)
    check("12bit/seed=2024 找到碰撞", m1 is not None and m2 is not None,
          f"尝试 {n} 次")
    if m1 is not None:
        check("两条消息不同", m1 != m2)
        d1, d2 = hashlib.sha256(m1).digest(), hashlib.sha256(m2).digest()
        check("完整摘要不同", d1 != d2)
        check("前 12 位指纹相同", truncated(d1, 12) == truncated(d2, 12))
    m1b, m2b, nb = attack(12, "sha256", 200000, seed=2024)
    check("同 seed 结果可复现", (m1, m2, n) == (m1b, m2b, nb))
    print("selftest:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


def main(argv=None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(
        description="生日攻击碰撞演示（截短哈希，教学用）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--bits", type=int, default=24,
                    help="截短位数（默认 24）")
    ap.add_argument("--algo", default="sha256",
                    help="哈希算法（默认 sha256，如 md5/sha1/sha512）")
    ap.add_argument("--max-attempts", type=int, default=5_000_000,
                    help="尝试上限（默认 5000000）")
    ap.add_argument("--seed", type=int, default=None,
                    help="固定随机种子以复现结果")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        msg1, msg2, attempts = attack(args.bits, args.algo,
                                      args.max_attempts, args.seed)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return report(args.bits, args.algo.lower().replace("-", ""),
                  msg1, msg2, attempts, args.seed)


if __name__ == "__main__":
    sys.exit(main())
