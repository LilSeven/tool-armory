#!/usr/bin/env python3
"""口令泄露库核查（Have I Been Pwned，k-匿名查询）。

用途：
    对口令计算 SHA-1，仅把前 5 个十六进制字符（k-匿名前缀）发送到
    Have I Been Pwned 的 Pwned Passwords API；在返回的后缀列表中于本地
    比对完整哈希的后 35 位，判断口令是否出现在公开泄露库中。
    口令明文与完整哈希都不会离开本机。

示例命令：
    python hibp-check.py 'MySecret123!'        # 检查单个口令
    python hibp-check.py 'pw-one' 'pw-two'     # 批量检查多个口令
    echo 'MySecret123!' | python hibp-check.py --stdin
    python hibp-check.py                       # 隐藏式输入口令
    python hibp-check.py --self-test           # 离线自测（不联网）

退出码：
    0 = 查询成功且全部口令未泄露（或离线自测通过）
    1 = 至少一个口令出现在泄露库中
    2 = 参数错误或网络/服务异常

仅依赖 Python 标准库：hashlib / urllib.request / argparse / getpass。
"""

import argparse
import getpass
import hashlib
import sys
import urllib.error
import urllib.request

API_URL = "https://api.pwnedpasswords.com/range/{}"
DEFAULT_TIMEOUT = 15.0
USER_AGENT = "hibp-check-stdlib-cli/1.0"
HEX_DIGITS = set("0123456789ABCDEF")


def sha1_hex(text):
    """Return the uppercase SHA-1 hex digest of text (UTF-8 encoded)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest().upper()


def fetch_range(prefix, timeout=DEFAULT_TIMEOUT):
    """Fetch the raw 'SUFFIX:COUNT' body for a 5-char hash prefix from HIBP."""
    if len(prefix) != 5 or any(ch not in HEX_DIGITS for ch in prefix):
        raise ValueError("prefix must be exactly 5 uppercase hex characters")
    request = urllib.request.Request(
        API_URL.format(prefix),
        headers={"User-Agent": USER_AGENT, "Accept": "text/plain"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise OSError("unexpected HTTP status %s from %s"
                          % (status, API_URL.format(prefix)))
        return response.read().decode("utf-8", errors="replace")


def parse_suffixes(body):
    """Parse an API response body into {35-char suffix: count}."""
    suffixes = {}
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        suffix, sep, count = line.partition(":")
        suffix = suffix.strip().upper()
        count = count.strip()
        if (not sep or len(suffix) != 35
                or any(ch not in HEX_DIGITS for ch in suffix)
                or not count.isdigit()):
            raise ValueError("malformed API response line: %r" % line)
        suffixes[suffix] = int(count)
    return suffixes


def pwn_count(password, timeout=DEFAULT_TIMEOUT, fetch=fetch_range):
    """k-anonymized lookup; returns how many times the password was seen."""
    digest = sha1_hex(password)
    prefix, suffix = digest[:5], digest[5:]
    return parse_suffixes(fetch(prefix, timeout)).get(suffix, 0)


def masked(password):
    """Mask all but the first two characters of a password for display."""
    if len(password) <= 2:
        return "*" * len(password)
    return password[:2] + "*" * (len(password) - 2)


def self_test():
    """Offline self-test: hash vectors, prefix split, parsing, fake lookup."""
    print("hibp-check offline self-test (no network)")
    failures = []

    def check(name, condition):
        print("  %-44s %s" % (name, "PASS" if condition else "FAIL"))
        if not condition:
            failures.append(name)

    for text, expected in (
        ("", "DA39A3EE5E6B4B0D3255BFEF95601890AFD80709"),
        ("abc", "A9993E364706816ABA3E25717850C26C9CD0D89D"),
        ("password", "5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8"),
    ):
        check("sha1 known-answer %r" % text, sha1_hex(text) == expected)

    digest = sha1_hex("password")
    check("prefix is first 5 hex chars",
          digest[:5] == "5BAA6" and len(digest[5:]) == 35)

    body = "%s:1234\r\n%s:1\r\n" % (digest[5:], "0" * 35)
    try:
        parsed = parse_suffixes(body)
        check("parse SUFFIX:COUNT body",
              parsed.get(digest[5:]) == 1234 and len(parsed) == 2)
    except ValueError as exc:
        check("parse SUFFIX:COUNT body (%s)" % exc, False)

    check("k-anonymized lookup via fake transport",
          pwn_count("password", fetch=lambda prefix, timeout: body) == 1234)
    check("absent password yields count 0",
          pwn_count("not-in-fake-body-9x8y",
                    fetch=lambda prefix, timeout: body) == 0)

    try:
        parse_suffixes("TOOSHORT:3")
        check("malformed line raises ValueError", False)
    except ValueError:
        check("malformed line raises ValueError", True)

    print("SELF-TEST %s" % ("PASSED" if not failures else "FAILED: %s" % failures))
    return 0 if not failures else 2


def main(argv=None):
    try:
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        prog="hibp-check",
        description="Check passwords against the Have I Been Pwned breach corpus "
                    "using k-anonymity (only the 5-char SHA-1 prefix is sent).")
    parser.add_argument("passwords", nargs="*", help="password(s) to check")
    parser.add_argument("--stdin", action="store_true",
                        help="read one password per line from stdin instead of argv")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="network timeout in seconds (default %(default)s)")
    parser.add_argument("--self-test", action="store_true",
                        help="run offline self-tests and exit (no network access)")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    passwords = list(args.passwords)
    if args.stdin:
        passwords.extend(line.strip("\r\n") for line in sys.stdin if line.strip())
    if not passwords:
        try:
            passwords.append(getpass.getpass("Password to check (input hidden): "))
        except Exception as exc:  # no tty available
            print("error: no password given (%s)" % exc, file=sys.stderr)
            return 2
    if not passwords or all(pw == "" for pw in passwords):
        print("error: empty password", file=sys.stderr)
        return 2

    any_pwned = False
    try:
        for index, password in enumerate(passwords, 1):
            count = pwn_count(password, timeout=args.timeout)
            verdict = ("PWNED  - seen %d time(s) in known breaches" % count
                       if count else "CLEAN  - not found in known breaches")
            print("[%d] %s  sha1-prefix=%s  %s"
                  % (index, masked(password), sha1_hex(password)[:5], verdict))
            any_pwned = any_pwned or bool(count)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("error: HIBP query failed: %s" % exc, file=sys.stderr)
        return 2
    return 1 if any_pwned else 0


if __name__ == "__main__":
    sys.exit(main())
