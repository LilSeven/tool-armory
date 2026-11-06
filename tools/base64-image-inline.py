"""图片转 data URI —— 把图片文件转成 data:image/png;base64,... 内联字符串。

用途:
    读取图片文件, 根据扩展名推断 MIME 类型(可用 --mime 覆盖), 对文件内容做
    Base64 编码, 拼成可直接粘贴进 HTML/CSS 的 data URI 输出。
    默认输出单行完整 URI; --wrap 仅作展示用折行(复制嵌入请用单行)。

示例命令:
    python base64-image-inline.py logo.png
    python base64-image-inline.py avatar.jpg --out uri.txt
    python base64-image-inline.py icon.svg --mime image/svg+xml
    python base64-image-inline.py photo.png --wrap 100

退出码: 0 成功; 1 文件不存在或读取失败; 2 参数错误。

仅依赖 Python 标准库。
"""

import argparse
import base64
import mimetypes
import pathlib
import sys

MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".jfif": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".svgz": "image/svg+xml",
    ".ico": "image/x-icon",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".avif": "image/avif",
}


def guess_mime(path):
    """优先按扩展名查表, 再退回 mimetypes 推断; 都失败则报错。"""
    mime = MIME_BY_EXT.get(path.suffix.lower())
    if mime:
        return mime
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed and guessed.startswith("image/"):
        return guessed
    raise ValueError("无法识别图片类型: %s (请用 --mime 显式指定)" % path.name)


def build_data_uri(data, mime):
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))


def wrap_line(s, width):
    return "\n".join(s[i:i + width] for i in range(0, len(s), width))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="把图片文件转成 data:image/...;base64,... 内联字符串")
    parser.add_argument("image", help="图片文件路径")
    parser.add_argument("--mime", help="强制指定 MIME 类型, 如 image/jpeg")
    parser.add_argument("--out", help="把 data URI 写入该文件(默认打印到 stdout)")
    parser.add_argument("--wrap", type=int, default=0,
                        help="按每 N 个字符折行输出(默认 0=单行)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if args.wrap < 0:
        parser.error("--wrap 不能为负数")

    try:
        path = pathlib.Path(args.image)
        if not path.is_file():
            print("错误: 文件不存在或不是普通文件: %s" % path, file=sys.stderr)
            return 1
        data = path.read_bytes()
        mime = args.mime.strip() if args.mime else guess_mime(path)
        uri = build_data_uri(data, mime)
        if args.wrap > 0:
            uri = wrap_line(uri, args.wrap)
        if args.out:
            pathlib.Path(args.out).write_text(uri + "\n", encoding="utf-8")
            print("已写入 %s: mime=%s, 原始 %d 字节, URI %d 字符"
                  % (args.out, mime, len(data), len(uri)), file=sys.stderr)
        else:
            print(uri)
            print("# mime=%s, 原始 %d 字节, URI %d 字符"
                  % (mime, len(data), len(uri)), file=sys.stderr)
        return 0
    except Exception as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
