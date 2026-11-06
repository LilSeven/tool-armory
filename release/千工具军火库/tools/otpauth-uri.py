#!/usr/bin/env python3
"""otpauth:// 链接与 Google Authenticator 迁移串（otpauth-migration）构建/解析工具。纯标准库。

支持:
  * 构建/解析 otpauth://totp/... 与 otpauth://hotp/... 链接
  * 构建/解析 otpauth-migration://offline?data=... 迁移串（内置精简 protobuf 编解码，
    OtpParameters 字段: secret/name/issuer/algorithm/digits/type/counter）

示例:
  python otpauth-uri.py build --type totp --issuer Example --account alice@example.com --secret JBSWY3DPEHPK3PXP
  python otpauth-uri.py build --type hotp --issuer Example --account bob --secret JBSWY3DPEHPK3PXP --counter 5
  python otpauth-uri.py parse "otpauth://totp/Example%3Aalice%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=Example"
  python otpauth-uri.py mig-build --file uris.txt          # 每行一条 otpauth:// 链接；'-' 读 stdin
  python otpauth-uri.py mig-parse "otpauth-migration://offline?data=..." --emit-uris
  python otpauth-uri.py selftest
"""
import argparse
import base64
import json
import sys
from urllib.parse import parse_qs, quote, unquote, urlsplit

ALG_TO_ENUM = {"SHA1": 1, "SHA256": 2, "SHA512": 3, "MD5": 4}
ENUM_TO_ALG = {v: k for k, v in ALG_TO_ENUM.items()}
DIGITS_TO_ENUM = {6: 1, 8: 2}
ENUM_TO_DIGITS = {v: k for k, v in DIGITS_TO_ENUM.items()}
TYPE_TO_ENUM = {"hotp": 1, "totp": 2}
ENUM_TO_TYPE = {v: k for k, v in TYPE_TO_ENUM.items()}


# ---------------------------------------------------------------------------
# protobuf 基元（varint / length-delimited）
# ---------------------------------------------------------------------------
def _varint(n: int) -> bytes:
    if n < 0:
        raise ValueError("varint 不支持负数")
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_varint(buf: bytes, i: int):
    val = 0
    shift = 0
    while True:
        if i >= len(buf):
            raise ValueError("varint 越界（数据截断）")
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, i
        shift += 7
        if shift > 63:
            raise ValueError("varint 过长")


def _tag(field: int, wire_type: int) -> bytes:
    return _varint((field << 3) | wire_type)


def _iter_fields(buf: bytes):
    """遍历 protobuf 消息字段，产出 (field_number, wire_type, value)。"""
    i = 0
    n = len(buf)
    while i < n:
        key, i = _read_varint(buf, i)
        field, wt = key >> 3, key & 7
        if field == 0:
            raise ValueError("非法字段号 0")
        if wt == 0:
            v, i = _read_varint(buf, i)
            yield field, wt, v
        elif wt == 1:
            if i + 8 > n:
                raise ValueError("fixed64 截断")
            yield field, wt, bytes(buf[i:i + 8])
            i += 8
        elif wt == 2:
            ln, i = _read_varint(buf, i)
            if i + ln > n:
                raise ValueError("长度字段截断")
            yield field, wt, bytes(buf[i:i + ln])
            i += ln
        elif wt == 5:
            if i + 4 > n:
                raise ValueError("fixed32 截断")
            yield field, wt, bytes(buf[i:i + 4])
            i += 4
        else:
            raise ValueError(f"不支持的 wire type: {wt}")


# ---------------------------------------------------------------------------
# otpauth:// 链接
# ---------------------------------------------------------------------------
def b32_decode_secret(s: str) -> bytes:
    s = "".join(s.split()).replace("-", "").upper()
    pad = s + "=" * (-len(s) % 8)
    try:
        return base64.b32decode(pad, casefold=True)
    except Exception as e:
        raise ValueError(f"无效的 base32 密钥: {e}") from None


def build_otpauth_uri(otype, issuer, account, secret_b32, algorithm, digits, period, counter):
    label = f"{issuer}:{account}" if issuer else account
    params = ["secret=" + secret_b32]
    if issuer:
        params.append("issuer=" + quote(issuer, safe=""))
    if otype == "hotp":
        params.append(f"counter={counter}")
    params.append(f"algorithm={algorithm}")
    params.append(f"digits={digits}")
    if otype == "totp":
        params.append(f"period={period}")
    return f"otpauth://{otype}/{quote(label, safe='')}?" + "&".join(params)


def parse_otpauth_uri(uri: str) -> dict:
    sp = urlsplit(uri.strip())
    if sp.scheme.lower() != "otpauth":
        raise ValueError(f"不是 otpauth:// 链接: {uri[:60]!r}")
    otype = sp.netloc.lower()
    if otype not in TYPE_TO_ENUM:
        raise ValueError(f"不支持的类型: {otype!r}（应为 totp/hotp）")
    label = unquote(sp.path.lstrip("/"))
    q = parse_qs(sp.query, keep_blank_values=True)
    get1 = lambda k, d=None: q[k][0] if k in q and q[k] else d

    label_issuer, account = None, label
    if ":" in label:
        label_issuer, account = label.split(":", 1)
    secret = get1("secret", "")
    if not secret:
        raise ValueError("缺少 secret 参数")
    raw = b32_decode_secret(secret)
    algorithm = get1("algorithm", "SHA1").upper()
    if algorithm not in ALG_TO_ENUM:
        raise ValueError(f"不支持的算法: {algorithm}")
    digits = int(get1("digits", "6"))
    if digits not in DIGITS_TO_ENUM:
        raise ValueError(f"digits 仅支持 6/8: {digits}")
    out = {
        "type": otype,
        "label": label,
        "label_issuer": label_issuer,
        "account": account,
        "issuer": get1("issuer"),
        "secret": secret.upper(),
        "secret_bytes": raw,
        "algorithm": algorithm,
        "digits": digits,
    }
    if otype == "totp":
        out["period"] = int(get1("period", "30"))
    else:
        out["counter"] = int(get1("counter", "0"))
    return out


# ---------------------------------------------------------------------------
# otpauth-migration:// 离线迁移串
# ---------------------------------------------------------------------------
def _encode_otp_params(e: dict) -> bytes:
    out = bytearray()
    out += _tag(1, 2) + _varint(len(e["secret_bytes"])) + e["secret_bytes"]
    name = e.get("name", "")
    if name:
        nb = name.encode("utf-8")
        out += _tag(2, 2) + _varint(len(nb)) + nb
    issuer = e.get("issuer", "")
    if issuer:
        ib = issuer.encode("utf-8")
        out += _tag(3, 2) + _varint(len(ib)) + ib
    out += _tag(4, 0) + _varint(ALG_TO_ENUM.get(e["algorithm"], 1))
    out += _tag(5, 0) + _varint(DIGITS_TO_ENUM.get(e["digits"], 1))
    out += _tag(6, 0) + _varint(TYPE_TO_ENUM[e["type"]])
    if e["type"] == "hotp":
        out += _tag(7, 0) + _varint(e.get("counter", 0))
    return bytes(out)


def encode_migration(entries) -> bytes:
    """entries: [{"name","issuer","type","algorithm","digits","counter","secret_bytes"}...]"""
    body = bytearray()
    n = len(entries)
    for e in entries:
        p = _encode_otp_params(e)
        body += _tag(1, 2) + _varint(len(p)) + p
    body += _tag(2, 0) + _varint(1)          # version = 1
    body += _tag(3, 0) + _varint(n)          # batch_size
    body += _tag(4, 0) + _varint(0)          # batch_index
    return bytes(body)


def decode_migration(payload: bytes) -> dict:
    entries = []
    version = batch_size = batch_index = None
    for f, wt, v in _iter_fields(payload):
        if f == 1 and wt == 2:
            e = {"name": "", "issuer": "", "algorithm": 1, "digits": 1,
                 "type": 2, "counter": 0, "secret_bytes": b""}
            for f2, wt2, v2 in _iter_fields(v):
                if f2 == 1 and wt2 == 2:
                    e["secret_bytes"] = v2
                elif f2 == 2 and wt2 == 2:
                    e["name"] = v2.decode("utf-8", "replace")
                elif f2 == 3 and wt2 == 2:
                    e["issuer"] = v2.decode("utf-8", "replace")
                elif f2 == 4 and wt2 == 0:
                    e["algorithm"] = v2
                elif f2 == 5 and wt2 == 0:
                    e["digits"] = v2
                elif f2 == 6 and wt2 == 0:
                    e["type"] = v2
                elif f2 == 7 and wt2 == 0:
                    e["counter"] = v2
            entries.append(e)
        elif f == 2 and wt == 0:
            version = v
        elif f == 3 and wt == 0:
            batch_size = v
        elif f == 4 and wt == 0:
            batch_index = v
    return {"entries": entries, "version": version,
            "batch_size": batch_size, "batch_index": batch_index}


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(s: str) -> bytes:
    s = s.strip().replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s)


def build_migration_uri(entries) -> str:
    return "otpauth-migration://offline?data=" + b64url_encode(encode_migration(entries))


def parse_migration_arg(arg: str) -> dict:
    """接受完整 otpauth-migration:// 链接，或裸 data 载荷（base64）。"""
    arg = arg.strip()
    if arg.lower().startswith("otpauth-migration://"):
        sp = urlsplit(arg)
        q = parse_qs(sp.query, keep_blank_values=True)
        if "data" not in q:
            raise ValueError("迁移链接缺少 data 参数")
        payload = b64url_decode(q["data"][0])
    else:
        payload = b64url_decode(arg)
    return decode_migration(payload)


def entry_to_otpauth_uri(e: dict) -> str:
    otype = ENUM_TO_TYPE.get(e["type"])
    if otype is None:
        raise ValueError(f"未知类型枚举: {e['type']}")
    name = e.get("name") or "account"
    issuer = e.get("issuer") or (name.split(":", 1)[0] if ":" in name else "")
    account = name.split(":", 1)[1] if issuer and name.startswith(issuer + ":") else name
    secret_b32 = base64.b32encode(e["secret_bytes"]).decode("ascii")
    return build_otpauth_uri(otype, issuer, account, secret_b32,
                             ENUM_TO_ALG.get(e["algorithm"], f"enum{e['algorithm']}"),
                             ENUM_TO_DIGITS.get(e["digits"], 6),
                             30, e.get("counter", 0))


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
def cmd_build(args) -> int:
    raw = b32_decode_secret(args.secret)
    uri = build_otpauth_uri(args.type, args.issuer, args.account,
                            "".join(args.secret.split()).replace("-", "").upper().rstrip("="),
                            args.algorithm, args.digits, args.period, args.counter)
    info = {
        "uri": uri,
        "type": args.type,
        "issuer": args.issuer or None,
        "account": args.account,
        "secret_base32": "".join(args.secret.split()).replace("-", "").upper().rstrip("="),
        "secret_hex": raw.hex(),
        "secret_bytes": len(raw),
        "algorithm": args.algorithm,
        "digits": args.digits,
    }
    if args.type == "totp":
        info["period"] = args.period
    else:
        info["counter"] = args.counter
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(uri)
    return 0


def _fmt_entry(e: dict) -> list:
    t = e["type"]
    alg = e["algorithm"]
    rows = [
        "name:      " + e.get("name", ""),
        "issuer:    " + (e.get("issuer", "") or "-"),
        "type:      " + ENUM_TO_TYPE.get(t, "enum%d" % t),
        "algorithm: " + ENUM_TO_ALG.get(alg, "enum%d" % alg),
        "digits:    " + str(ENUM_TO_DIGITS.get(e["digits"], "?")),
        "counter:   " + (str(e.get("counter", 0)) if t == 1 else "-"),
        "secret:    " + base64.b32encode(e["secret_bytes"]).decode("ascii"),
        "secret_hex:" + (" " + e["secret_bytes"].hex() if e["secret_bytes"] else " (空)"),
    ]
    return rows


def cmd_parse(args) -> int:
    out = []
    for uri in args.uri:
        p = parse_otpauth_uri(uri)
        p["secret_hex"] = p.pop("secret_bytes").hex()
        out.append(p)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    for p in out:
        print(f"type:      {p['type']}")
        print(f"label:     {p['label']}")
        print(f"label_issuer: {p['label_issuer'] or '-'}")
        print(f"issuer(query): {p['issuer'] or '-'}")
        print(f"account:   {p['account']}")
        print(f"secret:    {p['secret']}  ({len(p['secret_hex']) // 2} 字节)")
        print(f"algorithm: {p['algorithm']}")
        print(f"digits:    {p['digits']}")
        if p["type"] == "totp":
            print(f"period:    {p['period']}")
        else:
            print(f"counter:   {p['counter']}")
        print()
    return 0


def cmd_mig_build(args) -> int:
    if args.file:
        text = sys.stdin.read() if args.file == "-" else open(args.file, "r", encoding="utf-8").read()
    elif args.uris:
        text = args.uris
    else:
        print("错误: 需要 --file PATH(- 为 stdin) 或 --uris", file=sys.stderr)
        return 2
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = parse_otpauth_uri(line)
        name = f"{p['issuer']}:{p['account']}" if p["issuer"] else p["label"]
        e = {
            "name": name,
            "issuer": p["issuer"] or "",
            "type": p["type"],
            "algorithm": p["algorithm"],
            "digits": p["digits"],
            "counter": p.get("counter", 0),
            "secret_bytes": p["secret_bytes"],
        }
        entries.append(e)
    if not entries:
        print("错误: 未读到任何 otpauth:// 链接", file=sys.stderr)
        return 2
    print(build_migration_uri(entries))
    return 0


def cmd_mig_parse(args) -> int:
    arg = args.migration
    if arg == "-":  # '-' 表示从 stdin 读取迁移串
        arg = sys.stdin.read()
    d = parse_migration_arg(arg)
    meta = {"version": d["version"], "batch_size": d["batch_size"],
            "batch_index": d["batch_index"], "count": len(d["entries"])}
    if args.json:
        items = []
        for e in d["entries"]:
            it = dict(e)
            it["secret_base32"] = base64.b32encode(it.pop("secret_bytes")).decode("ascii")
            it["type"] = ENUM_TO_TYPE.get(it["type"], it["type"])
            it["algorithm"] = ENUM_TO_ALG.get(it["algorithm"], it["algorithm"])
            it["digits"] = ENUM_TO_DIGITS.get(it["digits"], it["digits"])
            items.append(it)
        print(json.dumps({"meta": meta, "entries": items}, ensure_ascii=False, indent=2))
        return 0
    print(f"version={meta['version']} batch_size={meta['batch_size']} "
          f"batch_index={meta['batch_index']} 条目数={meta['count']}")
    for i, e in enumerate(d["entries"], 1):
        print(f"--- 条目 {i} ---")
        for row in _fmt_entry(e):
            print(row)
        if args.emit_uris:
            print("otpauth:  " + entry_to_otpauth_uri(e))
    return 0


# ---------------------------------------------------------------------------
# 自测
# ---------------------------------------------------------------------------
def _selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}")

    # 1. build: 精确字符串
    uri = build_otpauth_uri("totp", "Example", "alice@example.com",
                            "JBSWY3DPEHPK3PXP", "SHA1", 6, 30, 0)
    check("build totp 精确字符串",
          uri == "otpauth://totp/Example%3Aalice%40example.com?secret=JBSWY3DPEHPK3PXP"
                 "&issuer=Example&algorithm=SHA1&digits=6&period=30")
    uri_hotp = build_otpauth_uri("hotp", "Example", "bob", "JBSWY3DPEHPK3PXP", "SHA1", 6, 30, 5)
    check("build hotp 精确字符串",
          uri_hotp == "otpauth://hotp/Example%3Abob?secret=JBSWY3DPEHPK3PXP"
                      "&issuer=Example&counter=5&algorithm=SHA1&digits=6")

    # 2. parse 往返
    p = parse_otpauth_uri(uri)
    check("parse totp 字段", p["type"] == "totp" and p["issuer"] == "Example"
          and p["account"] == "alice@example.com"
          and p["secret"] == "JBSWY3DPEHPK3PXP"
          and p["secret_bytes"] == base64.b32decode("JBSWY3DPEHPK3PXP")
          and p["algorithm"] == "SHA1" and p["digits"] == 6 and p["period"] == 30)
    p2 = parse_otpauth_uri(uri_hotp)
    check("parse hotp counter", p2["counter"] == 5 and p2["type"] == "hotp")
    p3 = parse_otpauth_uri(build_otpauth_uri(
        "totp", "", "noreply@example.com",
        base64.b32encode(bytes(range(20))).decode(), "SHA256", 8, 60, 0))
    check("parse 无 issuer + SHA256/8位/60s",
          p3["issuer"] is None and p3["algorithm"] == "SHA256"
          and p3["digits"] == 8 and p3["period"] == 60)

    # 3. 迁移串: 手工构造的 protobuf 字节（不经过本工具编码器）验证解码器
    secret = b"12345678"
    name = "Demo:alice@example.com"
    manual_params = (b"\x0a\x08" + secret
                     + b"\x12\x16" + name.encode()
                     + b"\x1a\x04Demo"
                     + b"\x20\x01"      # algorithm = SHA1(1)
                     + b"\x28\x01"      # digits = SIX(1)
                     + b"\x30\x02")     # type = TOTP(2)
    manual_payload = (b"\x0a" + bytes([len(manual_params)]) + manual_params
                      + b"\x10\x01"    # version = 1
                      + b"\x18\x01"    # batch_size = 1
                      + b"\x20\x00")   # batch_index = 0
    d = decode_migration(manual_payload)
    e = d["entries"][0]
    check("解码手工迁移载荷",
          len(d["entries"]) == 1 and e["secret_bytes"] == secret
          and e["name"] == name and e["issuer"] == "Demo"
          and e["algorithm"] == 1 and e["digits"] == 1 and e["type"] == 2
          and d["version"] == 1 and d["batch_size"] == 1 and d["batch_index"] == 0)

    # 4. 编码器输出与手工字节完全一致
    mine = encode_migration([{"name": name, "issuer": "Demo", "type": "totp",
                              "algorithm": "SHA1", "digits": 6, "counter": 0,
                              "secret_bytes": secret}])
    check("编码器输出 == 手工 protobuf 字节", mine == manual_payload)

    # 5. 迁移 URI 往返（含大 counter 与 SHA512/8 位）
    big = {"name": "Big:c@d", "issuer": "Big", "type": "hotp",
           "algorithm": "SHA512", "digits": 8, "counter": 2 ** 40,
           "secret_bytes": bytes(range(32))}
    d2 = decode_migration(encode_migration([big]))
    e2 = d2["entries"][0]
    check("大 counter(2^40)/SHA512/8位 往返",
          e2["counter"] == 2 ** 40 and e2["algorithm"] == 3 and e2["digits"] == 2
          and e2["type"] == 1 and e2["secret_bytes"] == bytes(range(32)))
    mig_uri = build_migration_uri([big])
    check("迁移 URI 前缀", mig_uri.startswith("otpauth-migration://offline?data="))
    d3 = parse_migration_arg(mig_uri)
    check("迁移 URI 解析还原", d3["entries"][0]["secret_bytes"] == bytes(range(32)))

    # 6. 多条目: build -> parse -> emit -> 与原 URI 一致
    uris = [uri, uri_hotp]
    ent = []
    for u in uris:
        pp = parse_otpauth_uri(u)
        ent.append({"name": f"{pp['issuer']}:{pp['account']}" if pp["issuer"] else pp["label"],
                    "issuer": pp["issuer"] or "", "type": pp["type"],
                    "algorithm": pp["algorithm"], "digits": pp["digits"],
                    "counter": pp.get("counter", 0), "secret_bytes": pp["secret_bytes"]})
    d4 = parse_migration_arg(build_migration_uri(ent))
    emitted = [entry_to_otpauth_uri(e) for e in d4["entries"]]
    check("多条目迁移 build->parse->emit 与原 URI 一致", emitted == uris)

    # 7. varint 边界
    for n in (0, 1, 127, 128, 16383, 16384, 2 ** 32, 2 ** 63 - 1):
        v, i = _read_varint(_varint(n), 0)
        if v != n or i != len(_varint(n)):
            check(f"varint {n}", False)
            break
    else:
        check("varint 边界值编码/解码", True)

    # 8. 异常输入报错
    try:
        parse_otpauth_uri("https://example.com/x")
        check("非 otpauth 链接报错", False)
    except ValueError:
        check("非 otpauth 链接报错", True)
    try:
        b32_decode_secret("abc1")  # 1 不是 base32 字母表
        check("非法 base32 报错", False)
    except ValueError:
        check("非法 base32 报错", True)

    failed = [n for n, ok in checks if not ok]
    print(f"\nselftest: {len(checks) - len(failed)}/{len(checks)} 项通过")
    if failed:
        print("失败项:", "; ".join(failed))
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="otpauth-uri.py",
        description="构建/解析 otpauth:// 链接与 otpauth-migration 迁移串。")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="构建 otpauth:// 链接")
    b.add_argument("--type", default="totp", choices=["totp", "hotp"])
    b.add_argument("--issuer", default="", help="发行方（可选）")
    b.add_argument("--account", required=True, help="账号名")
    b.add_argument("--secret", required=True, help="base32 共享密钥")
    b.add_argument("--algorithm", default="SHA1", choices=list(ALG_TO_ENUM))
    b.add_argument("--digits", type=int, default=6, choices=[6, 8])
    b.add_argument("--period", type=int, default=30, help="仅 totp（默认 30 秒）")
    b.add_argument("--counter", type=int, default=0, help="仅 hotp（默认 0）")
    b.add_argument("--json", action="store_true")
    b.set_defaults(func=cmd_build)

    pa = sub.add_parser("parse", help="解析 otpauth:// 链接（可多条）")
    pa.add_argument("uri", nargs="+")
    pa.add_argument("--json", action="store_true")
    pa.set_defaults(func=cmd_parse)

    mb = sub.add_parser("mig-build", help="由 otpauth:// 链接构建迁移串")
    mb.add_argument("--file", help="每行一条 otpauth:// 链接；'-' 读 stdin")
    mb.add_argument("--uris", help="直接给定链接文本（换行分隔）")
    mb.set_defaults(func=cmd_mig_build)

    mp = sub.add_parser("mig-parse", help="解析 otpauth-migration:// 迁移串")
    mp.add_argument("migration", help="迁移链接或裸 data 载荷(base64)")
    mp.add_argument("--emit-uris", action="store_true", help="同时还原输出 otpauth:// 链接")
    mp.add_argument("--json", action="store_true")
    mp.set_defaults(func=cmd_mig_parse)

    st = sub.add_parser("selftest", help="运行内置自测")
    st.set_defaults(func=lambda a: _selftest())
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"IO 错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
