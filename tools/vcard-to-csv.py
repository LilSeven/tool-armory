#!/usr/bin/env python3
"""vCard 转 CSV：解析 .vcf 联系人文件的基本字段（FN/N/TEL/EMAIL/ORG 等），输出为 CSV。

用法:
    python vcard-to-csv.py input.vcf -o output.csv
    python vcard-to-csv.py input.vcf              # 输出到 stdout

说明:
    - 支持 vCard 2.1/3.0/4.0 基本语法：BEGIN/END 卡片、属性参数、
      quoted-printable 与 base64 编码值、反斜杠转义。
    - 每个联系人一行；多值字段（多个 TEL/EMAIL）用 " | " 连接。
    - CSV 列: FN, N, NICKNAME, TEL, EMAIL, ORG, TITLE, ADR, URL, NOTE, BDAY

示例:
    python vcard-to-csv.py contacts.vcf -o contacts.csv
"""

import argparse
import base64
import csv
import quopri
import sys

COLUMNS = ["FN", "N", "NICKNAME", "TEL", "EMAIL", "ORG", "TITLE", "ADR", "URL", "NOTE", "BDAY"]

BS = chr(92)  # 反斜杠


def _unescape(value):
    """vCard 文本转义还原：反斜杠n 反斜杠N 反斜杠, 反斜杠; 反斜杠反斜杠"""
    value = value.replace(BS + BS, chr(0))
    value = value.replace(BS + "n", "\n").replace(BS + "N", "\n")
    value = value.replace(BS + ",", ",").replace(BS + ";", ";")
    return value.replace(chr(0), BS)


def _decode_value(value, params):
    enc = ""
    charset = "utf-8"
    for p in params:
        pl = p.lower()
        if pl.startswith("encoding="):
            pl = pl[len("encoding="):]
        if pl in ("quoted-printable", "b", "base64", "8bit"):
            enc = pl
        elif pl.startswith("charset="):
            charset = p.split("=", 1)[1]
    if enc == "quoted-printable":
        raw = value.encode("latin-1", "replace")
        try:
            return quopri.decodestring(raw).decode(charset, "replace")
        except Exception:
            return value
    if enc in ("b", "base64"):
        try:
            return base64.b64decode(value).decode(charset, "replace")
        except Exception:
            return value
    return value


def parse_vcf(text):
    # 预处理：按逻辑行折叠（以空格/制表符开头的行是续行）
    phys = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = []
    for line in phys:
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)

    contacts = []
    cur = None
    pending_qp = False  # 2.1 quoted-printable 跨行
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if upper.startswith("BEGIN:VCARD"):
            cur = {}
            pending_qp = False
            continue
        if upper.startswith("END:VCARD"):
            if cur is not None:
                contacts.append(cur)
            cur = None
            continue
        if cur is None:
            continue

        if pending_qp:
            # 续接 quoted-printable 值（累加器存放在 __qp_key__ 指向的元组键下）
            key = cur.get("__qp_key__")
            if key is not None:
                piece = stripped
                cont = piece.endswith("=")
                if cont:
                    piece = piece[:-1]
                cur[key] = cur.get(key, "") + piece
                if not cont:
                    done = _decode_value(cur[key], cur.get("__qp_params__", []))
                    keyname, params = key
                    cur.pop("__qp_key__", None)
                    cur.pop("__qp_params__", None)
                    cur.pop(key, None)
                    pending_qp = False
                    _store(cur, keyname, params, done)
            continue

        if ":" not in line:
            continue
        head, _, value = line.partition(":")
        if ";" in head:
            keyname, *params = head.split(";")
        else:
            keyname, params = head, []
        keyname = keyname.strip().upper()

        raw_params = list(params)
        is_qp = any(p.upper().replace("ENCODING=", "") == "QUOTED-PRINTABLE"
                    for p in raw_params)
        if is_qp and value.endswith("="):
            # 2.1 QP 软断行：先积累，后续行续接
            pending_qp = True
            key = (keyname, raw_params)
            cur["__qp_key__"] = key
            cur["__qp_params__"] = raw_params
            cur[key] = value[:-1]
            continue

        decoded = _decode_value(value, raw_params)
        _store(cur, keyname, raw_params, decoded)
    return contacts


def _store(cur, keyname, params, value):
    value = _unescape(value)
    ptypes = []
    for p in params:
        pl = p.strip().upper()
        if pl.startswith("TYPE="):
            ptypes.extend(t for t in pl[5:].split(",") if t and t != "PREF")
        elif "=" not in p and pl not in ("ENCODING=QUOTED-PRINTABLE", "ENCODING=8BIT", "ENCODING=B"):
            ptypes.append(pl)
    entry = value
    if ptypes:
        entry = "%s (%s)" % (value, "/".join(t.lower() for t in ptypes))
    if keyname in cur:
        cur[keyname] = cur[keyname] + " | " + entry
    else:
        cur[keyname] = entry


def contacts_to_rows(contacts):
    rows = []
    for c in contacts:
        row = {}
        for col in COLUMNS:
            if col == "N":
                # 结构化姓名: Last;First;Middle;Prefix;Suffix -> "Last, First Middle"
                raw = c.get("N", "")
                if raw:
                    parts = raw.split(";")
                    name = " ".join(p for p in parts[1:3] if p).strip()
                    full = ", ".join(x for x in [parts[0].strip(), name] if x)
                    row[col] = full or raw
                else:
                    row[col] = ""
            elif col == "ADR":
                raw = c.get("ADR", "")
                if raw:
                    segs = [s for s in raw.split(";") if s.strip()]
                    row[col] = " ".join(segs)
                else:
                    row[col] = ""
            else:
                row[col] = c.get(col, "")
        rows.append(row)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="vCard(.vcf) 转 CSV")
    ap.add_argument("input", help="输入 .vcf 文件")
    ap.add_argument("-o", "--output", help="输出 CSV 文件（缺省打印到 stdout）")
    args = ap.parse_args(argv)

    with open(args.input, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()

    contacts = parse_vcf(text)
    rows = contacts_to_rows(contacts)

    if args.output:
        out = open(args.output, "w", encoding="utf-8-sig", newline="")
    else:
        out = sys.stdout
    try:
        w = csv.DictWriter(out, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    finally:
        if args.output:
            out.close()
            print("written: %s (%d contacts)" % (args.output, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
