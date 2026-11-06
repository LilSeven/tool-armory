"""Quoted-Printable 编解码 —— 用标准库 quopri 处理邮件 QP 编码正文(=XX 与软换行)。

用途:
    encode: 把文本编码为 Quoted-Printable(RFC 2045): 非 ASCII/控制字符与 '='
            变成 =XX, 超过 76 列自动插入行尾软换行 '=', 行尾空格/制表符也被编码。
    decode: 把 QP 文本还原为原始字节: =XX 还原为对应字节, 行尾的 '='(软换行)
            连同换行符一起移除。解码输出原始字节(可能是 UTF-8 等任意编码),
            终端显示乱码时建议配合 --out 落盘。
    说明: 当输入本身不以换行结尾时, 编码会去掉 quopri 按行约定补在末尾的换行,
    以便结果可以继续当字符串使用; 解码是宽松的, 非法的 '=' 序列按原样保留。

示例命令:
    python quoted-printable-tool.py encode --string "你好, = world!"
    python quoted-printable-tool.py decode --string "caf=C3=A9 =\r\nbar"
    python quoted-printable-tool.py encode --in body.txt --out body.qp
    python quoted-printable-tool.py decode --in body.qp --out body.txt
    cat body.qp | python quoted-printable-tool.py decode

退出码: 0 成功; 1 输入读取失败; 2 参数错误。

仅依赖 Python 标准库。
"""

import argparse
import pathlib
import quopri
import sys


def read_bytes(args):
    if args.string is not None:
        return args.string.encode("utf-8")
    path = args.in_file or args.file
    if path:
        return pathlib.Path(path).read_bytes()
    if sys.stdin.isatty():
        raise ValueError("没有输入: 请用 --string、--in/位置参数文件或 stdin 提供内容")
    return sys.stdin.buffer.read()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Quoted-Printable 编解码(邮件正文 QP, 处理 =XX 转义与行尾软换行)")
    parser.add_argument("mode", choices=("encode", "decode"),
                        help="encode=编码, decode=解码")
    parser.add_argument("file", nargs="?", help="输入文件(省略则读 stdin)")
    parser.add_argument("--string", help="直接传入内容(字符串, 按 UTF-8 编码)")
    parser.add_argument("--in", dest="in_file", help="输入文件路径(优先于位置参数)")
    parser.add_argument("--out", help="输出文件路径(默认写 stdout)")
    parser.add_argument("--quote-tabs", action="store_true",
                        help="编码时把正文中的空格/制表符也转成 =XX(默认只编码行尾的)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    try:
        data = read_bytes(args)
    except Exception as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1

    if args.mode == "encode":
        out = quopri.encodestring(data, quotetabs=args.quote_tabs)
        if data and not data.endswith(b"\n") and out.endswith(b"\n"):
            out = out[:-1]  # quopri 总是给最后一行补换行, 输入无换行时去掉
    else:
        out = quopri.decodestring(data)

    if args.out:
        pathlib.Path(args.out).write_bytes(out)
    else:
        sys.stdout.flush()
        sys.stdout.buffer.write(out)
        sys.stdout.buffer.flush()
    print("\n[%s 完成] 输入 %d 字节 -> 输出 %d 字节%s"
          % (args.mode, len(data), len(out),
             ", 已写入 %s" % args.out if args.out else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
