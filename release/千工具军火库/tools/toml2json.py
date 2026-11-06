#!/usr/bin/env python3
"""TOML 转 JSON：解析 pyproject.toml 等 TOML 文件并输出 JSON。

Python 3.11+ 优先使用标准库 tomllib；若运行于 3.10 及以下（无 tomllib），
回退到本文件内置的纯标准库 TOML 字符级解析器。内置解析器支持：
  表 [a.b] / 数组表 [[a.b]]、点键与引号键、
  基本字符串 / 字面量字符串 / 三引号多行字符串、
  整数（十进制 / 0x / 0o / 0b / 下划线）、浮点（指数 / inf / nan）、布尔、
  可跨行的数组、内联表、行内与整行注释；
  日期/日期时间按 ISO 8601 字符串输出（tomllib 产出的 date/datetime
  对象经 default=str 后同样是该字符串，两引擎输出一致）。

用法:
    python toml2json.py pyproject.toml           # 输出到 stdout
    python toml2json.py pyproject.toml -o out.json
    cat app.toml | python toml2json.py -

示例命令:
    python toml2json.py pyproject.toml --indent 2
"""
import argparse
import json
import re
import sys

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python <= 3.10
    tomllib = None


# ---------------- 内置 TOML 解析器 (3.10 回退，纯标准库) ----------------

_BARE_KEY_RE = re.compile(r"[A-Za-z0-9_-]+")
_HEX_RE = re.compile(r"[+-]?0[xX][0-9a-fA-F]+|[+-]?0[oO][0-7]+|[+-]?0[bB][01]+")
_DATETIME_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})?)?"
    r"|\d{2}:\d{2}:\d{2}(?:\.\d+)?"
)
_TIME_SUFFIX_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})?"
)
_B_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r",
              '"': '"', "\\": "\\"}


def _unescape_basic(s):
    """解码基本字符串的转义序列（\\b \\t \\n \\f \\r \\" \\\\ \\uXXXX \\UXXXXXXXX）。"""
    out = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        if i + 1 >= n:
            raise ValueError("转义序列不完整")
        e = s[i + 1]
        if e in _B_ESCAPES:
            out.append(_B_ESCAPES[e])
            i += 2
        elif e in ("u", "U"):
            width = 4 if e == "u" else 8
            hexs = s[i + 2:i + 2 + width]
            if len(hexs) < width:
                raise ValueError(f"Unicode 转义 \\{e} 不足 {width} 位十六进制")
            try:
                out.append(chr(int(hexs, 16)))
            except ValueError:
                raise ValueError(f"无效 Unicode 转义: \\{e}{hexs}") from None
            i += 2 + width
        else:
            raise ValueError(f"无效转义序列: \\{e}")
    return "".join(out)


def _skip_spaces(text, i):
    """仅跳过空格与制表符。"""
    n = len(text)
    while i < n and text[i] in " \t":
        i += 1
    return i


def _skip_ws_comments(text, i):
    """跳过空白、换行与注释（数组/内联表内及语句之间允许）。"""
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\n\r":
            i += 1
        elif c == "#":
            while i < n and text[i] != "\n":
                i += 1
        else:
            break
    return i


def _expect_eol(text, i, context):
    """值/表头之后：只允许空白、行内注释或换行/EOF。"""
    n = len(text)
    i = _skip_spaces(text, i)
    if i >= n:
        return i
    c = text[i]
    if c == "\n":
        return i + 1
    if c == "#":
        while i < n and text[i] != "\n":
            i += 1
        return i + 1 if i < n else i
    raise ValueError(f"{context}有多余内容: {text[i:i + 20]!r}")


def _read_quoted(text, i):
    """读取单行引号键名，i 处为引号，返回 (内容, 结束索引)。"""
    q = text[i]
    n = len(text)
    j = i + 1
    buf = []
    while j < n:
        c = text[j]
        if q == '"' and c == "\\":
            if j + 1 >= n:
                raise ValueError("键名转义不完整")
            buf.append(c)
            buf.append(text[j + 1])
            j += 2
            continue
        if c == q:
            body = "".join(buf)
            return (_unescape_basic(body) if q == '"' else body), j + 1
        if c == "\n":
            raise ValueError("键名字符串未闭合")
        buf.append(c)
        j += 1
    raise ValueError("键名字符串未闭合")


def _read_key_path(text, i):
    """读取键路径（点分，允许引号键），返回 (段列表, 结束索引)。"""
    parts = []
    n = len(text)
    while True:
        i = _skip_spaces(text, i)
        if i >= n:
            raise ValueError("键名不完整")
        c = text[i]
        if c in "\"'":
            seg, i = _read_quoted(text, i)
        else:
            m = _BARE_KEY_RE.match(text, i)
            if not m:
                raise ValueError(f"无效键名: {text[i:i + 10]!r}")
            seg = m.group(0)
            i = m.end()
        parts.append(seg)
        i = _skip_spaces(text, i)
        if i < n and text[i] == ".":
            i += 1
            continue
        return parts, i


def _read_basic(text, i):
    """单行基本字符串 "..."。"""
    j = i + 1
    n = len(text)
    buf = []
    while j < n:
        c = text[j]
        if c == '"':
            return _unescape_basic("".join(buf)), j + 1
        if c == "\\":
            if j + 1 >= n:
                raise ValueError("转义序列不完整")
            buf.append(c)
            buf.append(text[j + 1])
            j += 2
            continue
        if c == "\n":
            raise ValueError("基本字符串未闭合（不允许跨行）")
        buf.append(c)
        j += 1
    raise ValueError("基本字符串未闭合")


def _read_literal(text, i):
    """单行字面量字符串 '...'。"""
    j = i + 1
    n = len(text)
    buf = []
    while j < n:
        c = text[j]
        if c == "'":
            return "".join(buf), j + 1
        if c == "\n":
            raise ValueError("字面量字符串未闭合（不允许跨行）")
        buf.append(c)
        j += 1
    raise ValueError("字面量字符串未闭合")


def _read_ml_basic(text, i):
    """多行基本字符串 \"\"\"...\"\"\"（支持行尾反斜杠续行）。"""
    j = i + 3
    n = len(text)
    if j < n and text[j] == "\n":  # 开定界符后紧随的换行被裁剪
        j += 1
    buf = []
    while j < n:
        c = text[j]
        if c == "\\":
            k = j + 1
            if k < n and text[k] in " \t\n":  # 行尾反斜杠：吞掉后续空白与换行
                while k < n and text[k] in " \t\n":
                    k += 1
                j = k
                continue
            if k >= n:
                raise ValueError("转义序列不完整")
            buf.append(c)
            buf.append(text[k])
            j = k + 1
            continue
        if c == '"':
            k = j
            while k < n and text[k] == '"':
                k += 1
            run = k - j
            if run == 3:
                return _unescape_basic("".join(buf)), k
            if run > 3:  # 末 3 个引号是定界符，其余属于内容
                buf.append('"' * (run - 3))
                return _unescape_basic("".join(buf)), k
            buf.append('"' * run)
            j = k
            continue
        buf.append(c)
        j += 1
    raise ValueError("多行基本字符串未闭合")


def _read_ml_literal(text, i):
    """多行字面量字符串 '''...'''。"""
    j = i + 3
    n = len(text)
    if j < n and text[j] == "\n":
        j += 1
    buf = []
    while j < n:
        c = text[j]
        if c == "'":
            k = j
            while k < n and text[k] == "'":
                k += 1
            run = k - j
            if run == 3:
                return "".join(buf), k
            if run > 3:
                buf.append("'" * (run - 3))
                return "".join(buf), k
            buf.append("'" * run)
            j = k
            continue
        buf.append(c)
        j += 1
    raise ValueError("多行字面量字符串未闭合")


def _read_array(text, i):
    """数组 [...]，元素可跨行，元素间/前后允许注释。"""
    j = i + 1
    n = len(text)
    arr = []
    while True:
        j = _skip_ws_comments(text, j)
        if j >= n:
            raise ValueError("数组未闭合")
        if text[j] == "]":
            return arr, j + 1
        v, j = _read_value(text, j)
        arr.append(v)
        j = _skip_ws_comments(text, j)
        if j >= n:
            raise ValueError("数组未闭合")
        if text[j] == ",":
            j += 1
            continue
        if text[j] == "]":
            return arr, j + 1
        raise ValueError(f"数组元素后缺少 ',' 或 ']': {text[j:j + 15]!r}")


def _read_inline(text, i):
    """内联表 {...}。"""
    j = i + 1
    n = len(text)
    tbl = {}
    while True:
        j = _skip_ws_comments(text, j)
        if j >= n:
            raise ValueError("内联表未闭合")
        if text[j] == "}":
            return tbl, j + 1
        parts, j = _read_key_path(text, j)
        j = _skip_spaces(text, j)
        if j >= n or text[j] != "=":
            raise ValueError("内联表键后缺少 '='")
        j += 1
        j = _skip_spaces(text, j)
        v, j = _read_value(text, j)
        d = tbl
        for p in parts[:-1]:
            nxt = d.get(p)
            if isinstance(nxt, dict):
                d = nxt
            elif nxt is None:
                d[p] = {}
                d = d[p]
            else:
                raise ValueError(f"内联表点键路径与已有值冲突: {p}")
        d[parts[-1]] = v
        j = _skip_ws_comments(text, j)
        if j >= n:
            raise ValueError("内联表未闭合")
        if text[j] == ",":
            j += 1
            continue
        if text[j] == "}":
            return tbl, j + 1
        raise ValueError(f"内联表元素后缺少 ',' 或 '}}': {text[j:j + 15]!r}")


def _read_number_or_datetime(text, i):
    """数字 / 日期时间。日期时间按 ISO 字符串返回。"""
    n = len(text)
    j = i
    while j < n and text[j] not in "\n#,]} \t":
        j += 1
    tok = text[i:j]
    # 日期时间允许空格分隔: 1979-05-27 07:32:00
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", tok) and j < n and text[j] == " ":
        m = _TIME_SUFFIX_RE.match(text, j + 1)
        if m:
            tok = tok + " " + m.group(0)
            j = m.end()
    if _DATETIME_RE.fullmatch(tok):
        return tok, j
    low = tok.lower()
    if low in ("inf", "+inf"):
        return float("inf"), j
    if low == "-inf":
        return float("-inf"), j
    if low in ("nan", "+nan", "-nan"):
        return float("nan"), j
    num = tok.replace("_", "")
    try:
        return int(num), j
    except ValueError:
        pass
    if _HEX_RE.fullmatch(num):
        try:
            return int(num, 0), j
        except ValueError:
            pass
    try:
        return float(num), j
    except ValueError:
        pass
    raise ValueError(f"无法解析 TOML 值: {tok!r}")


def _read_value(text, i):
    n = len(text)
    if i >= n:
        raise ValueError("缺少值")
    c = text[i]
    if text.startswith('"""', i):
        return _read_ml_basic(text, i)
    if text.startswith("'''", i):
        return _read_ml_literal(text, i)
    if c == '"':
        return _read_basic(text, i)
    if c == "'":
        return _read_literal(text, i)
    if c == "[":
        return _read_array(text, i)
    if c == "{":
        return _read_inline(text, i)
    if text.startswith("true", i):
        return True, i + 4
    if text.startswith("false", i):
        return False, i + 5
    return _read_number_or_datetime(text, i)


def _descend(root, parts):
    """沿表路径下钻，逐段创建中间表；路径穿过数组表时取最后一个元素。"""
    d = root
    for p in parts:
        cur = d.get(p)
        if isinstance(cur, dict):
            d = cur
        elif isinstance(cur, list):
            if not cur:
                raise ValueError(f"表路径 {p} 指向空的数组表")
            d = cur[-1]
        elif cur is None:
            d[p] = {}
            d = d[p]
        else:
            raise ValueError(f"表路径与已有标量值冲突: {p}")
    return d


def _read_table_header(text, i, root):
    """解析 [a.b] / [[a.b]]，返回 (目标表, 结束索引)。"""
    n = len(text)
    i += 1
    is_array = False
    if i < n and text[i] == "[":
        is_array = True
        i += 1
    parts, i = _read_key_path(text, i)
    i = _skip_spaces(text, i)
    if i >= n or text[i] != "]":
        raise ValueError("表头缺少 ']'")
    i += 1
    if is_array:
        if i < n and text[i] == "]":
            i += 1
        else:
            raise ValueError("[[...]] 缺少第二个 ']'")
    name = ".".join(parts)
    i = _expect_eol(text, i, f"表头 [{name}] 之后")
    parent = _descend(root, parts[:-1])
    last = parts[-1]
    if is_array:
        arr = parent.get(last)
        if arr is None:
            arr = []
            parent[last] = arr
        if not isinstance(arr, list):
            raise ValueError(f"[[{name}]] 与已有值冲突")
        elem = {}
        arr.append(elem)
        return elem, i
    tbl = parent.get(last)
    if tbl is None:
        tbl = {}
        parent[last] = tbl
    if not isinstance(tbl, dict):
        raise ValueError(f"[{name}] 与已有值冲突")
    return tbl, i


def _read_keyval(text, i, current):
    """解析键值对（支持点键），返回结束索引。"""
    parts, i = _read_key_path(text, i)
    i = _skip_spaces(text, i)
    if i >= len(text) or text[i] != "=":
        raise ValueError(f"键 {'.'.join(parts)} 后缺少 '='")
    i += 1
    i = _skip_spaces(text, i)
    value, i = _read_value(text, i)
    i = _expect_eol(text, i, f"键 {'.'.join(parts)} 的值之后")
    d = current
    for p in parts[:-1]:
        nxt = d.get(p)
        if isinstance(nxt, dict):
            d = nxt
        elif nxt is None:
            d[p] = {}
            d = d[p]
        else:
            raise ValueError(f"点键路径与已有值冲突: {p}")
    d[parts[-1]] = value
    return i


def _parse_toml(text):
    """解析 TOML 文本为 dict（纯标准库实现）。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    root = {}
    current = root
    i, n = 0, len(text)
    while True:
        i = _skip_ws_comments(text, i)
        if i >= n:
            return root
        if text[i] == "[":
            current, i = _read_table_header(text, i, root)
        else:
            i = _read_keyval(text, i, current)


# ---------------- 主流程 ----------------

def load_toml(text: str):
    """优先 tomllib（3.11+），否则回退内置解析器。返回 (数据, 引擎名)。"""
    if tomllib is not None:
        return tomllib.loads(text), "tomllib"
    return _parse_toml(text), "fallback"


def main(argv=None):
    # stdout 重定向时 Windows 默认用本地编码(如 GBK)，强制 UTF-8 保证输出可被
    # UTF-8 消费方解析，与 -o 写文件路径 (encoding="utf-8") 保持一致
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        except (ValueError, OSError):
            pass
    ap = argparse.ArgumentParser(description="TOML 文件转 JSON")
    ap.add_argument("input", help="TOML 文件路径，'-' 表示 stdin")
    ap.add_argument("-o", "--output", help="输出 JSON 路径，缺省 stdout")
    ap.add_argument("--indent", type=int, default=2, help="输出缩进 (默认 2)")
    args = ap.parse_args(argv)

    src = sys.stdin if args.input == "-" else open(args.input, encoding="utf-8-sig")
    try:
        text = src.read()
    finally:
        if args.input != "-":
            src.close()

    try:
        data, engine = load_toml(text)
    except Exception as e:
        print(f"toml2json: TOML 解析失败: {e}", file=sys.stderr)
        return 1

    out = open(args.output, "w", encoding="utf-8", newline="\n") if args.output else sys.stdout
    try:
        json.dump(data, out, ensure_ascii=False, indent=args.indent, default=str)
        out.write("\n")
    finally:
        if args.output:
            out.close()
    if engine == "fallback":
        print("# 注: 当前 Python < 3.11，使用了内置 TOML 解析器", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
