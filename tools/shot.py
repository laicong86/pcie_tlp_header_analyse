# -*- coding: utf-8 -*-
"""开发期自检脚本：启动界面 → 截图 → 退出（不进入 mainloop 常驻）。

用法：
    py -3 tools/shot.py [输出文件名]
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk

from ui.app import App, create_root


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "shot.png"
    mode = sys.argv[2] if len(sys.argv) > 2 else ""
    root = create_root()
    app = App(root)
    if mode.lower() in ("fm", "flit"):
        app.mode_var.set("Flit Mode")
        app._on_change()
    root.update_idletasks()
    root.update()
    root.lift()
    root.attributes("-topmost", True)
    root.update()

    grabbed = {"ok": False}

    def shoot():
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(out)
            tx, ty = app.text.winfo_rootx(), app.text.winfo_rooty()
            tw, th = app.text.winfo_width(), app.text.winfo_height()
            img.crop((tx, ty, tx + tw, ty + th)).save(out.replace(".png", "_text.png"))
            grabbed["ok"] = True
        except Exception as exc:  # pragma: no cover
            print("截图失败：", exc)
        root.after(120, root.destroy)

    print("窗口尺寸:", root.winfo_width(), "x", root.winfo_height())
    print("输出文本行数:", len(app.text.get("1.0", "end").strip().splitlines()))
    root.after(900, shoot)
    root.mainloop()
    print("已保存:", out if grabbed["ok"] else "（未生成）")


if __name__ == "__main__":
    main()
