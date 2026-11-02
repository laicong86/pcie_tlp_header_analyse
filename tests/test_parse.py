# -*- coding: utf-8 -*-
"""解析器的自检用例（stdlib unittest，无需额外依赖）。

运行：
    py -3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tlp.parser import parse  # noqa: E402


def mk(*byte_values):
    return list(byte_values)


def find_line(lines, prefix):
    for line in lines:
        if line.text.strip().startswith(prefix):
            return line.text
    return ""


class TestNonFlit(unittest.TestCase):
    def test_mwr64(self):
        # Fmt=011(4DW+data) Type=00000 → MWr 64 位；Length=1；地址 0x00000010_9488BC00
        data = mk(0x60, 0x01, 0x00, 0x01,
                  0x00, 0x00, 0x00, 0x00,
                  0x00, 0x00, 0x00, 0x10,
                  0x94, 0x88, 0xBC, 0x00)
        r = parse(data, "nfm", provided_dw=4)
        self.assertIn("MWr", r.text)
        self.assertIn("4 DW header, with data", r.text)
        self.assertIn("0x000000109488BC00", r.text)
        self.assertIn("1 DW", find_line(r.lines, "Length[9:0]"))

    def test_cpld_3dw(self):
        # Fmt=010 Type=01010 → CplD；Completer ID=0000h，Byte Count=4
        data = mk(0x4A, 0x00, 0x00, 0x01,
                  0x00, 0x00, 0x00, 0x04,
                  0x01, 0x00, 0x00, 0x00)
        r = parse(data, "nfm", provided_dw=3)
        self.assertIn("CplD", r.text)
        self.assertIn("Successful Completion", r.text)
        self.assertIn("4 DW", find_line(r.lines, "Byte Count[11:0]"))
        self.assertIn("3 DW", find_line(r.lines, "头部长度"))

    def test_prefix_then_header(self):
        # DW0：Fmt=100 Type=10000 → End-End TPH Prefix；DW1 起是 MRd 32 位
        data = mk(0x90, 0x00, 0x00, 0x00,
                  0x00, 0x00, 0x00, 0x01,
                  0x00, 0x00, 0x00, 0x00,
                  0x10, 0x00, 0x00, 0x00)
        r = parse(data, "nfm", provided_dw=4)
        self.assertIn("TPH Prefix", r.text)
        self.assertIn("MRd", r.text)
        self.assertIn("3 DW", find_line(r.lines, "头部长度"))

    def test_length_zero_means_1024(self):
        data = mk(0x60, 0x00, 0x00, 0x00, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        r = parse(data, "nfm", provided_dw=4)
        self.assertIn("1024", find_line(r.lines, "Data Payload"))

    def test_attr_bits(self):
        # Attr[1]=1（Relaxed Ordering）、Attr[2]=1（IDO，来自 byte1 的 A2 位）
        data = mk(0x60, 0x0C, 0x20, 0x01, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        r = parse(data, "nfm", provided_dw=4)
        attr_line = find_line(r.lines, "Attr[2:0]")
        self.assertIn("RO", attr_line)
        self.assertIn("IDO", attr_line)


class TestFlit(unittest.TestCase):
    def test_mwr64_flit(self):
        # Type=0x60 → MWr（64b，4 DW Base）；ReqID=0100h；Tag[13:0]=0x0ABC
        data = mk(0x60, 0x00, 0x00, 0x01,
                  0x01, 0x00, 0x0A, 0xBC,
                  0x10, 0x00, 0x00, 0x00,
                  0x25, 0x22, 0x2F, 0x00)
        r = parse(data, "fm", provided_dw=4)
        self.assertIn("MWr", r.text)
        self.assertIn("4 DW", find_line(r.lines, "Header Base"))
        self.assertIn("0x0ABC", find_line(r.lines, "Tag[13:0]"))
        self.assertIn("0x1000000025222F00", r.text)

    def test_flit_with_ohc_a(self):
        # OHC=0b00001 → OHC-A 存在；头部应为 4+1 DW，只给 4 DW 时应告警
        data = mk(0x60, 0x01, 0x00, 0x01, 0x01, 0x00, 0x00, 0x00,
                  0x10, 0x00, 0x00, 0x00, 0x25, 0x22, 0x2F, 0x00)
        r = parse(data, "fm", provided_dw=4)
        self.assertIn("OHC-A", r.text)
        self.assertIn("输入 DW 少于头部长度", r.text)

    def test_flit_ohc_a1_decode(self):
        # 给足 5 DW：第 5 DW 为 OHC-A1（PV=1, PASID=0x12345, LastBE=1111, FirstBE=0001）
        data = mk(0x60, 0x01, 0x00, 0x01, 0x01, 0x00, 0x00, 0x00,
                  0x10, 0x00, 0x00, 0x00, 0x25, 0x22, 0x2F, 0x00,
                  0x41, 0x23, 0x45, 0xF1)
        r = parse(data, "fm", provided_dw=5)
        self.assertIn("OHC-A1", r.text)
        self.assertIn("0x12345", r.text)

    def test_nop(self):
        data = mk(0x00, 0x00, 0x00, 0x00)
        r = parse(data, "fm", provided_dw=1)
        self.assertIn("NOP", r.text)
        self.assertIn("1 DW", find_line(r.lines, "Header Base"))


class TestUnparsable(unittest.TestCase):
    """域段值无法解析时应产出 kind='err' 的行（UI 会整行标红）。"""

    def err_lines(self, r):
        return [ln for ln in r.lines if ln.kind == "err"]

    def test_normal_has_no_err(self):
        data = mk(0x60, 0x01, 0x00, 0x01, 0, 0, 0, 0, 0, 0, 0, 0x10, 0x94, 0x88, 0xBC, 0x00)
        r = parse(data, "nfm", provided_dw=4)
        self.assertEqual(r.error_count, 0)
        self.assertNotIn("处无法解析", r.summary)

    def test_nfm_reserved_fmt(self):
        # Fmt=101b 为保留编码
        r = parse(mk(0xA0, 0x00, 0x00, 0x00), "nfm", provided_dw=1)
        self.assertGreaterEqual(r.error_count, 1)
        self.assertIn("保留编码", find_line(r.lines, "Fmt[2:0]"))
        self.assertEqual([ln.kind for ln in r.lines if ln.text.strip().startswith("Fmt[2:0]")],
                         ["err"])

    def test_nfm_undefined_type(self):
        # Fmt=011b / Type=11111b 未定义
        r = parse(mk(0x7F, 0x01, 0x00, 0x00), "nfm", provided_dw=1)
        self.assertGreaterEqual(r.error_count, 1)
        self.assertEqual([ln.kind for ln in r.lines if ln.text.strip().startswith("Type[4:0]")],
                         ["err"])

    def test_nfm_reserved_at(self):
        # AT[1:0]=11b 保留，位于 byte2[3:2]
        r = parse(mk(0x60, 0x01, 0x0C, 0x01), "nfm", provided_dw=1)
        at_lines = [ln for ln in r.lines if ln.text.strip().startswith("AT[1:0]")]
        self.assertEqual(len(at_lines), 1)
        self.assertEqual(at_lines[0].kind, "err")

    def test_nfm_reserved_completion_status(self):
        # Cpl. Status=111b 保留，位于 byte6[7:5]
        data = mk(0x4A, 0x00, 0x00, 0x01, 0x00, 0x00, 0xE0, 0x00, 0x01, 0x00, 0x00, 0x00)
        r = parse(data, "nfm", provided_dw=3)
        st_lines = [ln for ln in r.lines if ln.text.strip().startswith("Cpl. Status")]
        self.assertEqual(len(st_lines), 1)
        self.assertEqual(st_lines[0].kind, "err")

    def test_fm_reserved_hv(self):
        # OHC-B 的 HV=10b 为保留编码（DW4 的 byte3[5:4]）
        data = mk(0x60, 0x02, 0x00, 0x01) + [0] * 12 + [0x00, 0x00, 0x00, 0x20]
        r = parse(data, "fm", provided_dw=5)
        hv_lines = [ln for ln in r.lines if ln.text.strip().startswith("HV[1:0]")]
        self.assertEqual(len(hv_lines), 1)
        self.assertEqual(hv_lines[0].kind, "err")
        self.assertEqual(r.error_count, 1)

    def test_fm_reserved_ohc_e_entry(self):
        # OHC=0b11000 → OHC-E 4 DW；DW4 的 entry 编码 0x3 非法
        data = mk(0x60, 0x18, 0x00, 0x01) + [0] * 12 + [0x30, 0x00, 0x00, 0x00]
        r = parse(data, "fm", provided_dw=5)
        e_lines = [ln for ln in r.lines if ln.text.strip().startswith("OHC-E DW0")]
        self.assertEqual(len(e_lines), 1)
        self.assertEqual(e_lines[0].kind, "err")

    def test_ohc_e_missing_data_does_not_crash(self):
        # 只给 1 DW，OHC-E 指向不存在的 DW：应补 0 而不是抛异常
        r = parse(mk(0x60, 0x18, 0x00, 0x01), "fm", provided_dw=1)
        self.assertIn("Flit Mode", r.text)


if __name__ == "__main__":
    unittest.main()
