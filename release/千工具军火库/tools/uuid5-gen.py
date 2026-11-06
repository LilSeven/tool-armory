#!/usr/bin/env python3
"""命名空间 UUID 生成器 —— 生成 v3(MD5)/v5(SHA1) 命名 UUID（RFC 4122/9562），内置 DNS/URL/OID/X500 命名空间。

示例:
  python uuid5-gen.py example.com                        # 默认 v5 + DNS 命名空间
  python uuid5-gen.py --version 3 example.com            # v3(MD5)
  python uuid5-gen.py --namespace url https://example.com/a
  python uuid5-gen.py --namespace oid 2.999.1 --namespace x500 "CN=Alice,O=Example"
  python uuid5-gen.py --namespace 6ba7b810-9dad-11d1-80b4-00c04fd430c8 example.com
  python uuid5-gen.py --check 886313e1-3b8a-5372-9b90-0c9aee199e5d example.com
  python uuid5-gen.py --list-namespaces                  # 列出内置命名空间
  python uuid5-gen.py selftest                           # 内置自测
"""
import argparse
import hashlib
import json
import sys
import uuid

NAMESPACE_IDS = {
    "dns": uuid.NAMESPACE_DNS,
    "url": uuid.NAMESPACE_URL,
    "oid": uuid.NAMESPACE_OID,
    "x500": uuid.NAMESPACE_X500,
}
_VERSIONS = (3, 5)


def gen_named(version: int, namespace, name: str) -> uuid.UUID:
    """RFC 4122 命名 UUID：hash(命名空间字节 + 名字字节)，置版本/变体位。

    namespace 接受 uuid.UUID 实例或 32 位十六进制字符串。
    """
    if version not in _VERSIONS:
        raise ValueError(f"version 仅支持 {list(_VERSIONS)}")
    if not isinstance(namespace, uuid.UUID):
        try:
            namespace = uuid.UUID(str(namespace))
        except ValueError as e:
            raise ValueError(f"命名空间 UUID 无效: {e}") from None
    h = hashlib.md5() if version == 3 else hashlib.sha1()
    h.update(namespace.bytes + name.encode("utf-8"))
    n = int.from_bytes(h.digest()[:16], "big")
    n = (n & ~(0xF << 76)) | (version << 76)      # version 位
    n = (n & ~(0x3 << 62)) | (0x2 << 62)          # variant = RFC 4122
    return uuid.UUID(int=n)


def resolve_namespace(key: str) -> uuid.UUID:
    """'dns'/'url'/'oid'/'x500' 或裸 UUID 字符串 -> uuid.UUID。"""
    k = key.strip().lower()
    if k in NAMESPACE_IDS:
        return NAMESPACE_IDS[k]
    try:
        return uuid.UUID(key.strip())
    except ValueError as e:
        raise ValueError(f"未知命名空间 {key!r}（可用: {', '.join(NAMESPACE_IDS)} 或 UUID）") from None


def list_namespaces() -> str:
    rows = []
    for k, v in NAMESPACE_IDS.items():
        rows.append(f"{k:5s} {v}")
    return "\n".join(rows)


def cmd_main(args) -> int:
    ns = resolve_namespace(args.namespace)
    for name in args.name:
        u = gen_named(args.version, ns, name)
        print(f"{u}  {name}")
    return 0


def _selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}")

    # 1. 与标准库 uuid.uuid3/uuid5 全命名空间对拍（stdlib 即权威实现）
    names = ["python.org", "example.com", "", "https://example.com/a?b=1",
             "2.999.1", "CN=Alice,O=Example", "中文域名.example", "a" * 300]
    ok35 = okns = True
    for ver, ref in ((3, uuid.uuid3), (5, uuid.uuid5)):
        for nskey, nsid in NAMESPACE_IDS.items():
            for nm in names:
                if str(gen_named(ver, nsid, nm)) != str(ref(nsid, nm)):
                    ok35 = False
                    print(f"  不一致: v{ver} {nskey} {nm[:20]!r}")
        for nm in names:
            if str(gen_named(ver, uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), nm)) \
                    != str(ref(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), nm)):
                okns = False
    check("v3/v5 × 4 内置命名空间 × 8 个名字 与标准库一致", ok35)
    check("自定义命名空间与标准库一致", okns)

    # 2. 独立按 RFC 手工构造（不经 uuid 模块命名函数）交叉验证
    for ver, algo in ((3, "md5"), (5, "sha1")):
        for nsid in NAMESPACE_IDS.values():
            for nm in ("example.com", "x"):
                h = hashlib.new(algo)
                h.update(nsid.bytes + nm.encode("utf-8"))
                n = int.from_bytes(h.digest()[:16], "big")
                n = (n & ~(0xF << 76) & ~(0x3 << 62)) | (ver << 76) | (0x2 << 62)
                if str(gen_named(ver, nsid, nm)) != str(uuid.UUID(int=n)):
                    check(f"手工 RFC 构造 v{ver}", False)
                    break
            else:
                continue
            break
        else:
            check(f"手工 RFC 构造 v{ver}（{algo}）", True)

    # 3. 版本/变体位
    u5 = gen_named(5, uuid.NAMESPACE_DNS, "python.org")
    u3 = gen_named(3, uuid.NAMESPACE_DNS, "python.org")
    check("版本位: v5==5, v3==3", u5.version == 5 and u3.version == 3)
    check("变体位: RFC 4122", u5.variant == uuid.RFC_4122 and u3.variant == uuid.RFC_4122)

    # 4. 确定性: 同名同空间结果一致；不同空间/名字结果不同
    check("确定性（两次生成一致）",
          gen_named(5, NAMESPACE_IDS["dns"], "a.com") == gen_named(5, NAMESPACE_IDS["dns"], "a.com"))
    check("不同命名空间结果不同",
          gen_named(5, NAMESPACE_IDS["dns"], "x") != gen_named(5, NAMESPACE_IDS["url"], "x"))
    check("不同名字结果不同",
          gen_named(5, NAMESPACE_IDS["dns"], "x") != gen_named(5, NAMESPACE_IDS["dns"], "y"))
    check("v3 与 v5 结果不同", u3 != u5)

    # 5. Python 官方文档示例: uuid5(NAMESPACE_DNS, 'python.org')
    check("文档示例 uuid5(DNS,'python.org')",
          str(u5) == "886313e1-3b8a-5372-9b90-0c9aee199e5d" == str(uuid.uuid5(uuid.NAMESPACE_DNS, "python.org")))

    # 6. resolve_namespace: 名称/大小写/裸 UUID/非法值
    check("resolve: dns→NAMESPACE_DNS", resolve_namespace("dns") == uuid.NAMESPACE_DNS)
    check("resolve: 大写 URL", resolve_namespace("URL") == uuid.NAMESPACE_URL)
    check("resolve: 裸 UUID", resolve_namespace("6ba7b810-9dad-11d1-80b4-00c04fd430c8") == uuid.NAMESPACE_DNS)
    try:
        resolve_namespace("nope")
        check("resolve: 非法命名空间报错", False)
    except ValueError:
        check("resolve: 非法命名空间报错", True)
    try:
        gen_named(4, "dns", "x")
        check("version=4 拒绝", False)
    except ValueError:
        check("version=4 拒绝", True)

    # 7. list_namespaces 输出
    txt = list_namespaces()
    check("list_namespaces 含 4 个命名空间",
          all(k in txt for k in NAMESPACE_IDS) and len(txt.splitlines()) == 4)

    failed = [n2 for n2, ok2 in checks if not ok2]
    print(f"\nselftest: {len(checks) - len(failed)}/{len(checks)} 项通过")
    if failed:
        print("失败项:", "; ".join(failed))
        return 1
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="uuid5-gen.py",
        description="生成 v3(MD5)/v5(SHA1) 命名空间 UUID，内置 DNS/URL/OID/X500。")
    p.add_argument("name", nargs="*", help="名字（可多个，逐行输出）")
    p.add_argument("--version", type=int, default=5, choices=_VERSIONS,
                   help="UUID 版本: 5=SHA1(默认) / 3=MD5")
    p.add_argument("--namespace", default="dns",
                   help="命名空间: dns/url/oid/x500 或裸 UUID（默认 dns）")
    p.add_argument("--check", metavar="UUID", help="校验给定 UUID 是否等于 name 的命名 UUID")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--list-namespaces", action="store_true", help="列出内置命名空间")
    p.add_argument("cmd", nargs="?", choices=["selftest"], help=argparse.SUPPRESS)
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    if "selftest" in argv:  # selftest 关键字优先于位置参数解析
        return _selftest()
    args = build_parser().parse_args(argv)
    if args.cmd == "selftest":
        return _selftest()
    if args.list_namespaces:
        print(list_namespaces())
        return 0
    try:
        ns = resolve_namespace(args.namespace)
        if not args.name:
            args.error("需要至少一个 name（或用 --list-namespaces / selftest）")
        rows = []
        for name in args.name:
            u = gen_named(args.version, ns, name)
            row = {"name": name, "uuid": str(u), "version": args.version,
                   "namespace": str(ns)}
            if args.check:
                row["match"] = (str(u).lower() == args.check.strip().lower())
            rows.append(row)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            if args.check:
                return 0 if any(r["match"] for r in rows) else 1
            return 0
        for r in rows:
            line = f"{r['uuid']}  {r['name']}"
            if args.check:
                line += f"  [check: {'MATCH' if r['match'] else 'MISMATCH'}]"
            print(line)
        if args.check:
            return 0 if any(r["match"] for r in rows) else 1
        return 0
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
