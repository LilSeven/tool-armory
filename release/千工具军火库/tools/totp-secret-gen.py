#!/usr/bin/env python3
"""TOTP 密钥生成器 —— 生成 base32 编码的 TOTP 共享密钥，并输出配套 otpauth:// 链接与二维码字符画。

只用 Python 标准库。内置：
  * 纯 Python QR Code 编码器（ISO/IEC 18004，Model 2，字节模式，版本 1-40，纠错级别 L/M/Q/H）
  * RFC 6238 TOTP 实现（SHA1/SHA256/SHA512），可用 --code 现场验证密钥可用

示例:
  python totp-secret-gen.py                                   # 默认参数生成密钥+链接+二维码
  python totp-secret-gen.py --issuer GitHub --account alice@example.com
  python totp-secret-gen.py --algorithm SHA256 --digits 8 --period 60 --code
  python totp-secret-gen.py --bits 128 --ascii                # 纯 ASCII 二维码（无 Unicode 块字符）
  python totp-secret-gen.py --no-qr --count 3                 # 只要密钥与链接
  python totp-secret-gen.py selftest                          # 内置自测（RFC 6238 测试向量 + QR 结构校验）
"""
import argparse
import base64
import hashlib
import hmac
import itertools
import secrets
import sys
import time

# ---------------------------------------------------------------------------
# QR Code 编码器（遵循 ISO/IEC 18004；字节模式；版本 1-40）
# ---------------------------------------------------------------------------
_QR_ECC_ORD = {"L": 0, "M": 1, "Q": 2, "H": 3}
_QR_ECC_FORMATBITS = (1, 0, 3, 2)  # L M Q H 在格式信息中的 2bit 编码
# [纠错级别][版本] -> 每块纠错码字数（索引 0 为占位）
_QR_ECC_CW_PER_BLOCK = (
    (-1,  7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
    (-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    (-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
)
# [纠错级别][版本] -> 分块数
_QR_NUM_ECC_BLOCKS = (
    (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4,  4,  4,  4,  4,  6,  6,  6,  6,  7,  8,  8,  9,  9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25),
    (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5,  5,  8,  9,  9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49),
    (-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8,  8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),
    (-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81),
)
_QR_MASKS = (
    lambda x, y: (x + y) % 2,
    lambda x, y: y % 2,
    lambda x, y: x % 3,
    lambda x, y: (x + y) % 3,
    lambda x, y: (x // 3 + y // 2) % 2,
    lambda x, y: x * y % 2 + x * y % 3,
    lambda x, y: (x * y % 2 + x * y % 3) % 2,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2,
)


def _qr_raw_modules(ver: int) -> int:
    """版本 ver 的数据模块总数（含余数位）。"""
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        num_align = ver // 7 + 2
        result -= (25 * num_align - 10) * num_align - 55
        if ver >= 7:
            result -= 36
    return result


def _qr_num_data_cw(ver: int, ecl_ord: int) -> int:
    return _qr_raw_modules(ver) // 8 \
        - _QR_ECC_CW_PER_BLOCK[ecl_ord][ver] * _QR_NUM_ECC_BLOCKS[ecl_ord][ver]


def _qr_align_pos(ver: int) -> list:
    if ver == 1:
        return []
    num_align = ver // 7 + 2
    step = (ver * 8 + num_align * 3 + 5) // (num_align * 4 - 4) * 2
    result = [ver * 4 + 10 - i * step for i in range(num_align - 1)] + [6]
    return list(reversed(result))


def _gf_mul(x: int, y: int) -> int:
    """GF(2^8/0x11D) 乘法。"""
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> bytes:
    result = bytearray([0] * (degree - 1) + [1])
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return bytes(result)


def _rs_remainder(data: bytes, divisor: bytes) -> bytes:
    result = bytearray([0] * len(divisor))
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return bytes(result)


def _qr_interleave(data: bytes, ver: int, ecl_ord: int) -> bytes:
    """数据码字 -> 分块加 RS 纠错 -> 按列交织成最终码字序列。"""
    nb = _QR_NUM_ECC_BLOCKS[ecl_ord][ver]
    elen = _QR_ECC_CW_PER_BLOCK[ecl_ord][ver]
    raw = _qr_raw_modules(ver) // 8
    nshort = nb - raw % nb
    sblen = raw // nb
    blocks = []
    rsdiv = _rs_divisor(elen)
    k = 0
    for i in range(nb):
        dat = bytearray(data[k: k + sblen - elen + (0 if i < nshort else 1)])
        k += len(dat)
        ecc = _rs_remainder(bytes(dat), rsdiv)
        if i < nshort:
            dat.append(0)  # 占位字节，使各块长度一致；输出时跳过
        blocks.append(bytes(dat) + ecc)
    assert k == len(data)
    out = bytearray()
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != sblen - elen or j >= nshort:  # 跳过短块中的占位字节
                out.append(blk[i])
    assert len(out) == raw
    return bytes(out)


def _qr_draw_format(modules, isfn, size, fmtbit, mask):
    def setfn(x, y, dark):
        modules[y][x] = dark
        isfn[y][x] = True

    data = fmtbit << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    bits = (data << 10 | rem) ^ 0x5412
    for i in range(6):
        setfn(8, i, bool(bits >> i & 1))
    setfn(8, 7, bool(bits >> 6 & 1))
    setfn(8, 8, bool(bits >> 7 & 1))
    setfn(7, 8, bool(bits >> 8 & 1))
    for i in range(9, 15):
        setfn(14 - i, 8, bool(bits >> i & 1))
    for i in range(8):
        setfn(size - 1 - i, 8, bool(bits >> i & 1))
    for i in range(8, 15):
        setfn(8, size - 15 + i, bool(bits >> i & 1))
    setfn(8, size - 8, True)  # 恒黑模块


def _qr_draw_version(modules, isfn, size, ver):
    if ver < 7:
        return

    def setfn(x, y, dark):
        modules[y][x] = dark
        isfn[y][x] = True

    rem = ver
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
    bits = ver << 12 | rem
    for i in range(18):
        bit = bool(bits >> i & 1)
        a = size - 11 + i % 3
        b = i // 3
        setfn(a, b, bit)
        setfn(b, a, bit)


def _qr_draw_cw(modules, isfn, size, data):
    """把码字按锯齿形路径填入数据区（跳过功能模块与第 6 列）。"""
    i = 0
    total = len(data) * 8
    for right in range(size - 1, 0, -2):
        if right <= 6:
            right -= 1
        for vert in range(size):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = (size - 1 - vert) if upward else vert
                if not isfn[y][x] and i < total:
                    modules[y][x] = bool((data[i >> 3] >> (7 - (i & 7))) & 1)
                    i += 1
    assert i == total


def _qr_build_matrix(ver, fmtbit, all_cw):
    """构建功能图案并填入码字（未加掩码、格式位为占位 mask 0）。返回 (modules, isfn)。"""
    size = ver * 4 + 17
    modules = [[False] * size for _ in range(size)]
    isfn = [[False] * size for _ in range(size)]

    def setfn(x, y, dark):
        modules[y][x] = dark
        isfn[y][x] = True

    for i in range(size):  # 时序图案
        setfn(6, i, i % 2 == 0)
        setfn(i, 6, i % 2 == 0)

    def finder(cx, cy):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                xx, yy = cx + dx, cy + dy
                if 0 <= xx < size and 0 <= yy < size:
                    setfn(xx, yy, max(abs(dx), abs(dy)) not in (2, 4))

    finder(3, 3)
    finder(size - 4, 3)
    finder(3, size - 4)

    pos = _qr_align_pos(ver)
    n = len(pos)
    for i in range(n):
        for j in range(n):
            if (i, j) in ((0, 0), (0, n - 1), (n - 1, 0)):
                continue  # 三个角落与定位图案重叠，跳过
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    setfn(pos[i] + dx, pos[j] + dy, max(abs(dx), abs(dy)) != 1)

    _qr_draw_format(modules, isfn, size, fmtbit, 0)  # 占位，之后按实际 mask 重画
    _qr_draw_version(modules, isfn, size, ver)
    _qr_draw_cw(modules, isfn, size, all_cw)
    return modules, isfn


def _qr_apply_mask(modules, isfn, mask):
    size = len(modules)
    masker = _QR_MASKS[mask]
    for y in range(size):
        for x in range(size):
            if not isfn[y][x] and masker(x, y) == 0:
                modules[y][x] = not modules[y][x]


def _qr_penalty(modules) -> int:
    """按 ISO 四条规则精确打分（用于自动选 mask；评分方式与参考实现一致）。"""
    from collections import deque

    size = len(modules)
    penalty = 0

    def add_history(run_len, hist):
        if hist[0] == 0:
            run_len += size
        hist.appendleft(run_len)

    def count_patterns(hist):
        n = hist[1]
        core = n > 0 and hist[2] == hist[4] == hist[5] == n and hist[3] == n * 3
        return (1 if core and hist[0] >= n * 4 and hist[6] >= n else 0) \
             + (1 if core and hist[6] >= n * 4 and hist[0] >= n else 0)

    def terminate_and_count(cur_color, cur_len, hist):
        if cur_color:
            add_history(cur_len, hist)
            cur_len = 0
        cur_len += size
        add_history(cur_len, hist)
        return count_patterns(hist)

    for y in range(size):  # 规则 1+3：行
        runcolor = False
        runx = 0
        hist = deque([0] * 7, 7)
        for x in range(size):
            if modules[y][x] == runcolor:
                runx += 1
                if runx == 5:
                    penalty += 3
                elif runx > 5:
                    penalty += 1
            else:
                add_history(runx, hist)
                if not runcolor:
                    penalty += count_patterns(hist) * 40
                runcolor = modules[y][x]
                runx = 1
        penalty += terminate_and_count(runcolor, runx, hist) * 40
    for x in range(size):  # 规则 1+3：列
        runcolor = False
        runy = 0
        hist = deque([0] * 7, 7)
        for y in range(size):
            if modules[y][x] == runcolor:
                runy += 1
                if runy == 5:
                    penalty += 3
                elif runy > 5:
                    penalty += 1
            else:
                add_history(runy, hist)
                if not runcolor:
                    penalty += count_patterns(hist) * 40
                runcolor = modules[y][x]
                runy = 1
        penalty += terminate_and_count(runcolor, runy, hist) * 40
    for y in range(size - 1):  # 规则 2：2x2 同色块
        for x in range(size - 1):
            if modules[y][x] == modules[y][x + 1] == modules[y + 1][x] == modules[y + 1][x + 1]:
                penalty += 3
    dark = sum(1 for row in modules for v in row if v)  # 规则 4：明暗比例
    total = size * size
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    penalty += k * 10
    return penalty


def qr_encode(data: bytes, ecl: str = "M", mask=None, min_version: int = 1):
    """把字节串编码为 QR 码。返回 (modules, info)；modules[y][x] 为 True 表示暗模块。"""
    if not data:
        raise ValueError("编码内容为空")
    if len(data) > 2953:
        raise ValueError("内容超过 QR 版本 40 字节模式上限（2953 字节）")
    e = _QR_ECC_ORD[ecl]
    fmtbit = _QR_ECC_FORMATBITS[e]
    ver = None
    for v in range(min_version, 41):
        cap = _qr_num_data_cw(v, e) * 8
        need = 4 + (8 if v < 10 else 16) + 8 * len(data)
        if need <= cap:
            ver = v
            break
    if ver is None:
        raise ValueError("内容过长，无法编码为 QR（版本 1-40 字节模式）")
    cap = _qr_num_data_cw(ver, e) * 8

    bits = []

    def push(val, n):
        for k in range(n - 1, -1, -1):
            bits.append((val >> k) & 1)

    push(0b0100, 4)                     # 字节模式指示符
    push(len(data), 8 if ver < 10 else 16)  # 字符计数
    for b in data:
        push(b, 8)
    push(0, min(4, cap - len(bits)))    # 终止符
    push(0, -len(bits) % 8)             # 补齐到字节
    for pad in itertools.cycle((0xEC, 0x11)):
        if len(bits) >= cap:
            break
        push(pad, 8)
    data_cw = bytearray(len(bits) // 8)
    for idx, b in enumerate(bits):
        data_cw[idx >> 3] |= b << (7 - (idx & 7))
    all_cw = _qr_interleave(bytes(data_cw), ver, e)

    candidates = [mask] if mask is not None else list(range(8))
    best = None
    for m in candidates:
        modules, isfn = _qr_build_matrix(ver, fmtbit, all_cw)
        _qr_apply_mask(modules, isfn, m)
        _qr_draw_format(modules, isfn, ver * 4 + 17, fmtbit, m)
        score = _qr_penalty(modules) if len(candidates) > 1 else 0
        if best is None or score < best[0]:
            best = (score, m, modules)
    _, m, modules = best
    info = {
        "version": ver,
        "ecl": ecl,
        "mask": m,
        "size": ver * 4 + 17,
        "data_codewords": _qr_num_data_cw(ver, e),
    }
    return modules, info


def qr_render(modules, quiet: int = 3, invert: bool = False, ascii_mode: bool = False) -> str:
    """渲染二维码为终端字符画。默认用 Unicode 半块字符（高宽比约 1:1）；ascii 模式用 '#'。"""
    size = len(modules)
    dim = size + 2 * quiet
    grid = [[False] * dim for _ in range(dim)]
    for y in range(size):
        for x in range(size):
            dark = modules[y][x] != invert
            grid[y + quiet][x + quiet] = dark
    lines = []
    if ascii_mode:
        for row in grid:
            lines.append("".join("##" if c else "  " for c in row).rstrip())
    else:
        for y in range(0, dim, 2):
            top = grid[y]
            bot = grid[y + 1] if y + 1 < dim else [False] * dim
            chars = []
            for a, b in zip(top, bot):
                if a and b:
                    chars.append("█")
                elif a:
                    chars.append("▀")
                elif b:
                    chars.append("▄")
                else:
                    chars.append(" ")
            lines.append("".join(chars).rstrip())
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# RFC 6238 TOTP
# ---------------------------------------------------------------------------
def totp(secret: bytes, when: float, period: int = 30, digits: int = 6, algorithm: str = "SHA1") -> str:
    counter = int(when // period)
    digest = hmac.new(secret, counter.to_bytes(8, "big"), getattr(hashlib, algorithm.lower())).digest()
    off = digest[-1] & 0x0F
    code = ((digest[off] & 0x7F) << 24) | (digest[off + 1] << 16) | (digest[off + 2] << 8) | digest[off + 3]
    return str(code % (10 ** digits)).zfill(digits)


def b32_normalize(s: str) -> str:
    s = "".join(s.split()).upper().rstrip("=")
    return s + "=" * (-len(s) % 8)


def build_otpauth_uri(otype, issuer, account, secret_b32, algorithm, digits, period, counter):
    label = f"{issuer}:{account}" if issuer else account
    params = ["secret=" + secret_b32]
    if issuer:
        from urllib.parse import quote
        params.append("issuer=" + quote(issuer, safe=""))
    if otype == "hotp":
        params.append(f"counter={counter}")
    params.append(f"algorithm={algorithm}")
    params.append(f"digits={digits}")
    if otype == "totp":
        params.append(f"period={period}")
    from urllib.parse import quote
    return f"otpauth://{otype}/{quote(label, safe='')}?" + "&".join(params)


# ---------------------------------------------------------------------------
# 主功能
# ---------------------------------------------------------------------------
def gen_secret(bits: int):
    raw = secrets.token_bytes(bits // 8)
    b32 = base64.b32encode(raw).decode("ascii")
    return raw, b32


def one_block(args, index=None):
    account = args.account
    if args.count > 1 and index is not None:
        account = f"{account}-{index + 1}"
    raw, b32 = gen_secret(args.bits)
    uri = build_otpauth_uri("totp", args.issuer, account, b32, args.algorithm,
                            args.digits, args.period, 0)
    lines = []
    lines.append(f"secret (base32): {b32}")
    lines.append(f"secret (hex):    {raw.hex()}")
    lines.append(f"secret (bytes):  {len(raw)}")
    lines.append(f"otpauth URI:")
    lines.append(f"  {uri}")
    if args.code:
        now = time.time()
        code = totp(raw, now, args.period, args.digits, args.algorithm)
        remain = args.period - int(now) % args.period
        lines.append(f"current TOTP:    {code}  (有效约 {remain}s)")
    if not args.no_qr:
        modules, info = qr_encode(uri.encode("utf-8"), args.ecl)
        title = f"QR (version {info['version']}, ECC {info['ecl']}, mask {info['mask']}, {info['size']}x{info['size']}) —— 用验证器 App 扫码:"
        lines.append(title)
        lines.append(qr_render(modules, quiet=args.quiet, invert=args.invert, ascii_mode=args.ascii))
    return "\n".join(lines)


def cmd_main(args) -> int:
    for i in range(args.count):
        if i:
            print()
        print(one_block(args, index=i))
    return 0


# ---------------------------------------------------------------------------
# 自测
# ---------------------------------------------------------------------------
def _selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}")

    # ---- RFC 6238 附录 B 测试向量（种子为 ASCII "1234567890..."）----
    seed20 = b"12345678901234567890"
    seed32 = b"1234567890" * 3 + b"12"          # RFC 6238 32 字节种子
    seed64 = b"1234567890" * 6 + b"1234"        # RFC 6238 64 字节种子
    vectors = [
        (seed20, "SHA1", 59, "94287082"),
        (seed32, "SHA256", 59, "46119246"),
        (seed64, "SHA512", 59, "90693936"),
        (seed20, "SHA1", 1111111109, "07081804"),
        (seed20, "SHA1", 1111111111, "14050471"),
        (seed20, "SHA1", 1234567890, "89005924"),
        (seed20, "SHA1", 2000000000, "69279037"),
        (seed20, "SHA1", 20000000000, "65353130"),
        (seed32, "SHA256", 1111111109, "68084774"),
        (seed64, "SHA512", 1111111109, "25091201"),
        (seed32, "SHA256", 1234567890, "91819424"),
        (seed64, "SHA512", 1234567890, "93441116"),
        (seed32, "SHA256", 2000000000, "90698825"),
        (seed64, "SHA512", 2000000000, "38618901"),
        (seed32, "SHA256", 20000000000, "77737706"),
        (seed64, "SHA512", 20000000000, "47863826"),
    ]
    for seed, algo, t, want in vectors:
        got = totp(seed, t, 30, 8, algo)
        check(f"RFC6238 {algo} T={t} -> {want}", got == want)

    # ---- 密钥生成 ----
    raw1, b321 = gen_secret(160)
    raw2, b322 = gen_secret(160)
    check("base32 长度 = 32 字符", len(b321) == 32)
    check("base32 解码还原", base64.b32decode(b32_normalize(b321)) == raw1)
    check("两次生成不同（随机性）", raw1 != raw2)
    check("位数换算正确", len(raw1) == 20)

    # ---- otpauth URI ----
    uri = build_otpauth_uri("totp", "Example", "alice@example.com",
                            "JBSWY3DPEHPK3PXP", "SHA1", 6, 30, 0)
    check("URI 包含 secret", "secret=JBSWY3DPEHPK3PXP" in uri)
    check("URI 包含 issuer", "issuer=Example" in uri)
    check("URI scheme/type 正确", uri.startswith("otpauth://totp/Example%3A"))

    # ---- QR 结构校验 ----
    def fmtbits_of(modules):
        get = lambda x, y: 1 if modules[y][x] else 0
        bits = 0
        for i in range(6):
            bits |= get(8, i) << i
        bits |= get(8, 7) << 6
        bits |= get(8, 8) << 7
        bits |= get(7, 8) << 8
        for i in range(9, 15):
            bits |= get(14 - i, 8) << i
        return bits

    def zigzag_cells(size):
        """与 _qr_draw_cw 相同顺序遍历数据区坐标。"""
        cells = []
        for right in range(size - 1, 0, -2):
            if right <= 6:
                right -= 1
            for vert in range(size):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = (size - 1 - vert) if upward else vert
                    cells.append((x, y))
        return cells

    def rs_syndrome_zero(block, nsym):
        for i in range(nsym):
            root = 1
            for _ in range(i):
                root = _gf_mul(root, 2)
            acc = 0
            for b in block:
                acc = _gf_mul(acc, root) ^ b
            if acc != 0:
                return False
        return True

    samples = [
        uri.encode("utf-8"),
        b"https://example.com/login?q=" + b"x" * 150,   # 触发多块交织 + 版本信息位
        b"M" * 275,                                     # 触发 v10+（16bit 计数）与多块
        b"hi",                                          # 最小 v1
    ]
    for data in samples:
        for ecl in ("L", "M", "Q", "H"):
            modules, info = qr_encode(data, ecl)
            ver, size, mask = info["version"], info["size"], info["mask"]
            e = _QR_ECC_ORD[ecl]
            ok_shape = len(modules) == size and all(len(r) == size for r in modules)
            # 格式信息 BCH 校验
            b15 = fmtbits_of(modules) ^ 0x5412
            rem = b15 >> 10
            for _ in range(10):
                rem = (rem << 1) ^ ((rem >> 9) * 0x537)
            fmt_ok = (rem & 0x3FF) == (b15 & 0x3FF) and (b15 >> 10) == (_QR_ECC_FORMATBITS[e] << 3 | mask)
            # 重新构建 isfn 以提取码字（生成未加掩码的基准矩阵获得 isfn，并对数据区去掩码）
            fmtbit = _QR_ECC_FORMATBITS[e]
            base_mod, isfn = _qr_build_matrix(
                ver, fmtbit,
                _qr_interleave(_rebuild_data_cw(data, ver, e), ver, e))
            masker = _QR_MASKS[mask]
            plain = [row[:] for row in modules]
            for y in range(size):
                for x in range(size):
                    if not isfn[y][x] and masker(x, y) == 0:
                        plain[y][x] = not plain[y][x]
            raw_cw = _qr_raw_modules(ver) // 8
            extracted = bytearray(raw_cw)
            bitpos = 0
            for (x, y) in zigzag_cells(size):
                if isfn[y][x]:
                    continue
                if bitpos < len(extracted) * 8:
                    if plain[y][x]:
                        extracted[bitpos >> 3] |= 1 << (7 - (bitpos & 7))
                    bitpos += 1
            # 去交织回块并做 RS 校验
            nb = _QR_NUM_ECC_BLOCKS[e][ver]
            elen = _QR_ECC_CW_PER_BLOCK[e][ver]
            nshort = nb - raw_cw % nb
            sblen = raw_cw // nb
            blocks = [bytearray() for _ in range(nb)]
            idx = 0
            for i in range(sblen + 1):
                for j in range(nb):
                    if i != sblen - elen or j >= nshort:
                        blocks[j].append(extracted[idx])
                        idx += 1
            rs_ok = True
            for blk in blocks:
                # 去交织时短块的占位字节已被跳过，blk 即连续的 data||ecc 码字
                if not rs_syndrome_zero(bytes(blk), elen):
                    rs_ok = False
            nonfn_total = sum(1 for (x, y) in zigzag_cells(size) if not isfn[y][x])
            rem_bits = _qr_raw_modules(ver) % 8
            check(f"QR {ecl} len={len(data)} v{ver}: 尺寸/格式BCH/RS校验",
                  ok_shape and fmt_ok and rs_ok
                  and bitpos == raw_cw * 8 and nonfn_total == raw_cw * 8 + rem_bits)

    # ---- 确定性 ----
    m1, _ = qr_encode(b"stable content", "M")
    m2, _ = qr_encode(b"stable content", "M")
    check("同内容输出确定性一致", m1 == m2)

    # ---- 渲染 ----
    art = qr_render(m1)
    art_ascii = qr_render(m1, ascii_mode=True)
    check("Unicode 渲染含块字符", "█" in art or "▀" in art or "▄" in art)
    check("ASCII 渲染仅含 # 和空格", set(art_ascii.replace("\n", "")) <= {"#", " "})

    failed = [n for n, ok in checks if not ok]
    print(f"\nselftest: {len(checks) - len(failed)}/{len(checks)} 项通过")
    if failed:
        print("失败项:", "; ".join(failed))
        return 1
    return 0


def _rebuild_data_cw(data: bytes, ver: int, e: int) -> bytes:
    """自测辅助：重新生成数据码字序列（与 qr_encode 内部一致）。"""
    cap = _qr_num_data_cw(ver, e) * 8
    bits = []

    def push(val, n):
        for k in range(n - 1, -1, -1):
            bits.append((val >> k) & 1)

    push(0b0100, 4)
    push(len(data), 8 if ver < 10 else 16)
    for b in data:
        push(b, 8)
    push(0, min(4, cap - len(bits)))
    push(0, -len(bits) % 8)
    for pad in itertools.cycle((0xEC, 0x11)):
        if len(bits) >= cap:
            break
        push(pad, 8)
    cw = bytearray(len(bits) // 8)
    for idx, b in enumerate(bits):
        cw[idx >> 3] |= b << (7 - (idx & 7))
    return bytes(cw)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def build_parser():
    p = argparse.ArgumentParser(
        prog="totp-secret-gen.py",
        description="生成 base32 编码的 TOTP 共享密钥、配套 otpauth:// 链接与终端二维码字符画。")
    p.add_argument("--issuer", default="MyApp", help="发行方名称（默认 MyApp）")
    p.add_argument("--account", default="user@example.com", help="账号名（默认 user@example.com）")
    p.add_argument("--bits", type=int, default=160, help="密钥位数（默认 160，需为 8 的倍数）")
    p.add_argument("--algorithm", default="SHA1", choices=["SHA1", "SHA256", "SHA512"],
                   help="哈希算法（默认 SHA1）")
    p.add_argument("--digits", type=int, default=6, choices=[6, 8], help="验证码位数（默认 6）")
    p.add_argument("--period", type=int, default=30, help="时间步长秒数（默认 30）")
    p.add_argument("--count", type=int, default=1, help="生成组数（默认 1，上限 100）")
    p.add_argument("--ecl", default="M", choices=["L", "M", "Q", "H"], help="二维码纠错级别（默认 M）")
    p.add_argument("--quiet", type=int, default=3, help="二维码留白边宽（默认 3 模块）")
    p.add_argument("--code", action="store_true", help="同时显示当前时刻的 TOTP 验证码")
    p.add_argument("--ascii", action="store_true", help="二维码用纯 ASCII（'#'/空格）渲染")
    p.add_argument("--invert", action="store_true", help="二维码明暗反转（浅色终端适用）")
    p.add_argument("--no-qr", action="store_true", help="不输出二维码")
    p.add_argument("cmd", nargs="?", choices=["selftest"], help=argparse.SUPPRESS)
    return p


def main(argv=None) -> int:
    _utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "selftest":
        return _selftest()
    if args.bits <= 0 or args.bits % 8 or args.bits > 1024:
        parser.error("--bits 必须是 8 的倍数且不超过 1024")
    if args.count < 1 or args.count > 100:
        parser.error("--count 取值 1..100")
    if args.period < 1:
        parser.error("--period 必须 >= 1")
    return cmd_main(args)


if __name__ == "__main__":
    sys.exit(main())
