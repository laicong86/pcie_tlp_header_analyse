# -*- coding: utf-8 -*-
"""PCIe TLP Header 解析器 —— 程序入口。

运行：
    python main.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    try:
        from ui.app import main as run
    except ImportError as exc:  # pragma: no cover
        sys.stderr.write(
            "无法加载界面（需要带 tkinter 的 Python 解释器）：{}\n"
            "Windows 上可用：py -3 main.py\n".format(exc)
        )
        raise SystemExit(1)
    run()


if __name__ == "__main__":
    main()
