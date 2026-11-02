# -*- coding: utf-8 -*-
"""打包产物自检：启动 dist 下的 exe，等窗口出现后截图，再关闭进程。

用法：
    py -3 tools/verify_exe.py [截图输出路径]
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time

TITLE = "PCIe TLP Header 解析器"


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "_exe_shot.png"
    exe = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "dist", "PCIe_TLP_Header_Parser.exe")
    if not os.path.isfile(exe):
        print("找不到产物：", exe)
        return 2

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    t0 = time.time()
    proc = subprocess.Popen([exe], cwd=os.path.dirname(exe))
    user32 = ctypes.windll.user32

    hwnd = 0
    deadline = time.time() + 25
    while time.time() < deadline:
        hwnd = user32.FindWindowW(None, TITLE)
        if hwnd:
            break
        if proc.poll() is not None:
            print("进程已退出，退出码 =", proc.returncode)
            return 3
        time.sleep(0.25)

    if not hwnd:
        print("25s 内未出现窗口")
        proc.terminate()
        return 4

    print("窗口出现，耗时 {:.1f}s".format(time.time() - t0))

    from PIL import ImageGrab

    rect = ctypes.wintypes.RECT()
    pad = 10

    # 反复截图直到画面内容稳定（避免抓到尚未绘制的首帧）
    shot = None
    for _ in range(12):
        time.sleep(0.6)
        img = ImageGrab.grab()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        box = (max(rect.left - pad, 0), max(rect.top - pad - 30, 0),
               min(rect.right + pad, img.width), min(rect.bottom + pad, img.height))
        crop = img.crop(box)
        same = shot is not None and crop.tobytes() == shot.tobytes()
        shot = crop
        if same and len(set(crop.convert("RGB").getdata())) >= 30:
            break

    shot.save(out)
    if os.environ.get("SHOT_FULL"):
        img.save(out.replace(".png", "_full.png"))
    colors = len(set(shot.convert("RGB").getdata()))
    print("已保存:", out, "尺寸:", shot.size, "颜色数:", colors)
    if colors < 30:
        print("警告：画面颜色过少，可能未正常渲染")

    alive = proc.poll() is None
    print("进程仍在运行:", alive)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    return 0 if alive else 5


if __name__ == "__main__":
    import ctypes.wintypes  # noqa: F401  延迟导入，避免非 Windows 报错
    sys.exit(main())
