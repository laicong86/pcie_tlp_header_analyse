# -*- coding: utf-8 -*-
"""PCIe 7.0 TLP Header 编码表。

数据来源：PCI Express Base Specification Rev 7.0
  - Table 2-2  Fmt[2:0] 编码（§2.2.1.1）
  - Table 2-3  Non-Flit Mode Fmt/Type 编码（§2.2.1.1）
  - Table 2-5  Flit Mode Type[7:0] 编码（§2.2.1.2）
  - Table 2-38 / 2-39  TLP Prefix 类型
  - §2.2.1.2   TS[2:0] / OHC[4:0] 编码
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------- NFM 表 2-2

FMT_NFM: Dict[int, Tuple[str, int, bool]] = {
    0b000: ("3 DW header, no data", 3, False),
    0b001: ("4 DW header, no data", 4, False),
    0b010: ("3 DW header, with data", 3, True),
    0b011: ("4 DW header, with data", 4, True),
    0b100: ("TLP Prefix", 1, False),
}


# ---------------------------------------------------------------- NFM 表 2-3
# key = Type[4:0]（对 Msg/MsgD 用 0x10 作为基址，路由位在低 3 位）
# value = {fmt: (名称, 说明)}
# 头长与是否带数据由 Fmt 直接决定，无需查表。

NFM_TYPE_NAME: Dict[int, Dict[int, Tuple[str, str]]] = {
    0x00: {0b000: ("MRd", "Memory Read Request（32 位地址）"),
           0b001: ("MRd", "Memory Read Request（64 位地址）"),
           0b010: ("MWr", "Memory Write Request（32 位地址）"),
           0b011: ("MWr", "Memory Write Request（64 位地址）")},
    0x01: {0b000: ("MRdLk", "Memory Read Request-Locked（32 位地址）"),
           0b001: ("MRdLk", "Memory Read Request-Locked（64 位地址）")},
    0x02: {0b000: ("IORd", "I/O Read Request"),
           0b010: ("IOWr", "I/O Write Request")},
    0x04: {0b000: ("CfgRd0", "Type 0 Configuration Read"),
           0b010: ("CfgWr0", "Type 0 Configuration Write")},
    0x05: {0b000: ("CfgRd1", "Type 1 Configuration Read"),
           0b010: ("CfgWr1", "Type 1 Configuration Write")},
    0x0A: {0b000: ("Cpl", "Completion（无数据）"),
           0b010: ("CplD", "Completion with Data")},
    0x0B: {0b000: ("CplLk", "Locked Read Completion（无数据，仅错误场景）"),
           0b010: ("CplDLk", "Locked Read Completion with Data")},
    0x0C: {0b010: ("FetchAdd", "AtomicOp FetchAdd（32 位地址）"),
           0b011: ("FetchAdd", "AtomicOp FetchAdd（64 位地址）")},
    0x0D: {0b010: ("Swap", "AtomicOp Swap（32 位地址）"),
           0b011: ("Swap", "AtomicOp Swap（64 位地址）")},
    0x0E: {0b010: ("CAS", "AtomicOp Compare-and-Swap（32 位地址）"),
           0b011: ("CAS", "AtomicOp Compare-and-Swap（64 位地址）")},
    0x1B: {0b000: ("TCfgRd", "已废弃（原 Trusted Config Read），应按 Malformed 处理"),
           0b010: ("DMWr", "Deferrable Memory Write（32 位地址）"),
           0b011: ("DMWr", "Deferrable Memory Write（64 位地址）")},
}

# Message：Fmt=001 → Msg（无数据）；Fmt=011 → MsgD（有数据）；Type = 1 0 r2r1r0
MSG_TYPE_BASE = 0x10

MSG_ROUTING: Dict[int, str] = {
    0b000: "路由到 Root Complex",
    0b001: "按地址路由（64 位）",
    0b010: "按 ID 路由",
    0b011: "从 Root Complex 广播",
    0b100: "本地，接收方终结",
    0b101: "汇聚并路由到 RC（PME_TO_Ack）",
    0b110: "保留编码",
    0b111: "保留编码",
}

# Local / End-End TLP Prefix（Table 2-38 / 2-39）
LOCAL_PREFIX: Dict[int, str] = {
    0b0000: "MR-IOV Prefix",
    0b1101: "Flit Mode Local Prefix",
    0b1110: "Vendor Defined Local Prefix 0",
    0b1111: "Vendor Defined Local Prefix 1",
}

END_END_PREFIX: Dict[int, str] = {
    0b0000: "TPH Prefix",
    0b0001: "PASID Prefix",
    0b0010: "IDE Prefix",
    0b1110: "Vendor Defined End-End Prefix 0",
    0b1111: "Vendor Defined End-End Prefix 1",
}


# ---------------------------------------------------------------- FM 表 2-5
# (起, 止, 名称, FC, 是否有载荷, Header Base DW)

FM_TYPE_RANGES: List[Tuple[int, int, str, str, bool, int]] = [
    (0, 0, "NOP", "none", False, 1),
    (1, 1, "MRdLk", "NPR", False, 3),
    (2, 2, "IORd", "NPR", False, 3),
    (3, 3, "MRd", "NPR", False, 3),
    (4, 4, "CfgRd0", "NPR", False, 3),
    (5, 5, "CfgRd1", "NPR", False, 3),
    (6, 7, "Reserved", "CPL", True, 4),
    (8, 9, "Reserved", "PR", False, 3),
    (10, 10, "Cpl", "CPL", False, 3),
    (11, 11, "CplLk", "CPL", False, 3),
    (12, 12, "UIOWrCpl", "CPL", False, 3),
    (13, 13, "UIORdCpl", "CPL", False, 3),
    (14, 15, "Reserved", "CPL", False, 3),
    (16, 19, "Reserved", "NPR", True, 5),
    (20, 21, "Reserved", "NPR", True, 5),
    (22, 23, "Reserved", "NPR", True, 7),
    (24, 25, "Reserved", "CPL", False, 7),
    (26, 26, "Reserved", "CPL", True, 7),
    (27, 27, "Reserved（原 Trusted Config Read）", "CPL", True, 7),
    (28, 29, "Reserved", "NPR", False, 3),
    (30, 31, "Reserved", "NPR", False, 6),
    (32, 32, "MRd", "NPR", False, 4),
    (33, 33, "MRdLk", "NPR", False, 4),
    (34, 34, "UIOMRd", "NPR", False, 4),
    (35, 35, "Reserved", "NPR", False, 4),
    (36, 39, "Reserved", "NPR", False, 4),
    (40, 43, "Reserved", "CPL", False, 4),
    (44, 45, "Reserved", "PR", False, 4),
    (46, 47, "Reserved", "PR", False, 5),
    (48, 53, "Msg", "PR", False, 4),
    (54, 55, "Msg（保留编码）", "PR", False, 4),
    (56, 59, "Reserved", "NPR", False, 4),
    (60, 61, "Reserved", "NPR", False, 4),
    (62, 63, "Reserved", "NPR", False, 5),
    (64, 64, "MWr", "PR", True, 3),
    (65, 65, "Reserved", "PR", True, 6),
    (66, 66, "IOWr", "NPR", True, 3),
    (67, 67, "Reserved", "PR", True, 6),
    (68, 68, "CfgWr0", "NPR", True, 3),
    (69, 69, "CfgWr1", "NPR", True, 3),
    (70, 71, "Reserved", "NPR", True, 3),
    (72, 72, "UIORdCplD", "CPL", True, 3),
    (73, 73, "Reserved", "CPL", True, 3),
    (74, 74, "CplD", "CPL", True, 3),
    (75, 75, "CplDLk", "CPL", True, 3),
    (76, 76, "FetchAdd", "NPR", True, 3),
    (77, 77, "Swap", "NPR", True, 3),
    (78, 78, "CAS", "NPR", True, 3),
    (79, 79, "Reserved", "PR", False, 4),
    (80, 83, "Reserved", "NPR", True, 6),
    (84, 85, "Reserved", "NPR", True, 6),
    (86, 87, "Reserved", "NPR", True, 7),
    (88, 89, "Reserved", "PR", True, 3),
    (90, 90, "Reserved", "PR", True, 4),
    (91, 91, "DMWr", "NPR", True, 3),
    (92, 93, "Reserved", "PR", True, 4),
    (94, 95, "Reserved", "PR", True, 5),
    (96, 96, "MWr", "PR", True, 4),
    (97, 97, "UIOMWr", "PR", True, 4),
    (98, 107, "Reserved", "PR", True, 4),
    (108, 108, "FetchAdd", "NPR", True, 4),
    (109, 109, "Swap", "NPR", True, 4),
    (110, 110, "CAS", "NPR", True, 4),
    (111, 111, "Reserved", "NPR", True, 4),
    (112, 117, "MsgD", "PR", True, 4),
    (118, 119, "MsgD（保留编码）", "PR", True, 4),
    (120, 122, "Reserved", "NPR", True, 4),
    (123, 123, "DMWr", "NPR", True, 4),
    (124, 127, "Reserved", "NPR", True, 4),
    (128, 140, "Reserved（Local Prefix）", "none", False, 1),
    (141, 141, "FlitModePrefix", "none", False, 1),
    (142, 142, "VendPrefixL0", "none", False, 1),
    (143, 143, "VendPrefixL1", "none", False, 1),
    (144, 147, "Reserved", "PR", False, 4),
    (148, 151, "Reserved", "PR", False, 5),
    (152, 155, "Reserved", "PR", False, 6),
    (156, 159, "Reserved", "PR", False, 7),
    (160, 167, "Reserved", "NPR", False, 5),
    (168, 169, "Reserved", "PR", False, 6),
    (170, 171, "Reserved", "PR", False, 7),
    (172, 173, "Reserved", "CPL", False, 5),
    (174, 175, "Reserved", "CPL", False, 6),
    (176, 183, "Reserved", "PR", True, 5),
    (184, 191, "Reserved", "PR", True, 5),
    (192, 199, "Reserved", "NPR", False, 6),
    (200, 201, "Reserved", "NPR", False, 7),
    (202, 203, "Reserved", "CPL", True, 5),
    (204, 205, "Reserved", "CPL", True, 6),
    (206, 207, "Reserved", "PR", True, 7),
    (208, 215, "Reserved", "PR", True, 6),
    (216, 223, "Reserved", "PR", True, 6),
    (224, 225, "Reserved（Local，终结）", "none", False, 4),
    (226, 227, "Reserved（Local，终结）", "none", False, 6),
    (228, 229, "Reserved（Local，终结）", "none", True, 4),
    (230, 231, "Reserved（Local，终结）", "none", True, 6),
    (232, 239, "Reserved", "NPR", False, 7),
    (240, 241, "Reserved", "NPR", True, 4),
    (242, 243, "Reserved", "NPR", True, 5),
    (244, 245, "Reserved", "NPR", True, 6),
    (246, 247, "Reserved", "NPR", True, 7),
    (248, 255, "Reserved", "PR", True, 7),
]

# FM 中 Msg/MsgD 的细分类名（48~53 / 112~117）
FM_MSG_NAME: Dict[int, str] = {
    48: "Msg（路由到 RC）",
    49: "Msg（按地址 64b 路由，当前无定义）",
    50: "Msg（按 ID 路由）",
    51: "Msg（从 RC 广播）",
    52: "Msg（本地，接收方终结）",
    53: "Msg（PME_TO_Ack 汇聚到 RC）",
    112: "MsgD（路由到 RC）",
    113: "MsgD（按地址 64b 路由，当前无定义）",
    114: "MsgD（按 ID 路由）",
    115: "MsgD（从 RC 广播）",
    116: "MsgD（本地，接收方终结）",
    117: "MsgD（PME_TO_Ack 汇聚，未使用）",
}

# FM 中“地址路由类请求”的类型，可按 Figure 2-18/2-19 解析 ReqID/Tag/Address
FM_ADDR_ROUTED_BASE: Dict[int, Tuple[str, int]] = {
    1: ("MRdLk", 3), 2: ("IORd", 3), 3: ("MRd", 3),
    32: ("MRd", 4), 33: ("MRdLk", 4), 34: ("UIOMRd", 4),
    64: ("MWr", 3), 66: ("IOWr", 3), 68: ("CfgWr0", 3), 69: ("CfgWr1", 3),
    96: ("MWr", 4), 97: ("UIOMWr", 4),
    76: ("FetchAdd", 3), 77: ("Swap", 3), 78: ("CAS", 3),
    108: ("FetchAdd", 4), 109: ("Swap", 4), 110: ("CAS", 4),
    91: ("DMWr", 3), 123: ("DMWr", 4),
}


def fm_type_info(type8: int) -> Optional[Tuple[str, str, bool, int]]:
    """返回 (名称, FC, 是否带载荷, Header Base DW)。"""
    for lo, hi, name, fc, has_data, base in FM_TYPE_RANGES:
        if lo <= type8 <= hi:
            if type8 in FM_MSG_NAME:
                name = FM_MSG_NAME[type8]
            return name, fc, has_data, base
    return None


# ---------------------------------------------------------------- FM 其它表

TS_TRAILER_DW: Dict[int, int] = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 5}

TS_DESC: Dict[int, str] = {
    0: "无 Trailer",
    1: "1 DW Trailer（IDE TLP 时为保留内容，否则为 ECRC）",
    2: "1 DW Trailer，内容保留",
    3: "2 DW Trailer，内容保留",
    4: "2 DW Trailer，内容保留",
    5: "3 DW Trailer（IDE TLP 为 IDE MAC，否则保留）",
    6: "4 DW Trailer（IDE TLP 为 IDE MAC + PCRC，否则保留）",
    7: "5 DW Trailer，内容保留",
}

OHC_E_DW: Dict[int, int] = {0: 0, 1: 1, 2: 2, 3: 4}


def ohc_layout(ohc: int) -> Tuple[bool, bool, bool, int]:
    """把 OHC[4:0] 拆成 (A, B, C, E 的 DW 数)。"""
    return bool(ohc & 1), bool(ohc & 2), bool(ohc & 4), OHC_E_DW[(ohc >> 3) & 0x3]


# ---------------------------------------------------------------- 通用字段表

AT_DESC: Dict[int, str] = {
    0b00: "Untranslated（未翻译）",
    0b01: "Translation Request（翻译请求）",
    0b10: "Translated（已翻译）",
    0b11: "Reserved",
}

CPL_STATUS: Dict[int, str] = {
    0b000: "Successful Completion (SC)",
    0b001: "Unsupported Request (UR)",
    0b010: "Configuration Request Retry Status (CRS)",
    0b100: "Completer Abort (CA)",
}

ATTR_DESC: Dict[int, str] = {
    0b000: "默认（RO=0, NS=0, IDO=0）",
}

# Attr[2:0] 的逐位含义（§2.2.6.3 / Figure 2-35 / Table 2-12 / Table 2-13）
# Attr[0] = No Snoop，Attr[1] = Relaxed Ordering，Attr[2] = ID-Based Ordering
ATTR_BITS: Tuple[Tuple[int, str, str], ...] = (
    (0, "NS", "No Snoop"),
    (1, "RO", "Relaxed Ordering"),
    (2, "IDO", "ID-Based Ordering"),
)
