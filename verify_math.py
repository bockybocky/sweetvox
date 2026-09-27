#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vocal_focus 設定檔的離線數學驗證（不需要裝 Equalizer APO、不需要 numpy）
驗三件事：
  1) mid/side 編碼 -> 濾波 -> 解碼 是否為無損還原（Copy 指令代數）
  2) 每個濾波器在關鍵頻率的實際增益（RBJ biquad，跟 Equalizer APO 同一套公式）
  3) 合成測試訊號：女聲(正中) vs 伴奏(兩側) 的能量比，開/關設定各是多少
"""
import cmath, math, random

# ---------- 1. Copy 指令的逐行代數（照文件：一行一個賦值，依序執行） ----------
def apo_chain(L, R, use_processing=True, side_db=-4.0, mid_filters=None):
    """完全照我寫的 config 順序模擬：
       Copy: R=0.5*L+-0.5*R        (R <- SIDE)
       Copy: L=L+-1.0*R            (L <- MID)
       [Channel: L] mid 濾波 / [Channel: R] side 衰減(-4dB)
       Copy: L=L+R                 (L <- MID+SIDE 還原左)
       Copy: R=L+-2.0*R            (R <- MID-SIDE 還原右)
    """
    # encode
    R = 0.5 * L + -0.5 * R          # SIDE = (L-R)/2   (用的是舊 L, 舊 R)
    L = L + -1.0 * R                # MID  = L - SIDE = (L+R)/2
    if use_processing:
        g_side = 10 ** (side_db / 20.0)
        R *= g_side
        # mid 濾波（單一頻率正弦時等於乘上該頻率的增益）
        if mid_filters:
            L *= mid_filters
    # decode
    L = L + R                       # MID + SIDE = 原 L
    R = L + -2.0 * R                # (MID+SIDE) - 2*SIDE = MID - SIDE = 原 R
    return L, R

random.seed(7)
worst = 0.0
for _ in range(200000):
    L = random.uniform(-1, 1); R = random.uniform(-1, 1)
    oL, oR = apo_chain(L, R, use_processing=False)
    worst = max(worst, abs(oL - L), abs(oR - R))
print("1) mid/side 還原誤差（200000 組隨機取樣）:", worst)

# 濾波階段的能量檢查：中置訊號(女聲)不該被 side 衰減影響、側面訊號(伴奏)該被壓
mid_only = apo_chain(0.5, 0.5, use_processing=True, mid_filters=1.0)
side_only = apo_chain(0.5, -0.5, use_processing=True, mid_filters=1.0)
print("   正中訊號 -> L=%.4f R=%.4f (應≈0.5/0.5，不被 side 衰減動到)" % mid_only)
print("   側面訊號 -> L=%.4f R=%.4f (應≈0.3155/-0.3155 = -4.0 dB)" % side_only)
print("   側面訊號實測衰減: %.2f dB" % (20 * math.log10(abs(side_only[0]) / 0.5)))

# ---------- 2. RBJ biquad 頻率響應（與 Equalizer APO 的 PK/HP/LS/HS 同公式） ----------
def rbj(kind, fs, f0, gain_db=0.0, q=0.707):
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * math.pi * f0 / fs
    alpha = math.sin(w0) / (2 * q)
    cw = math.cos(w0)
    if kind == 'PK':
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == 'LS':
        sq = 2 * math.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cw + sq), 2 * A * ((A - 1) - (A + 1) * cw),
             A * ((A + 1) - (A - 1) * cw - sq)]
        a = [(A + 1) + (A - 1) * cw + sq, -2 * ((A - 1) + (A + 1) * cw),
             (A + 1) + (A - 1) * cw - sq]
    elif kind == 'HS':
        sq = 2 * math.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cw + sq), -2 * A * ((A - 1) + (A + 1) * cw),
             A * ((A + 1) + (A - 1) * cw - sq)]
        a = [(A + 1) - (A - 1) * cw + sq, 2 * ((A - 1) - (A + 1) * cw),
             (A + 1) - (A - 1) * cw - sq]
    elif kind == 'HP':
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    else:
        raise ValueError(kind)
    b = [x / a[0] for x in b]; a = [x / a[0] for x in a]
    return b, a

def resp_db(filt, fs, f):
    kind, f0, g, q = filt
    b, a = rbj(kind, fs, f0, g, q)
    z = cmath.exp(-2j * math.pi * f / fs)
    H = (b[0] + b[1] * z + b[2] * z ** 2) / (a[0] + a[1] * z + a[2] * z ** 2)
    return 20 * math.log10(abs(H))

# 我寫進 config 的 mid（女聲）鏈
MID = [('HP', 35, 0, 0.7), ('LS', 150, 1.5, 0.7), ('PK', 350, -3.0, 1.4),
       ('PK', 3000, 2.5, 0.9), ('PK', 7500, -1.5, 2.0), ('HS', 10000, -1.5, 0.707)]
SIDE_PREAMP_DB = -4.0

def mid_total_db(f, fs=48000):
    return sum(resp_db(x, fs, f) for x in MID)

print("\n2) MID（女聲/中央）鏈的實測響應 (fs=48k):")
for f in [50, 150, 250, 350, 700, 1500, 3000, 5000, 7500, 10000, 14000]:
    print("   %6d Hz : %+5.2f dB" % (f, mid_total_db(f)))
print("   SIDE（伴奏/兩側）: 全頻 %.1f dB，2 kHz 另有 -1.5 dB 凹陷" % SIDE_PREAMP_DB)

# ---------- 3. 女聲 vs 伴奏 的相對能量變化 ----------
# 女聲: 以 3 kHz 為主的中央訊號；伴奏: 以 300 Hz 與 8 kHz 為主的兩側訊號
voice_f = [700, 1500, 3000, 5000]      # 女聲主要泛音
back_f = [300, 800, 2000, 8000]        # 伴奏牆主要成分
def band_power(freqs, is_mid):
    p = 0.0
    for f in freqs:
        g = mid_total_db(f) if is_mid else (SIDE_PREAMP_DB + (0 if f != 2000 else -1.5))
        p += 10 ** (g / 10.0)
    return p
v0 = band_power(voice_f, True)
b0 = band_power(back_f, False)
print("\n3) 開設定後，女聲頻段相對伴奏頻段的能量:")
print("   女聲(中央)增益: %+.2f dB 平均" % (10 * math.log10(v0 / len(voice_f))))
print("   伴奏(兩側)增益: %+.2f dB 平均" % (10 * math.log10(b0 / len(back_f))))
print("   => 女聲/伴奏 能量比提升: %+.2f dB" % (10 * math.log10(v0 / len(voice_f)) - 10 * math.log10(b0 / len(back_f))))
