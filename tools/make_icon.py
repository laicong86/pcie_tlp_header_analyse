# -*- coding: utf-8 -*-
"""生成应用图标 assets/app.ico（不参与打包，仅开发时重新生成用）。

图形语义：深蓝底 + 四条“头字段行”，末行为琥珀色，对应 TLP Header 的位域排版。
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

S = 1024  # 超采样画布，最后缩到各尺寸以保证边缘平滑


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def build() -> Image.Image:
    # 背景：对角渐变
    small = Image.new("RGB", (48, 48))
    c1, c2 = (0x12, 0x28, 0x55), (0x2F, 0x74, 0xD8)
    for y in range(48):
        for x in range(48):
            t = (x + y) / 94.0
            small.putpixel((x, y), lerp(c1, c2, t))
    bg = small.resize((S, S), Image.BICUBIC).convert("RGBA")

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)

    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    canvas.paste(bg, (0, 0), mask)

    d = ImageDraw.Draw(canvas)
    h = int(S * 0.088)          # 条高
    r = h // 2
    x0 = int(S * 0.185)
    rows = [
        (0.285, 0.630, (255, 255, 255, 240)),
        (0.415, 0.470, (125, 211, 252, 245)),
        (0.545, 0.545, (255, 255, 255, 240)),
        (0.675, 0.360, (251, 191, 36, 250)),
    ]
    for cy, frac, color in rows:
        y0 = int(S * cy)
        x1 = x0 + int(S * frac)
        d.rounded_rectangle([x0, y0, x1, y0 + h], radius=r, fill=color)
    return canvas


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "assets")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    img = build()
    ico = os.path.join(out_dir, "app.ico")
    img.save(ico, format="ICO",
             sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    # 顺便留一张 PNG 方便 README / 商店页展示
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(out_dir, "app.png"))
    print("saved:", ico, os.path.getsize(ico), "bytes")


if __name__ == "__main__":
    main()
