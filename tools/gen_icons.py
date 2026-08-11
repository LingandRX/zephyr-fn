#!/usr/bin/env python3
"""生成应用图标（纯 Python，无第三方依赖）。

输出：
  ICON.PNG / ICON_256.PNG          应用包根目录图标（64 / 256）
  app/ui/images/icon_64.png / icon_256.png  桌面入口图标

风格：圆角矩形 + 渐变背景 + 白色卡片图形（符合 fnOS 图标规范）。
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SS = 4  # 超采样倍数


def clamp(v: int) -> int:
    return max(0, min(255, v))


def lerp(a, b, t):
    return a + (b - a) * t


def rounded_rect_alpha(x, y, w, h, r, px, py):
    """返回像素 (px,py) 在圆角矩形内的覆盖率 [0,1]。"""
    if px < x or px >= x + w or py < y or py >= y + h:
        return 0.0
    cx = min(max(px + 0.5, x + r), x + w - r)
    cy = min(max(py + 0.5, y + r), y + h - r)
    dx = px + 0.5 - cx
    dy = py + 0.5 - cy
    dist = (dx * dx + dy * dy) ** 0.5
    if dist <= r:
        return 1.0
    return max(0.0, 1.0 - (dist - r))


def render(size: int) -> bytes:
    W = size * SS
    bg = (99, 102, 241)      # indigo
    bg2 = (139, 92, 246)     # purple
    white = (255, 255, 255)

    rows = []
    for py in range(W):
        row = bytearray()
        for px in range(W):
            # 背景圆角矩形（占满画布，圆角半径 ~22%）
            bg_a = rounded_rect_alpha(0, 0, W, W, W * 0.22, px, py)
            t = py / max(1, W - 1)
            r = clamp(int(lerp(bg[0], bg2[0], t)))
            g = clamp(int(lerp(bg[1], bg2[1], t)))
            b = clamp(int(lerp(bg[2], bg2[2], t)))

            # 白色卡片（居中，圆角，宽 72%，高 52%）
            cw, ch = W * 0.72, W * 0.52
            cx, cy = (W - cw) / 2, (W - ch) / 2
            card_a = rounded_rect_alpha(cx, cy, cw, ch, ch * 0.16, px, py)

            # 卡片上的图形：芯片（小圆角矩形）+ 两条横线 + 支付圆
            chip_a = rounded_rect_alpha(cx + cw * 0.08, cy + ch * 0.16, cw * 0.22, ch * 0.20,
                                        ch * 0.06, px, py)
            line1_a = rounded_rect_alpha(cx + cw * 0.08, cy + ch * 0.52, cw * 0.55, ch * 0.055,
                                         ch * 0.03, px, py)
            line2_a = rounded_rect_alpha(cx + cw * 0.08, cy + ch * 0.66, cw * 0.42, ch * 0.055,
                                         ch * 0.03, px, py)
            circle_cx, circle_cy, circle_r = cx + cw * 0.78, cy + ch * 0.30, ch * 0.13
            d = ((px + 0.5 - circle_cx) ** 2 + (py + 0.5 - circle_cy) ** 2) ** 0.5
            circle_a = clamp(1.0 - (d - circle_r)) / 255.0 if d > circle_r else 1.0

            shape_a = max(chip_a, line1_a, line2_a, circle_a)
            alpha = bg_a * (1.0 - card_a) + card_a * shape_a
            alpha = max(0.0, min(1.0, alpha))
            # 前景色：卡片区域用白色
            if card_a > 0.5 and shape_a > 0.5:
                fr, fg, fb = 238, 240, 255
            else:
                fr, fg, fb = r, g, b
            row += bytes([clamp(int(fr)), clamp(int(fg)), clamp(int(fb)),
                          clamp(int(alpha * 255))])
        rows.append(bytes(row))

    # 超采样降采样
    out = bytearray()
    for py in range(size):
        for px in range(size):
            rs = [0, 0, 0, 0]
            for sy in range(SS):
                for sx in range(SS):
                    i = ((py * SS + sy) * W + (px * SS + sx)) * 4
                    for c in range(4):
                        rs[c] += rows[(py * SS + sy)][(px * SS + sx) * 4 + c]
            n = SS * SS
            out += bytes([rs[0] // n, rs[1] // n, rs[2] // n, rs[3] // n])
    return _encode_png(size, size, bytes(out))


def _encode_png(w: int, h: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main() -> None:
    targets = {
        REPO_ROOT / "ICON.PNG": 64,
        REPO_ROOT / "ICON_256.PNG": 256,
        REPO_ROOT / "app/ui/images/icon_64.png": 64,
        REPO_ROOT / "app/ui/images/icon_256.png": 256,
    }
    for path, size in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(render(size))
        print(f"生成 {path} ({size}x{size}, {path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
