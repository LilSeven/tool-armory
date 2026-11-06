#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命名空间管理器：登记自定义命名空间 UUID（存本地 JSON），用固定盐生成稳定可复现 UUID。

用途：
    add    登记命名空间（名字 -> 指定 UUID）。
    new    由名字确定性派生一个命名空间 UUID（UUIDv5，与盐无关，跨机器一致）。
    list   查看已登记的命名空间与当前盐。
    rm     删除命名空间。
    salt   查看/修改持久化的固定盐（首次使用默认 tool-armory/salt/v1）。
    gen    用「盐 + 命名空间 UUID + 值」生成 UUIDv5：同一盐、同一命名空间、同一值，
           任何时候、任何进程都得到同一 UUID（SHA-1，稳定可复现）。
    selftest  运行内置自测（含跨进程可复现性检查）。

命名空间解析顺序：已登记名字 -> 内置 dns/url/oid/x500 -> 字面 UUID。
盐与值之间用 \\x1f 分隔，避免 ("ab","c") 与 ("a","bc") 撞车。

示例命令：
    python uuid-namespace.py --store ns.json add myapp 550e8400-e29b-41d4-a716-446655440000
    python uuid-namespace.py --store ns.json new reporting
    python uuid-namespace.py --store ns.json list
    python uuid-namespace.py --store ns.json gen myapp user:alice
    python uuid-namespace.py --store ns.json gen dns www.example.com --no-salt --raw
    python uuid-namespace.py --store ns.json salt my-secret-salt
    python uuid-namespace.py --store ns.json rm myapp
    python uuid-namespace.py selftest

退出码：0 成功；2 输入或参数非法。
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid as _uuid
from datetime import datetime, timezone

DEFAULT_STORE = os.path.join(os.path.expanduser("~"), ".tool-armory", "uuid-namespaces.json")
DEFAULT_SALT = "tool-armory/salt/v1"
ROOT_NS = _uuid.uuid5(_uuid.NAMESPACE_DNS, "tool-armory/uuid-namespace/root")
BUILTINS = {
    "dns": _uuid.NAMESPACE_DNS,
    "url": _uuid.NAMESPACE_URL,
    "oid": _uuid.NAMESPACE_OID,
    "x500": _uuid.NAMESPACE_X500,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_store() -> dict:
    return {"salt": DEFAULT_SALT, "namespaces": {}}


def load_store(path: str) -> dict:
    if not os.path.exists(path):
        return _empty_store()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("store file is not a JSON object: %s" % path)
    data.setdefault("salt", DEFAULT_SALT)
    data.setdefault("namespaces", {})
    return data


def save_store(path: str, data: dict) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def resolve_ns(store: dict, name: str):
    """解析命名空间标识 -> (UUID, 来源说明)。"""
    low = name.strip().lower()
    if not low:
        raise ValueError("namespace name must not be empty")
    if low in store["namespaces"]:
        return _uuid.UUID(store["namespaces"][low]["uuid"]), "registered:%s" % low
    if low in BUILTINS:
        return BUILTINS[low], "builtin:%s" % low
    try:
        return _uuid.UUID(name), "literal"
    except ValueError:
        raise ValueError("unknown namespace %r (not registered, not builtin, not a UUID)" % name)


def gen_uuid(ns_uuid: _uuid.UUID, value: str, salt: str = None) -> _uuid.UUID:
    """UUIDv5(ns, salt + \\x1f + value)；salt 为 None 时直接用 value。"""
    name = value if salt is None else salt + "\x1f" + value
    return _uuid.uuid5(ns_uuid, name)


def cmd_list(args) -> int:
    store = load_store(args.store)
    print("store: %s" % args.store)
    print("salt:  %s" % store["salt"])
    names = sorted(store["namespaces"])
    print("namespaces: %d" % len(names))
    for n in names:
        rec = store["namespaces"][n]
        note = ("  note=%s" % rec["note"]) if rec.get("note") else ""
        print("  %s  %s  created=%s%s" % (n, rec["uuid"], rec.get("created", "?"), note))
    return 0


def cmd_add(args) -> int:
    name = args.name.strip().lower()
    if not name:
        raise ValueError("namespace name must not be empty")
    u = _uuid.UUID(args.uuid)  # 非法则抛 ValueError
    store = load_store(args.store)
    if name in store["namespaces"] and not args.force:
        raise ValueError("namespace %r already exists (use --force to overwrite)" % name)
    store["namespaces"][name] = {"uuid": str(u), "created": _now_iso(), "note": args.note or ""}
    save_store(args.store, store)
    print("added namespace %r -> %s" % (name, u))
    return 0


def cmd_new(args) -> int:
    name = args.name.strip().lower()
    if not name:
        raise ValueError("namespace name must not be empty")
    store = load_store(args.store)
    if name in store["namespaces"] and not args.force:
        raise ValueError("namespace %r already exists (use --force to overwrite)" % name)
    u = _uuid.uuid5(ROOT_NS, "ns\x1f" + name)
    store["namespaces"][name] = {"uuid": str(u), "created": _now_iso(), "note": "derived-from-name"}
    save_store(args.store, store)
    print("namespace %r -> %s" % (name, u))
    return 0


def cmd_rm(args) -> int:
    store = load_store(args.store)
    name = args.name.strip().lower()
    if name not in store["namespaces"]:
        raise ValueError("namespace %r not found" % name)
    del store["namespaces"][name]
    save_store(args.store, store)
    print("removed namespace %r" % name)
    return 0


def cmd_salt(args) -> int:
    store = load_store(args.store)
    if args.value is None:
        print(store["salt"])
        return 0
    store["salt"] = args.value
    save_store(args.store, store)
    print("salt updated -> %s" % args.value)
    return 0


def cmd_gen(args) -> int:
    store = load_store(args.store)
    salt = None if args.no_salt else (args.salt if args.salt is not None else store["salt"])
    ns_u, kind = resolve_ns(store, args.ns)
    for value in args.values:
        u = gen_uuid(ns_u, value, salt)
        print(u if args.raw else "%s -> %s" % (value, u))
    return 0


def cmd_selftest(_args) -> int:
    checks = []

    def check(name, cond):
        checks.append(bool(cond))
        print(("ok:   " if cond else "FAIL: ") + name)

    script = os.path.abspath(__file__)
    py = sys.executable
    with tempfile.TemporaryDirectory() as td:
        store1 = os.path.join(td, "a.json")
        store2 = os.path.join(td, "b.json")

        def run(*extra):
            return subprocess.run([py, "-I", script, "--store", store1] + list(extra),
                                  capture_output=True, text=True)

        r = run("add", "myapp", "550e8400-e29b-41d4-a716-446655440000")
        check("add namespace returns 0", r.returncode == 0)
        g1 = run("gen", "myapp", "user:alice", "--raw")
        g2 = run("gen", "myapp", "user:alice", "--raw")
        check("gen returns 0 twice", g1.returncode == 0 and g2.returncode == 0)
        check("cross-process reproducible", g1.stdout == g2.stdout and g1.stdout.strip() != "")

        st = load_store(store1)
        ns_u = _uuid.UUID(st["namespaces"]["myapp"]["uuid"])
        expect = gen_uuid(ns_u, "user:alice", st["salt"])
        check("matches in-process uuid5(salt+value)", g1.stdout.strip() == str(expect))

        g3 = run("--salt", "other-salt", "gen", "myapp", "user:alice", "--raw")
        check("different salt changes output",
              g3.returncode == 0 and g3.stdout.strip() != g1.stdout.strip())

        n1 = subprocess.run([py, "-I", script, "--store", store1, "new", "reporting"],
                            capture_output=True, text=True)
        n2 = subprocess.run([py, "-I", script, "--store", store2, "new", "reporting"],
                            capture_output=True, text=True)
        check("new deterministic across stores",
              n1.returncode == 0 and n2.returncode == 0 and n1.stdout == n2.stdout)

        b1 = run("gen", "dns", "www.example.com", "--no-salt", "--raw")
        check("builtin dns + no salt matches uuid5",
              b1.returncode == 0
              and b1.stdout.strip() == str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "www.example.com")))

        r2 = run("rm", "myapp")
        st2 = load_store(store1)
        check("rm removes namespace", r2.returncode == 0 and "myapp" not in st2["namespaces"])

        bad = run("gen", "no-such-ns", "x")
        check("unknown namespace exits 2", bad.returncode == 2)

    total = len(checks)
    if all(checks):
        print("selftest ok (%d/%d checks)" % (total, total))
        return 0
    print("selftest FAILED (%d/%d checks failed)" % (checks.count(False), total))
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="uuid-namespace.py",
        description="登记自定义命名空间 UUID（本地 JSON），用固定盐生成稳定可复现 UUIDv5",
    )
    p.add_argument("--store", default=DEFAULT_STORE,
                   help="JSON 存储路径（默认 ~/.tool-armory/uuid-namespaces.json）")
    p.add_argument("--salt", default=None, help="临时覆盖盐（仅本次调用，不写回存储）")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="列出命名空间与盐")
    pl.set_defaults(func=cmd_list)
    pa = sub.add_parser("add", help="登记命名空间（指定 UUID）")
    pa.add_argument("name")
    pa.add_argument("uuid")
    pa.add_argument("--note", default="")
    pa.add_argument("--force", action="store_true")
    pa.set_defaults(func=cmd_add)
    pn = sub.add_parser("new", help="由名字确定性派生命名空间 UUID")
    pn.add_argument("name")
    pn.add_argument("--force", action="store_true")
    pn.set_defaults(func=cmd_new)
    pr = sub.add_parser("rm", help="删除命名空间")
    pr.add_argument("name")
    pr.set_defaults(func=cmd_rm)
    ps = sub.add_parser("salt", help="查看或设置固定盐")
    ps.add_argument("value", nargs="?", default=None)
    ps.set_defaults(func=cmd_salt)
    pg = sub.add_parser("gen", help="用盐 + 命名空间 + 值生成可复现 UUIDv5")
    pg.add_argument("ns", help="已登记名字 / 内置 dns|url|oid|x500 / 字面 UUID")
    pg.add_argument("values", nargs="+", help="一个或多个值")
    pg.add_argument("--no-salt", action="store_true", help="不掺盐（等价 uuid5(ns, value)）")
    pg.add_argument("--raw", action="store_true", help="只输出 UUID 本身")
    pg.set_defaults(func=cmd_gen)
    pt = sub.add_parser("selftest", help="运行内置自测")
    pt.set_defaults(func=cmd_selftest)
    return p


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
