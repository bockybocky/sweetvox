"""截圖客觀檢查：拉桿拉柄看不看得見、字銳不銳利（用數字判斷，不靠眼睛）。
用法: sep/.venv/Scripts/python.exe tools/check_gui_pixels.py <png>
"""
import sys

import numpy as np

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

ACCENT = (0xFF, 0x8F, 0xB1)   # 甜嗓粉（拉桿拉柄）
AMBER = (0xFF, 0xC4, 0x6B)    # 真空管琥珀（推力拉柄＋數值）
TROUGH = (0x0B, 0x0C, 0x10)   # 滑桿槽


def main():
    p = sys.argv[1] if len(sys.argv) > 1 else r"E:\AI\workspace\vocal_focus\gui_sweetvox.png"
    if not HAVE_PIL:
        print("沒有 PIL，無法讀 PNG")
        return
    im = Image.open(p).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    H, W, _ = a.shape
    print(f"圖 {W}x{H}")

    def near(color, tol=26):
        return (np.abs(a - np.array(color)).max(axis=2) <= tol)

    pink, amber, trough = near(ACCENT), near(AMBER), near(TROUGH)
    print(f"粉色(拉桿) {pink.sum():>7d} px    琥珀色 {amber.sum():>7d} px    滑桿槽 {trough.sum():>7d} px")

    # 拉桿列：同一列同時有「槽」和「粉/琥珀」＝拉柄真的畫出來了
    rows = []
    for y in range(H):
        t = trough[y].sum()
        c = pink[y].sum() + amber[y].sum()
        if t > 40 and c > 4:
            rows.append((y, int(t), int(c)))
    print(f"\n同時有滑桿槽與彩色拉柄的列：{len(rows)} 列")
    for y, t, c in rows[:12]:
        print(f"   y={y:4d}  槽 {t:4d} px  拉柄 {c:3d} px")

    # 銳利度：灰階梯度（糊掉的字梯度會攤平）
    g = (a[:, :, 0] * 0.299 + a[:, :, 1] * 0.587 + a[:, :, 2] * 0.114)
    gx = np.abs(np.diff(g, axis=1))
    gy = np.abs(np.diff(g, axis=0))
    grad = np.maximum(gx[:-1, :], gy[:, :-1])
    hot = grad > 60
    print(f"\n銳利度指標（梯度 >60 的邊緣像素）: {hot.sum()} px  ({hot.mean()*100:.2f}% 畫面)")
    print(f"梯度最大值 {grad.max():.0f}、前 1% 門檻 {np.percentile(grad, 99):.0f}")
    print("（文字若被系統放大重畫，邊緣梯度會低於 ~120、最大值也拉不高）")


if __name__ == "__main__":
    main()
