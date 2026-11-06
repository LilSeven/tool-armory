#!/usr/bin/env python3
"""UUIDv4 批量生成器 —— 用 os.urandom 级随机源批量生成随机 UUID，格式可选大括号/URN/无连字符/大写。

示例:
  python uuid4-gen.py                          # 默认 1 个，标准小写连字符格式
  python uuid4-gen.py --count 10               # 批量 10 个
  python uuid4-gen.py --style braces           # {XXXXXXXX-...} 大括号
  python uuid4-gen.py --style urn              # urn:uuid:XXXXXXXX-...
  python uuid4-gen.py --style hex              # 无连字符 32 位十六进制
  python uuid4-gen.py --count 5 --upper        # 大写输出
  python uuid4-gen.py --count 3 --sep ,        # 自定义分隔符
  python uuid4-gen.py selftest                 # 内置自测
"""
import argparse
import re
import secrets
import sys

UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

STYLES = ("bare", "braces", "urn", "hex")


def gen_one() -> str:
    """按 RFC 4122 直接构造 UUIDv4：随机 128 位 + 置版本(4)与变体(10x)位。"""
    n = int.from_bytes(secrets.token_bytes(16), "big")
    n = (n & ~(0xF << 76)) | (0x4 << 76)          # version = 4
    n = (n & ~(0x3 << 62)) | (0x2 << 62)          # variant = RFC 4122 (10xx)
    h = "%032x" % n
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def render(u: str, style: str = "bare", upper: bool = False) -> str:
    if style == "braces":
        out = "{%s}" % u
    elif style == "urn":
        out = "urn:uuid:" + u
    elif style == "hex":
        out = u.replace("-", "")
    else:
        out = u
    return out.upper() if upper else out


def cmd_main(args) -> int:
    for i in range(args.count):
        print(render(gen_one(), args.style, args.upper),
              end="\n" if i == args.count - 1 else args.sep)
    if args.sep != "\n" and args.count:
        print()
    return 0


def _selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}")

    # 1. 大批量: 版本位/变体位/格式/唯一性
    n = 20000
    seen = set()
    v_ok = var_ok = True
    for _ in range(n):
        u = gen_one()
        if not UUID_V4_RE.match(u):
            v_ok = False
        seen.add(u)
    check(f"{n} 个全部匹配 v4 模式（版本位=4，变体位=8/9/a/b）", v_ok)
    check(f"{n} 个全部唯一（{len(seen)}/{n}）", len(seen) == n)

    # 2. 与标准库 uuid.uuid4 的位语义一致（版本/变体 nibble 抽样对比）
    import uuid
    ok = True
    for _ in range(2000):
        u = uuid.UUID(gen_one())
        if u.version != 4 or u.variant != uuid.RFC_4122:
            ok = False
            break
    check("标准库解析: version==4 且 variant==RFC_4122", ok)

    # 3. 渲染格式正确性
    u = "c9bf9e57-1685-4c89-bafb-ff5af830be8a"
    check("bare", render(u) == u)
    check("braces", render(u, "braces") == "{%s}" % u)
    check("urn", render(u, "urn") == "urn:uuid:" + u)
    check("hex", render(u, "hex") == "c9bf9e5716854c89bafbff5af830be8a")
    check("upper", render(u, "braces", upper=True) == "{C9BF9E57-1685-4C89-BAFB-FF5AF830BE8A}")
    check("hex+upper 与 hex() 互逆", render(render(u, "hex"), "hex") == render(u, "hex"))

    # 4. 随机性 sanity: 不同前缀数量应远大于 1
    prefixes = {gen_one()[:8] for _ in range(500)}
    check("随机性 sanity（500 个前缀种类 > 400）", len(prefixes) > 400)

    failed = [n2 for n2, ok2 in checks if not ok2]
    print(f"\nselftest: {len(checks) - len(failed)}/{len(checks)} 项通过")
    if failed:
        print("失败项:", "; ".join(failed))
        return 1
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="uuid4-gen.py",
        description="批量生成随机 UUIDv4，格式可选大括号/URN/无连字符/大写。")
    p.add_argument("--count", "-n", type=int, default=1, help="生成数量（默认 1，上限 100000）")
    p.add_argument("--style", choices=list(STYLES), default="bare",
                   help="输出样式: bare(默认) / braces{...} / urn:uuid: / hex 无连字符")
    p.add_argument("--upper", action="store_true", help="大写输出")
    p.add_argument("--sep", default="\n", help="条目分隔符（默认换行）")
    p.add_argument("cmd", nargs="?", choices=["selftest"], help=argparse.SUPPRESS)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "selftest":
        return _selftest()
    if args.count < 1 or args.count > 100000:
        args.error("count 取值 1..100000")
    if args.sep == "\n":
        args.sep = "\n"
    return cmd_main(args)


if __name__ == "__main__":
    sys.exit(main())
