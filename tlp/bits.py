# -*- coding: utf-8 -*-
"""位域读取与格式化小工具。

约定与规范一致：一个字节内 bit7 为最高位；位号写作 ``[hi:lo]``。
"""

from __future__ import annotations

from typing import List, Sequence


def u32(data: Sequence[int], offset: int = 0) -> int:
    """把 data[offset:offset+4] 按 MSB 优先拼成一个 32 bit 整数。"""
    b = list(data[offset:offset + 4])
    while len(b) < 4:
        b.append(0)
    return (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]


def bits(byte_value: int, hi: int, lo: int) -> int:
    """取单字节内 [hi:lo] 位的值。"""
    if hi < lo:
        hi, lo = lo, hi
    width = hi - lo + 1
    return (byte_value >> lo) & ((1 << width) - 1)


def field(data: Sequence[int], byte_index: int, hi: int, lo: int) -> int:
    """取“第 byte_index 个字节的 [hi:lo] 位”。"""
    return bits(data[byte_index], hi, lo)


def multi_bits(data: Sequence[int], positions: List[tuple]) -> int:
    """按 MSB→LSB 顺序拼接若干 (byte_index, hi, lo) 片段。"""
    value = 0
    for byte_index, hi, lo in positions:
        width = hi - lo + 1
        value = (value << width) | field(data, byte_index, hi, lo)
    return value


def binstr(value: int, width: int) -> str:
    """格式化为定宽二进制串，带 b 后缀。"""
    return format(value, "0{}b".format(width)) + "b"


def hexstr(value: int, width_bytes: int = 2) -> str:
    """格式化为定宽十六进制串，带 h 后缀（宽度按字节数）。"""
    return "{:0{}X}h".format(value, width_bytes * 2)


def byte_str(data: Sequence[int]) -> str:
    return " ".join("{:02X}".format(b) for b in data)


def dw_list(data: Sequence[int]) -> List[int]:
    """把字节序列按 4 字节一组（DW）转成整数列表。"""
    out = []
    for i in range(0, len(data), 4):
        chunk = list(data[i:i + 4])
        if len(chunk) < 4:
            chunk += [0] * (4 - len(chunk))
        out.append((chunk[0] << 24) | (chunk[1] << 16) | (chunk[2] << 8) | chunk[3])
    return out


def parse_hex_dw(text: str) -> int:
    """把用户输入的 1~8 位十六进制解析成 32 bit 整数。

    允许 "0x" 前缀、空格、下划线；长度不足 8 位时按低位对齐（左补 0）。
    """
    s = (text or "").strip().replace("_", "").replace(" ", "")
    if s.lower().startswith("0x"):
        s = s[2:]
    if not s:
        raise ValueError("空")
    if len(s) > 8:
        raise ValueError("超过 8 位十六进制")
    return int(s, 16)
