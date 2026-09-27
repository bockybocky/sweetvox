"""生成手機用 EQ 曲線：加深重音、抬中音、少高音（沿用甜嗓的 350Hz 去濁 / 3k 甜度 / 7.5k 收齒音）。
輸出：phone/甜嗓_手機EQ.txt（10 段圖形 EQ ＋ 參數式 EQ 兩種格式，Wavelet/JamesDSP/Poweramp/Qudelix 都能用）
用法: sep/.venv/Scripts/python.exe tools/make_phone_eq.py
"""
import os

import numpy as np

FS = 48000.0
BANDS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]


def biquad(kind, f0, gain_db, q, fs=FS):
    A = 10 ** (gain_db / 40.0)
    w = 2 * np.pi * f0 / fs
    cw, sw = np.cos(w), np.sin(w)
    alpha = sw / (2 * q)
    if kind == "LS":
        b = [A * ((A + 1) - (A - 1) * cw + 2 * np.sqrt(A) * alpha),
             2 * A * ((A - 1) - (A + 1) * cw),
             A * ((A + 1) - (A - 1) * cw - 2 * np.sqrt(A) * alpha)]
        a = [(A + 1) + (A - 1) * cw + 2 * np.sqrt(A) * alpha,
             -2 * ((A - 1) + (A + 1) * cw),
             (A + 1) + (A - 1) * cw - 2 * np.sqrt(A) * alpha]
    elif kind == "HS":
        b = [A * ((A + 1) + (A - 1) * cw + 2 * np.sqrt(A) * alpha),
             -2 * A * ((A - 1) + (A + 1) * cw),
             A * ((A + 1) + (A - 1) * cw - 2 * np.sqrt(A) * alpha)]
        a = [(A + 1) - (A - 1) * cw + 2 * np.sqrt(A) * alpha,
             2 * ((A - 1) - (A + 1) * cw),
             (A + 1) - (A - 1) * cw - 2 * np.sqrt(A) * alpha]
    else:  # PK
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    return np.array(b) / a[0], np.array(a) / a[0]


# 甜嗓手機版曲線：他的要求（低音加深、中音多一些、高音少些）＋甜嗓本來的三個記號
CHAIN = [
    ("LS", 110, 7.0, 0.70),    # 重音：110 Hz 以下整體抬 7 dB
    ("PK", 200, 0.0, 1.00),    # （佔位，讓 250 附近不跟著隆起）
    ("PK", 350, -2.5, 1.40),   # 甜嗓：去濁
    ("PK", 1000, 2.5, 0.90),   # 中音：人聲厚度／清晰度
    ("PK", 3000, 3.0, 0.90),   # 中音：甜嗓的女聲甜度
    ("PK", 7500, -2.0, 1.60),  # 高音：收齒音
    ("HS", 9000, -4.0, 0.70),  # 高音：9 kHz 以上整體降 4 dB
]


def response(freqs, chain=CHAIN):
    out = np.ones(len(freqs), dtype=complex)
    for kind, f0, g, q in chain:
        b, a = biquad(kind, f0, g, q)
        z = np.exp(-2j * np.pi * np.asarray(freqs) / FS)
        out *= (b[0] + b[1] * z + b[2] * z ** 2) / (a[0] + a[1] * z + a[2] * z ** 2)
    return 20 * np.log10(np.abs(out))


def main():
    band_db = response([float(f) for f in BANDS])
    peak = response(np.linspace(20, 20000, 2000)).max()
    print("10 段數值（dB，正=加強 負=減少）：")
    for f, d in zip(BANDS, band_db):
        print(f"   {f:>6d} Hz : {d:+5.1f}")
    print(f"\n整條曲線最大增益 {peak:+.1f} dB（給播放器的 Preamp 就填 -{max(peak,0):.1f} dB，避免爆音）")

    out_dir = r"E:\AI\workspace\vocal_focus\phone"
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "甜嗓_手機EQ.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write("甜嗓 SweetVox — 手機版 EQ（加深重音 / 抬中音 / 少高音）\n")
        f.write("用途：手機播 YouTube Music。手機的 EQ 只能由『系統級 EQ App』或『帶 PEQ 的藍牙 DAC』套用。\n")
        f.write("=" * 68 + "\n\n")
        f.write("【格式 1】10 段圖形 EQ（Wavelet、內建音效、多數 App 直接照著拉）\n")
        f.write("    頻率(Hz)   增益(dB)\n")
        for fq, d in zip(BANDS, band_db):
            f.write(f"    {fq:>7d}   {d:+6.1f}\n")
        f.write(f"\n    播放器 Preamp / 前級：-{max(peak, 0):.1f} dB\n")
        f.write("\n【格式 2】參數式 EQ（Wavelet 自訂、RootlessJamesDSP、Poweramp、Qudelix 5K）\n")
        f.write("    類型    頻率       增益       Q\n")
        names = {"LS": "Low Shelf", "HS": "High Shelf", "PK": "Peaking"}
        for kind, f0, g, q in CHAIN:
            if g == 0:
                continue
            f.write(f"    {names[kind]:<9s} {f0:>6d} Hz  {g:+5.1f} dB  Q {q:.2f}\n")
        f.write("\n【甜嗓的記號（為什麼不只三個旋鈕）】\n")
        f.write("    350 Hz -2.5 dB  去掉悶濁，人聲才會『乾淨地往前站』\n")
        f.write("    3 kHz  +3.0 dB  女聲甜度（這一格是甜嗓的招牌）\n")
        f.write("    7.5 kHz -2.0 dB 收齒音，尖銳的ㄕㄘ音變柔\n")
        f.write("    9 kHz 以上 -4 dB 高音整體退一步（你要的『高音少些』）\n")
        f.write("\n【格式 3】Qudelix 5K PEQ（iPhone 唯一能動 YouTube Music 的走法：EQ 做在硬體裡）\n")
        f.write("    Qudelix App → 5K DAC AMP → Equalizer → PEQ（機器內建 20 段，填下面 6 段就夠）\n")
        f.write("    Pre-gain: -7.0 dB\n")
        f.write("    段數  類型        頻率       增益      Q\n")
        for i, (kind, f0, g, q) in enumerate([c for c in CHAIN if c[2] != 0], start=1):
            f.write(f"    {i:<4d}  {names[kind]:<10s} {f0:>6d} Hz  {g:+5.1f} dB  Q {q:.2f}\n")
        f.write("\n【iPhone 上的替代方案（不花錢的）】\n")
        f.write("    · iOS 的『耳機調節』(設定→輔助使用→音訊/視覺) 只有 AirPods/Beats 這類支援的耳機才生效，\n")
        f.write("      而且只能套預設幾檔或上傳聽力圖，形狀不夠自由 → 只能當粗略版\n")
        f.write("    · 換播放器：Spotify 有內建 EQ、Apple Music 有 23 組預設 EQ（但就不是 YouTube Music 了）\n")
        f.write("\n【怎麼套用】\n")
        f.write("  安卓：安裝 Wavelet → Custom / Graphic EQ 照上面拉；或 RootlessJamesDSP（需 Shizuku 或 ADB 授權）\n")
        f.write("  iPhone：系統不允許第三方 App 動聲音 → 只能用帶 PEQ 的藍牙 DAC（如 Qudelix 5K）輸入上面的參數式 EQ\n")
        f.write("  有線耳機/喇叭接手機：同樣是上面的 App 或硬體 PEQ，跟播放軟體無關\n")
    print(f"\n已寫出 {p}")


if __name__ == "__main__":
    main()
