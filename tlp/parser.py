# -*- coding: utf-8 -*-
"""TLP Header 解析核心。

支持两种模式：
  * Non-Flit Mode（NFM）：Fmt[2:0] + Type[4:0]，3 或 4 DW 头
  * Flit Mode（FM）：Type[7:0] 决定 Header Base，再叠加 OHC

实现依据见项目根目录 ``TLP_Header_格式解析说明.md``。
"""

from __future__ import annotations

import unicodedata
from typing import List, Optional, Sequence

from . import tables
from .bits import binstr, byte_str, field


# ---------------------------------------------------------------- 输出行模型

class Line(object):
    """一条渲染行。kind 决定 UI 上的样式。"""

    __slots__ = ("kind", "text")

    def __init__(self, kind: str, text: str) -> None:
        self.kind = kind
        self.text = text

    def __repr__(self) -> str:  # pragma: no cover
        return "Line({!r}, {!r})".format(self.kind, self.text)


def title(text: str) -> Line:
    return Line("title", text)


CN_NUM = "一二三四五六七八九十"


def _disp_width(text: str) -> int:
    """按等宽字体下的显示宽度计算（中日韩全角字符算 2 列）。"""
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _pad(text: str, width: int, gap: int = 2) -> str:
    return text + " " * max(width - _disp_width(text), gap)


class Sec(object):
    """自动编号的章节标题。"""

    def __init__(self) -> None:
        self.n = 0

    def __call__(self, name: str) -> Line:
        self.n += 1
        prefix = CN_NUM[self.n - 1] if self.n <= len(CN_NUM) else str(self.n)
        return Line("section", "{}、{}".format(prefix, name))


def kv(name: str, loc: str, value: str, bad: bool = False) -> Line:
    """一条字段行。bad=True 表示该域段的值无法解析（保留编码 / 未定义 / 缺表），UI 会整行标红。"""
    text = _pad("  " + name, 22) + _pad(loc, 22) + value
    return Line("err" if bad else "kv", text)


def note(text: str) -> Line:
    return Line("text", "  " + text)


def warn(text: str) -> Line:
    return Line("warn", "  ! " + text)


def good(text: str) -> Line:
    return Line("good", "  √ " + text)


def blank() -> Line:
    return Line("blank", "")


# ---------------------------------------------------------------- 结果对象

class ParseResult(object):
    def __init__(self, mode: str, lines: List[Line], summary: str = "") -> None:
        self.mode = mode
        self.lines = lines
        self.summary = summary

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def error_count(self) -> int:
        """无法解析的域段行数（kind == 'err'）。"""
        return sum(1 for line in self.lines if line.kind == "err")


# ---------------------------------------------------------------- 公共小工具

# 表里把这些值当作“该编码无法解析”的占位符
_BAD_WORDS = ("保留编码", "Reserved", "保留")


def _lookup(table, key):
    """查编码表并判断是否为保留/未定义编码。返回 (文本, 是否无法解析)。"""
    value = table.get(key)
    if value is None:
        return "保留编码（无法解析）", True
    return value, value in _BAD_WORDS


def _route_of_nfm(type5: int):
    """返回 (路由方式文本, 是否无法判定)。"""
    if type5 == 0x02:
        return "地址路由", False
    if type5 in (0x00, 0x01, 0x1B) or 0x0C <= type5 <= 0x0E:
        return "地址路由", False
    if type5 in (0x04, 0x05):
        return "ID 路由（配置空间）", False
    if type5 in (0x0A, 0x0B):
        return "按 Completer 返回（Completion）", False
    if 0x10 <= type5 <= 0x17:
        text, bad = _lookup(tables.MSG_ROUTING, type5 & 0x07)
        return "隐式 / " + text, bad
    return "无法判定（Type 未定义）", True


def _attr_text(attr: int) -> str:
    parts = []
    for bit, short, long_ in tables.ATTR_BITS:
        if attr & (1 << bit):
            parts.append(short)
    return "{}（{}）".format(binstr(attr, 3), ", ".join(parts) if parts else "全部为 0")


def _be_text(first: int, last: int) -> str:
    return "{} / {}".format(binstr(last, 4), binstr(first, 4))


def _at_desc(at: int):
    """AT[1:0] 的描述。返回 (文本, 是否无法解析)；11b 在规范中是保留编码。"""
    return _lookup(tables.AT_DESC, at)


def _dump(data: Sequence[int], start_dw: int, count: int) -> str:
    """把从 start_dw 开始的 count 个 DW 拼成十六进制串。"""
    end = min(len(data), (start_dw + count) * 4)
    return byte_str(data[start_dw * 4:end])


def _bytes_at(data: Sequence[int], dw: int) -> List[int]:
    """取某个 DW 的 4 个字节；数据不足时补 0（避免 OHC 等区域越界）。"""
    off = dw * 4
    chunk = list(data[off:off + 4])
    if len(chunk) < 4:
        chunk.extend([0] * (4 - len(chunk)))
    return chunk


# ---------------------------------------------------------------- Non-Flit

def parse_nfm(data: Sequence[int], provided_dw: int) -> ParseResult:
    lines: List[Line] = []
    sec = Sec()
    off = 0  # 字节偏移
    prefix_lines: List[Line] = []

    # ---- 前缀（Fmt = 100b）----
    guard = 0
    while off + 4 <= len(data) and (data[off] >> 5) == 0b100 and guard < 8:
        guard += 1
        p_type = data[off] & 0x1F
        key = p_type & 0x0F
        if p_type & 0x10:
            label, table = "End-End Prefix", tables.END_END_PREFIX
        else:
            label, table = "Local Prefix", tables.LOCAL_PREFIX
        pname, p_bad = _lookup(table, key)
        prefix_lines.append(kv(
            "TLP Prefix", "DW{} / byte{}".format(off // 4, off),
            "{}: {}".format(label, pname), bad=p_bad))
        off += 4

    if off + 4 > len(data):
        lines.append(warn("输入数据不足一个 TLP Header（需要至少 1 DW）。"))
        return ParseResult("Non-Flit Mode", lines)

    b = _bytes_at(data, off // 4)
    fmt = b[0] >> 5
    type5 = b[0] & 0x1F
    tc = field(b, 1, 6, 4)
    t9 = field(b, 1, 7, 7)
    t8 = field(b, 1, 3, 3)
    a2 = field(b, 1, 2, 2)
    r_bit = field(b, 1, 1, 1)
    th = field(b, 1, 0, 0)
    td = field(b, 2, 7, 7)
    ep = field(b, 2, 6, 6)
    attr = ((b[2] >> 4) & 0x3) | (a2 << 2)
    at = field(b, 2, 3, 2)
    length = ((b[2] & 0x3) << 8) | b[3]

    fmt_info = tables.FMT_NFM.get(fmt)
    fmt_bad = fmt_info is None
    if fmt_bad:
        lines.append(warn("Fmt[2:0] = {} 为保留编码，按 Malformed TLP 处理。".format(binstr(fmt, 3))))
        header_dw = 3
        has_data = False
        fmt_desc = "保留编码（无法解析）"
    else:
        fmt_desc, header_dw, has_data = fmt_info

    # ---- 类型名 ----
    type_name = "Reserved"
    type_desc = ""
    type_bad = False
    if 0x10 <= type5 <= 0x17:
        type_name = "MsgD" if has_data else "Msg"
        routing, type_bad = _lookup(tables.MSG_ROUTING, type5 & 0x07)
        type_desc = "Message {}（路由方式：{}）".format(
            "with Data" if has_data else "without Data", routing)
    else:
        entry = tables.NFM_TYPE_NAME.get(type5, {}).get(fmt)
        if entry:
            type_name, type_desc = entry
        elif type5 in tables.NFM_TYPE_NAME:
            type_name = "编码/类型不匹配"
            type_desc = "该 Type 在 Fmt={} 下未定义".format(binstr(fmt, 3))
            type_bad = True
        else:
            type_desc = "保留 / 未定义类型"
            type_bad = True

    route_name, route_bad = _route_of_nfm(type5)

    # ---- 标题 ----
    lines.append(title("Non-Flit Mode  TLP Header 解析"))
    lines.append(Line("text", "输入：{}   （{} DW / {} B）".format(
        byte_str(data), provided_dw, provided_dw * 4)))
    lines.append(blank())

    # ---- 概要 ----
    lines.append(sec("概要"))
    lines.append(kv("模式", "", "Non-Flit Mode"))
    lines.append(kv("TLP 类型", "Fmt+Type", "{}  —  {}".format(type_name, type_desc),
                    bad=type_bad or fmt_bad))
    lines.append(kv("路由方式", "Type[4:0]", route_name, bad=route_bad))
    lines.append(kv("头部长度", "Fmt[2:0]", "{} DW（{} B）".format(header_dw, header_dw * 4),
                    bad=fmt_bad))
    lines.append(kv("是否带数据", "Fmt[1]", "是" if has_data else "否", bad=fmt_bad))
    lines.append(blank())

    # ---- 前缀 ----
    if prefix_lines:
        lines.append(sec("TLP Prefix（位于头部之前，各 1 DW）"))
        lines.extend(prefix_lines)
        lines.append(blank())

    # ---- 通用字段 ----
    lines.append(sec("通用头字段（Figure 2-5）"))
    lines.append(kv("Fmt[2:0]", "byte0[7:5]", "{} = {}".format(binstr(fmt, 3), fmt_desc),
                    bad=fmt_bad))
    lines.append(kv("Type[4:0]", "byte0[4:0]", "{} = Type {}".format(binstr(type5, 5), type_name),
                    bad=type_bad))
    lines.append(kv("TC[2:0]", "byte1[6:4]", "{} = TC{}".format(binstr(tc, 3), tc)))
    lines.append(kv("T9 / T8", "byte1[7] / [3]",
                    "Tag[9]={}  Tag[8]={}".format(t9, t8)))
    lines.append(kv("A2 (Attr[2])", "byte1[2]", str(a2)))
    lines.append(kv("R", "byte1[1]", "{}（Reserved，接收方忽略）".format(r_bit)))
    lines.append(kv("TH", "byte1[0]", "{}（{}）".format(th, "含 TPH" if th else "无 TPH")))
    lines.append(kv("TD", "byte2[7]", "{}（{}）".format(td, "头部后带 1 DW ECRC" if td else "无 TLP Digest")))
    lines.append(kv("EP", "byte2[6]", "{}（{}）".format(ep, "已投毒" if ep else "未投毒")))
    lines.append(kv("Attr[2:0]", "byte2[5:4]+byte1[2]", _attr_text(attr)))
    at_text, at_bad = _at_desc(at)
    lines.append(kv("AT[1:0]", "byte2[3:2]", "{} = {}".format(binstr(at, 2), at_text), bad=at_bad))
    lines.append(kv("Length[9:0]", "byte2[1:0]+byte3[7:0]",
                    "0x{:03X} = {} DW{}".format(length, 1024 if length == 0 else length,
                                                "（编码 0 表示 1024）" if length == 0 else "")))
    lines.append(blank())

    # ---- 类型专属字段 ----
    lines.append(sec("类型专属字段"))
    lines.extend(_nfm_payload_fields(data, off, type5, header_dw, has_data))
    lines.append(blank())

    # ---- 长度统计 ----
    payload_dw = (1024 if length == 0 else length) if has_data else 0
    trailer_dw = 1 if td else 0
    total_dw = header_dw + payload_dw + trailer_dw
    lines.append(sec("长度统计与校验"))
    lines.append(kv("Header", "{} DW".format(header_dw), "{} 字节".format(header_dw * 4)))
    lines.append(kv("Data Payload", "Length", "{} DW（{} 字节）".format(payload_dw, payload_dw * 4)))
    lines.append(kv("TLP Digest", "TD", "{} DW".format(trailer_dw)))
    total_text = "{} DW / {} 字节".format(total_dw, total_dw * 4)
    if off:
        total_text += "（含前缀 {} DW）".format(off // 4)
    lines.append(kv("TLP 总长", "", total_text))
    lines.append(kv("实际提供", "", "{} DW / {} 字节".format(provided_dw, provided_dw * 4)))

    need_header_dw = header_dw + off // 4
    if provided_dw < need_header_dw:
        lines.append(warn("输入 DW 少于头部长度（需要 {} DW），头部字段按缺失补 0 解析。".format(need_header_dw)))
    else:
        lines.append(good("输入已覆盖完整头部。"))
    if provided_dw < need_header_dw + payload_dw:
        lines.append(note("若为完整 TLP，还需再提供 {} DW 数据载荷。".format(
            need_header_dw + payload_dw - provided_dw)))

    summary = "{} · {} DW 头 · 载荷 {} DW · TLP 总长 {} B".format(
        type_name, header_dw, payload_dw, total_dw * 4)
    n_bad = sum(1 for line in lines if line.kind == "err")
    if n_bad:
        summary += " · {} 处无法解析".format(n_bad)
    return ParseResult("Non-Flit Mode", lines, summary)


def _nfm_payload_fields(data: Sequence[int], off: int, type5: int,
                        header_dw: int, has_data: bool) -> List[Line]:
    """按类型给出 byte4 之后的字段。仅覆盖已核对的常见类型。"""
    out: List[Line] = []
    hdr = list(data[off:off + header_dw * 4])
    if len(hdr) < header_dw * 4:
        hdr = hdr + [0] * (header_dw * 4 - len(hdr))

    def need(n: int) -> bool:
        return len(hdr) >= n

    # --- 地址路由类请求 ---
    addr_routed = (type5 in (0x00, 0x01, 0x1B) or 0x0C <= type5 <= 0x0E)
    if addr_routed and need(8):
        req_id = (hdr[4] << 8) | hdr[5]
        tagv = hdr[6]
        last_be = hdr[7] >> 4
        first_be = hdr[7] & 0x0F
        out.append(kv("Requester ID", "byte4-5",
                      "{:04X}h  (Bus {:02X}h / Dev {:02X}h / Func {})".format(
                          req_id, req_id >> 8, (req_id >> 3) & 0x1F, req_id & 0x7)))
        out.append(kv("Tag[7:0]", "byte6", "{:02X}h".format(tagv)))
        out.append(kv("Tag[9:0]", "byte6 + T9/T8",
                      "0x{:03X}".format((field(hdr, 1, 7, 7) << 9) | (field(hdr, 1, 3, 3) << 8) | tagv)))
        out.append(kv("Last / First DW BE", "byte7[7:4] / [3:0]", _be_text(first_be, last_be)))
        if header_dw == 4 and need(16):
            addr_hi = (hdr[8] << 24) | (hdr[9] << 16) | (hdr[10] << 8) | hdr[11]
            addr_lo_raw = (hdr[12] << 24) | (hdr[13] << 16) | (hdr[14] << 8) | hdr[15]
            out.append(kv("Address[63:32]", "byte8-11", "{:08X}h".format(addr_hi)))
            out.append(kv("Address[31:2]", "byte12-15[31:2]", "{:08X}h".format(addr_lo_raw & 0xFFFFFFFC)))
            out.append(kv("PH[1:0]", "byte15[1:0]", binstr(addr_lo_raw & 0x3, 2)))
            out.append(kv("Address", "64 位",
                          "0x{:08X}{:08X}".format(addr_hi, addr_lo_raw & 0xFFFFFFFC)))
        else:
            addr_raw = (hdr[8] << 24) | (hdr[9] << 16) | (hdr[10] << 8) | hdr[11]
            out.append(kv("Address[31:2]", "byte8-11[31:2]", "{:08X}h".format(addr_raw & 0xFFFFFFFC)))
            out.append(kv("PH[1:0]", "byte11[1:0]", binstr(addr_raw & 0x3, 2)))
            out.append(kv("Address", "32 位", "0x{:08X}".format(addr_raw & 0xFFFFFFFC)))
        return out

    # --- Completion ---
    if type5 in (0x0A, 0x0B) and need(12):
        cpl_id = (hdr[4] << 8) | hdr[5]
        status = hdr[6] >> 5
        bcm = (hdr[6] >> 4) & 1
        byte_count = ((hdr[6] & 0x0F) << 8) | hdr[7]
        req_id = (hdr[8] << 8) | hdr[9]
        out.append(kv("Completer ID", "byte4-5",
                      "{:04X}h  (Bus {:02X}h / Dev {:02X}h / Func {})".format(
                          cpl_id, cpl_id >> 8, (cpl_id >> 3) & 0x1F, cpl_id & 0x7)))
        cpl_desc, cpl_bad = _lookup(tables.CPL_STATUS, status)
        out.append(kv("Cpl. Status", "byte6[7:5]",
                      "{} = {}".format(binstr(status, 3), cpl_desc), bad=cpl_bad))
        out.append(kv("BCM", "byte6[4]", "{}（{}）".format(bcm, "含修改过的字节计数" if bcm else "字节计数有效")))
        out.append(kv("Byte Count[11:0]", "byte6[3:0]+byte7", "0x{:03X} = {} DW".format(byte_count, byte_count)))
        out.append(kv("Requester ID", "byte8-9",
                      "{:04X}h  (Bus {:02X}h / Dev {:02X}h / Func {})".format(
                          req_id, req_id >> 8, (req_id >> 3) & 0x1F, req_id & 0x7)))
        out.append(kv("Tag[7:0]", "byte10", "{:02X}h".format(hdr[10])))
        out.append(kv("Lower Address[6:0]", "byte11[6:0]", "0x{:02X}".format(hdr[11] & 0x7F)))
        return out

    # --- 配置请求 ---
    if type5 in (0x04, 0x05) and need(12):
        req_id = (hdr[4] << 8) | hdr[5]
        out.append(kv("Requester ID", "byte4-5", "{:04X}h".format(req_id)))
        out.append(kv("Tag[7:0]", "byte6", "{:02X}h".format(hdr[6])))
        out.append(kv("Last / First DW BE", "byte7[7:4] / [3:0]", _be_text(hdr[7] & 0xF, hdr[7] >> 4)))
        out.append(kv("Destination ID", "byte8-9",
                      "Bus {:02X}h / Dev {:02X}h / Func {}".format(hdr[8], (hdr[9] >> 3) & 0x1F, hdr[9] & 0x7)))
        out.append(kv("Ext Reg Number", "byte10", "{:02X}h".format(hdr[10])))
        out.append(kv("Register Number", "byte11", "{:02X}h".format(hdr[11])))
        return out

    # --- Message ---
    if 0x10 <= type5 <= 0x17 and need(8):
        req_id = (hdr[4] << 8) | hdr[5]
        code = hdr[6]
        out.append(kv("Requester ID", "byte4-5", "{:04X}h".format(req_id)))
        out.append(kv("Tag[7:0]", "byte6-1", "{:02X}h".format(hdr[7])))
        msg_route, msg_bad = _lookup(tables.MSG_ROUTING, type5 & 0x07)
        out.append(kv("Message Code", "byte6", "{:02X}h  (r[2:0]={})".format(code, msg_route),
                      bad=msg_bad))
        out.append(note("byte8 之后的内容取决于 Message Code（§2.2.8 / Table 2-20 ~ 2-36），此处不解码。"))
        out.append(kv("原始数据", "byte8-15", _dump(hdr, 2, 2)))
        return out

    out.append(note("该类型的专属字段布局见 §2.2.5 / §2.2.8 / §2.2.9，本工具暂未展开。"))
    if len(hdr) > 4:
        out.append(kv("原始数据", "byte4 起", byte_str(hdr[4:])))
    return out


# ---------------------------------------------------------------- Flit Mode

def parse_fm(data: Sequence[int], provided_dw: int) -> ParseResult:
    lines: List[Line] = []
    sec = Sec()
    off = 0

    # ---- Local Prefix（Type 128~143）----
    prefix_lines: List[Line] = []
    guard = 0
    while off + 4 <= len(data) and 128 <= data[off] <= 143 and guard < 8:
        guard += 1
        t = data[off]
        known = {141: "FlitModePrefix", 142: "VendPrefixL0", 143: "VendPrefixL1"}.get(t)
        prefix_lines.append(kv("Local Prefix", "DW{} / byte{}".format(off // 4, off),
                               "Type 0x{:02X} = {}".format(t, known or "Reserved Local Prefix"),
                               bad=known is None))
        off += 4

    if off + 4 > len(data):
        lines.append(warn("输入数据不足一个 TLP Header（需要至少 1 DW）。"))
        return ParseResult("Flit Mode", lines)

    b = _bytes_at(data, off // 4)
    type8 = b[0]
    tc = field(b, 1, 7, 5)
    ohc = field(b, 1, 4, 0)
    ts = field(b, 2, 7, 5)
    attr = field(b, 2, 4, 2)
    length = ((b[2] & 0x3) << 8) | b[3]

    info = tables.fm_type_info(type8)
    type_bad = info is None
    if type_bad:
        name, fc, has_data, base_dw = "未定义（无法解析）", "—", False, 3
    else:
        name, fc, has_data, base_dw = info

    ohc_a, ohc_b, ohc_c, ohc_e_dw = tables.ohc_layout(ohc)
    ohc_dw = int(ohc_a) + int(ohc_b) + int(ohc_c) + ohc_e_dw
    header_total_dw = base_dw + ohc_dw
    payload_dw = (1024 if length == 0 else length) if has_data else 0
    trailer_dw = tables.TS_TRAILER_DW.get(ts, 0)
    total_dw = header_total_dw + payload_dw + trailer_dw + off // 4

    lines.append(title("Flit Mode  TLP Header Base 解析"))
    lines.append(Line("text", "输入：{}   （{} DW / {} B）".format(
        byte_str(data), provided_dw, provided_dw * 4)))
    lines.append(blank())

    lines.append(sec("概要"))
    lines.append(kv("模式", "", "Flit Mode"))
    lines.append(kv("TLP 类型", "Type[7:0]", "0x{:02X}  —  {}".format(type8, name), bad=type_bad))
    lines.append(kv("FC 类型", "Table 2-5", fc, bad=type_bad))
    lines.append(kv("是否带数据", "Table 2-5", "是" if has_data else "否", bad=type_bad))
    lines.append(kv("Header Base", "Type[7:0]", "{} DW（{} B）".format(base_dw, base_dw * 4),
                    bad=type_bad))
    lines.append(kv("OHC", "OHC[4:0]", "{} DW（A={} B={} C={} E={} DW）".format(
        ohc_dw, int(ohc_a), int(ohc_b), int(ohc_c), ohc_e_dw)))
    lines.append(kv("头部合计", "Base + OHC", "{} DW（{} B）".format(header_total_dw, header_total_dw * 4)))
    lines.append(blank())

    if prefix_lines:
        lines.append(sec("Local TLP Prefix（位于头部之前，各 1 DW）"))
        lines.extend(prefix_lines)
        lines.append(blank())

    lines.append(sec("通用头字段（Figure 2-6）"))
    lines.append(kv("Type[7:0]", "byte0[7:0]", "0x{:02X} = {}".format(type8, name),
                    bad=type_bad))
    lines.append(kv("TC[2:0]", "byte1[7:5]", "{} = TC{}".format(binstr(tc, 3), tc)))
    lines.append(kv("OHC[4:0]", "byte1[4:0]", "{} = {}".format(
        binstr(ohc, 5), "无 OHC" if ohc == 0 else "见下文 OHC 明细")))
    ts_desc, ts_bad = _lookup(tables.TS_DESC, ts)
    lines.append(kv("TS[2:0]", "byte2[7:5]", "{} = {}".format(binstr(ts, 3), ts_desc),
                    bad=ts_bad))
    lines.append(kv("Attr[2:0]", "byte2[4:2]", _attr_text(attr)))
    lines.append(kv("Length[9:0]", "byte2[1:0]+byte3[7:0]",
                    "0x{:03X} = {} DW{}".format(length, 1024 if length == 0 else length,
                                                "（编码 0 表示 1024）" if length == 0 else "")))
    lines.append(blank())

    lines.append(sec("类型专属字段"))
    lines.extend(_fm_payload_fields(data, off, type8, base_dw))
    lines.append(blank())

    # ---- OHC 明细 ----
    if ohc_dw:
        lines.append(sec("OHC（Orthogonal Header Content，紧跟 Header Base，顺序 A→B→C→E）"))
        dw_cursor = off // 4 + base_dw
        if ohc_a:
            lines.extend(_fm_ohc_a(data, dw_cursor, type8))
            dw_cursor += 1
        if ohc_b:
            lines.extend(_fm_ohc_b(data, dw_cursor))
            dw_cursor += 1
        if ohc_c:
            lines.extend(_fm_ohc_c(data, dw_cursor))
            dw_cursor += 1
        if ohc_e_dw:
            lines.extend(_fm_ohc_e(data, dw_cursor, ohc_e_dw))
            dw_cursor += ohc_e_dw
        lines.append(blank())

    # ---- 长度统计 ----
    lines.append(sec("长度统计与校验"))
    lines.append(kv("Header Base", "Type[7:0]", "{} DW".format(base_dw)))
    lines.append(kv("OHC", "OHC[4:0]", "{} DW".format(ohc_dw)))
    lines.append(kv("Header 合计", "", "{} DW / {} 字节".format(header_total_dw, header_total_dw * 4)))
    lines.append(kv("Data Payload", "Length", "{} DW（{} 字节）".format(payload_dw, payload_dw * 4)))
    lines.append(kv("Trailer", "TS[2:0]", "{} DW".format(trailer_dw)))
    lines.append(kv("TLP 总长", "", "{} DW / {} 字节".format(total_dw, total_dw * 4)))
    lines.append(kv("实际提供", "", "{} DW / {} 字节".format(provided_dw, provided_dw * 4)))

    need = (off // 4) + header_total_dw
    if provided_dw < need:
        lines.append(warn("输入 DW 少于头部长度（需要 {} DW，当前 {} DW），缺失部分按 0 解析。".format(
            need, provided_dw)))
    else:
        lines.append(good("输入已覆盖完整头部。"))
    if provided_dw < need + payload_dw:
        lines.append(note("若为完整 TLP，还需再提供 {} DW 数据载荷。".format(
            need + payload_dw - provided_dw)))

    summary = "{} · Base {} DW + OHC {} DW · 载荷 {} DW · TLP 总长 {} B".format(
        name, base_dw, ohc_dw, payload_dw, total_dw * 4)
    n_bad = sum(1 for line in lines if line.kind == "err")
    if n_bad:
        summary += " · {} 处无法解析".format(n_bad)
    return ParseResult("Flit Mode", lines, summary)


def _fm_payload_fields(data: Sequence[int], off: int, type8: int, base_dw: int) -> List[Line]:
    out: List[Line] = []
    hdr = list(data[off:off + base_dw * 4])
    if len(hdr) < base_dw * 4:
        hdr = hdr + [0] * (base_dw * 4 - len(hdr))

    entry = tables.FM_ADDR_ROUTED_BASE.get(type8)
    if not entry or len(hdr) < 8:
        out.append(note("该类型的专属字段布局见 §2.2.5 / §2.2.8 / §2.2.9，本工具暂未展开。"))
        if len(hdr) > 4:
            out.append(kv("原始数据", "byte4 起", byte_str(hdr[4:])))
        return out

    req_id = (hdr[4] << 8) | hdr[5]
    ep = hdr[6] >> 7
    r_bit = (hdr[6] >> 6) & 1
    tag = ((hdr[6] & 0x3F) << 8) | hdr[7]

    out.append(kv("Requester ID", "byte4-5",
                  "{:04X}h  (Bus {:02X}h / Dev {:02X}h / Func {})".format(
                      req_id, req_id >> 8, (req_id >> 3) & 0x1F, req_id & 0x7)))
    out.append(kv("EP", "byte6[7]", "{}（{}）".format(ep, "已投毒" if ep else "未投毒")))
    out.append(kv("R", "byte6[6]", "{}（Reserved）".format(r_bit)))
    out.append(kv("Tag[13:0]", "byte6[5:0]+byte7", "0x{:04X}".format(tag)))

    if base_dw >= 4 and len(hdr) >= 16:
        addr_hi = (hdr[8] << 24) | (hdr[9] << 16) | (hdr[10] << 8) | hdr[11]
        addr_lo_raw = (hdr[12] << 24) | (hdr[13] << 16) | (hdr[14] << 8) | hdr[15]
        out.append(kv("Address[63:32]", "byte8-11", "{:08X}h".format(addr_hi)))
        out.append(kv("Address[31:2]", "byte12-15[31:2]", "{:08X}h".format(addr_lo_raw & 0xFFFFFFFC)))
        at_text, at_bad = _at_desc(addr_lo_raw & 0x3)
        out.append(kv("AT[1:0]", "byte15[1:0]", "{} = {}".format(
            binstr(addr_lo_raw & 0x3, 2), at_text), bad=at_bad))
        out.append(kv("Address", "64 位", "0x{:08X}{:08X}".format(addr_hi, addr_lo_raw & 0xFFFFFFFC)))
    else:
        addr_raw = (hdr[8] << 24) | (hdr[9] << 16) | (hdr[10] << 8) | hdr[11]
        out.append(kv("Address[31:2]", "byte8-11[31:2]", "{:08X}h".format(addr_raw & 0xFFFFFFFC)))
        at_text, at_bad = _at_desc(addr_raw & 0x3)
        out.append(kv("AT[1:0]", "byte11[1:0]", "{} = {}".format(
            binstr(addr_raw & 0x3, 2), at_text), bad=at_bad))
        out.append(kv("Address", "32 位", "0x{:08X}".format(addr_raw & 0xFFFFFFFC)))

    if base_dw > 4:
        out.append(note("该类型 Header Base 为 {} DW，byte16 之后为类型相关扩展字段（§2.2.4.1 Figure 2-20~2-22）。".format(base_dw)))
    return out


def _fm_ohc_a(data: Sequence[int], dw: int, type8: int) -> List[Line]:
    out: List[Line] = [Line("text", "  · OHC-A @ DW{}".format(dw))]
    b = _bytes_at(data, dw)
    if not any(b):
        out.append(note("（该 DW 未提供或全 0）"))
        return out

    if type8 in (2, 66):  # I/O 请求 → OHC-A2
        out.append(kv("变体", "OHC-A2", "I/O Request"))
        out.append(kv("Last / First DW BE", "byte3[7:4] / [3:0]", _be_text(b[3] & 0xF, b[3] >> 4)))
        return out
    if type8 in (4, 5, 68, 69):  # 配置请求 → OHC-A3
        out.append(kv("变体", "OHC-A3", "Configuration Request"))
        dsv = b[2] >> 7
        out.append(kv("Destination Segment", "byte0", "{:02X}h{}".format(
            b[0], "" if dsv else "（DSV=0，Reserved）")))
        out.append(kv("DSV", "byte2[7]", str(dsv)))
        out.append(kv("Last / First DW BE", "byte3[7:4] / [3:0]", _be_text(b[3] & 0xF, b[3] >> 4)))
        return out
    if type8 in (10, 11, 12, 13, 74, 75, 72):  # Completion → OHC-A5
        out.append(kv("变体", "OHC-A5", "Completion"))
        dsv = b[2] >> 7
        out.append(kv("Destination Segment", "byte0", "{:02X}h".format(b[0])))
        out.append(kv("Completer Segment", "byte1", "{:02X}h".format(b[1])))
        out.append(kv("DSV", "byte2[7]", str(dsv)))
        out.append(kv("LA[1:0]", "byte3[3:2]", binstr((b[3] >> 2) & 0x3, 2)))
        out.append(kv("Cpl. Status", "byte3[1:0]", binstr(b[3] & 0x3, 2)))
        return out
    if 48 <= type8 <= 55 or 112 <= type8 <= 119:  # ID 路由 Message → OHC-A4
        out.append(kv("变体", "OHC-A4", "ID-Routed Message"))
        pv = (b[2] >> 6) & 1
        pasid = ((b[2] & 0x0F) << 16) | (b[1] << 8) | b[3]
        out.append(kv("Destination Segment", "byte0", "{:02X}h".format(b[0])))
        out.append(kv("DSV", "byte2[7]", str(b[2] >> 7)))
        out.append(kv("PV", "byte2[6]", str(pv)))
        out.append(kv("PASID[19:0]", "byte2[3:0]+byte1+byte3",
                      "0x{:05X}{}".format(pasid, "" if pv else "（PV=0，Reserved）")))
        return out

    # 其余（内存请求等）→ OHC-A1
    pv = (b[0] >> 6) & 1
    pasid = ((b[0] & 0x0F) << 16) | (b[1] << 8) | b[2]
    out.append(kv("变体", "OHC-A1", "Memory Request / Translation Request"))
    out.append(kv("NW / PV / PMR / ER", "byte0[7] / [6] / [5] / [4]", "{} / {} / {} / {}".format(
        b[0] >> 7, pv, (b[0] >> 5) & 1, (b[0] >> 4) & 1)))
    out.append(kv("PASID[19:0]", "byte0[3:0]+byte1+byte2",
                  "0x{:05X}{}".format(pasid, "" if pv else "（PV=0，Reserved）")))
    out.append(kv("Last / First DW BE", "byte3[7:4] / [3:0]", _be_text(b[3] & 0xF, b[3] >> 4)))
    return out


def _fm_ohc_b(data: Sequence[int], dw: int) -> List[Line]:
    out: List[Line] = [Line("text", "  · OHC-B @ DW{}".format(dw))]
    b = _bytes_at(data, dw)
    st = (b[1] << 8) | b[2]
    ph = b[3] >> 6
    hv = (b[3] >> 4) & 0x3
    ama = (b[3] >> 1) & 0x7
    av = b[3] & 1
    out.append(kv("Steering Tag", "byte1-2", "0x{:04X}".format(st)))
    out.append(kv("PH[1:0]", "byte3[7:6]", binstr(ph, 2)))
    out.append(kv("HV[1:0]", "byte3[5:4]", "{}（{}）".format(
        binstr(hv, 2),
        {0: "PH/ST 无效", 1: "仅 ST[7:0] 有效",
         2: "保留编码（无法解析），按 00b 处理", 3: "PH/ST 全部有效"}[hv]), bad=(hv == 2)))
    out.append(kv("AMA[2:0]", "byte3[3:1]", "{}{}".format(binstr(ama, 3), "" if av else "（AV=0，Reserved）")))
    out.append(kv("AV", "byte3[0]", str(av)))
    return out


def _fm_ohc_c(data: Sequence[int], dw: int) -> List[Line]:
    out: List[Line] = [Line("text", "  · OHC-C @ DW{}".format(dw))]
    b = _bytes_at(data, dw)
    sub = (b[3] >> 4) & 0x7
    out.append(kv("Requester Segment", "byte0", "{:02X}h{}".format(
        b[0], "" if (b[3] >> 3) & 1 else "（RSV=0，Reserved）")))
    out.append(kv("RSV", "byte3[3]", str((b[3] >> 3) & 1)))
    out.append(kv("PR_Sent_Counter", "byte1", "0x{:02X}".format(b[1])))
    out.append(kv("Stream_ID", "byte2", "0x{:02X}".format(b[2])))
    out.append(kv("XT / T / K", "byte3[7] / [0] / [1]", "{} / {} / {}".format(
        b[3] >> 7, b[3] & 1, (b[3] >> 1) & 1)))
    sub_desc = "IDE TLP" if sub in (0, 1, 2) else (
        "非 IDE（仅携带 Requester Segment）" if sub == 7 else "保留编码（无法解析）")
    out.append(kv("Sub-Stream[2:0]", "byte3[6:4]", "{}（{}）".format(binstr(sub, 3), sub_desc),
                  bad=(3 <= sub <= 6)))
    return out


def _fm_ohc_e(data: Sequence[int], dw: int, count: int) -> List[Line]:
    out: List[Line] = [Line("text", "  · OHC-E @ DW{}~{}（{} DW）".format(dw, dw + count - 1, count))]
    for i in range(count):
        b = _bytes_at(data, dw + i)
        code = b[0] >> 4
        if code == 0:
            desc, bad = "No Entry（本 DW 其余保留）", False
        elif code == 1:
            prefix_name, bad = _lookup(tables.END_END_PREFIX, b[0] & 0x0F)
            desc = "End-End Prefix: " + prefix_name
        else:
            desc, bad = "保留 Entry 类型（无法解析），按 No Entry 处理", True
        out.append(kv("OHC-E DW{}".format(i), "byte0[7:4]=0x{:X}".format(code), desc, bad=bad))
    return out


# ---------------------------------------------------------------- 统一入口

def parse(data: Sequence[int], mode: str, provided_dw: Optional[int] = None) -> ParseResult:
    """data 为头部字节序列；mode 取 'nfm' / 'fm'。"""
    if provided_dw is None:
        provided_dw = (len(data) + 3) // 4
    if str(mode).lower().startswith("f") and not str(mode).lower().startswith("non"):
        return parse_fm(data, provided_dw)
    return parse_nfm(data, provided_dw)
