#!/usr/bin/env python3
"""htpasswd {SHA} 口令条目生成器（Apache 兼容）。

用途：
    生成 Apache htpasswd 可用的 {SHA} 口令哈希条目，格式为
        user:{SHA}<base64(sha1(password))>
    等价于 `htpasswd -s`（无盐 SHA1）；也可校验既有条目是否匹配。
    注意：{SHA} 无盐、强度有限，生产环境建议 bcrypt/argon2（需第三方库）。

示例命令：
    python htpasswd-gen.py --selftest
    python htpasswd-gen.py alice "s3cret P@ss"       # 生成条目
    python htpasswd-gen.py alice                     # 交互式隐藏输入口令
    printf 's3cret P@ss\\n' | python htpasswd-gen.py alice --stdin
    python htpasswd-gen.py alice "s3cret P@ss" \\
        --verify "alice:{SHA}W6ph5Mm5Pz8GgiULbPgzG37mj9g="

退出码：0 成功/校验通过；1 校验失败；2 参数或输入错误。
"""

import argparse
import base64
import getpass
import hashlib
import hmac
import sys


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def sha_entry(password: str) -> str:
    digest = hashlib.sha1(password.encode("utf-8")).digest()
    return "{SHA}" + base64.b64encode(digest).decode("ascii")


def verify_entry(entry: str, password: str) -> bool:
    entry = entry.strip()
    if ":" in entry:                       # 允许传入整行 htpasswd 条目
        entry = entry.split(":", 1)[1].strip()
    if not entry.startswith("{SHA}"):
        return False
    want = entry[len("{SHA}"):].strip()
    got = base64.b64encode(hashlib.sha1(password.encode("utf-8")).digest())
    return hmac.compare_digest(want.encode("ascii"), got)


def check_username(username: str) -> str:
    if not username:
        raise ValueError("用户名不能为空")
    if ":" in username:
        raise ValueError("用户名不能包含冒号")
    if username != username.strip() or any(c in "\r\n\t" for c in username):
        raise ValueError("用户名不能含首尾空白或制表/换行符")
    return username


def selftest() -> int:
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok = ok and cond
        print(f"[{'PASS' if cond else 'FAIL'}] {name}"
              + (f"：{detail}" if detail else ""))

    check("已知向量 password → {SHA}W6ph5Mm5Pz8GgiULbPgzG37mj9g=",
          sha_entry("password") == "{SHA}W6ph5Mm5Pz8GgiULbPgzG37mj9g=",
          sha_entry("password"))
    entry = sha_entry("s3cret P@ss")
    check("自生成条目可校验通过", verify_entry(entry, "s3cret P@ss"), entry)
    check("整行条目（含用户名前缀）可校验通过",
          verify_entry("alice:" + entry, "s3cret P@ss"))
    check("错误口令校验失败", not verify_entry(entry, "wrong"))
    check("非 {SHA} 条目校验失败", not verify_entry("$apr1$xxxx", "x"))
    raw = base64.b64decode(entry[len("{SHA}"):])
    check("base64 解码后为 20 字节 SHA1 摘要", len(raw) == 20)
    try:
        check_username("bad:name")
        check("含冒号用户名被拒绝", False)
    except ValueError:
        check("含冒号用户名被拒绝", True)
    print("selftest:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


def main(argv=None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(
        description="生成 Apache htpasswd 的 {SHA} 口令条目（等价 htpasswd -s）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("username", nargs="?", help="用户名（不能含冒号）")
    ap.add_argument("password", nargs="?", help="口令；缺省时交互式隐藏输入")
    ap.add_argument("--stdin", action="store_true", help="从 stdin 第一行读口令")
    ap.add_argument("--verify", metavar="ENTRY",
                    help="校验模式：核对口令与既有条目（可为 user:{SHA}... 或 {SHA}...）")
    args = ap.parse_args(argv)

    try:
        if args.selftest:
            return selftest()
        if args.verify is not None:
            if args.password is None:
                ap.error("校验模式需要提供口令参数")
            ok = verify_entry(args.verify, args.password)
            print("校验通过" if ok else "校验失败：口令不匹配")
            return 0 if ok else 1
        if not args.username:
            ap.error("请提供用户名（或使用 --selftest）")
        if args.password is not None and args.stdin:
            ap.error("--stdin 与位置参数口令只能二选一")
        if args.stdin:
            password = sys.stdin.readline().rstrip("\r\n")
        elif args.password is not None:
            password = args.password
        else:
            password = getpass.getpass(f"Password for {args.username}: ")
        if not password:
            print("错误：口令为空", file=sys.stderr)
            return 2
        user = check_username(args.username)
        print(f"{user}:{sha_entry(password)}")
        return 0
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
