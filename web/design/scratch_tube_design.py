#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""挑一個 WaveShaper 曲線：1 kHz 正弦、-12 dBFS 入力、pre/post = +/- drive dB
目標 THD(推力 6 dB) 1%~3%，且偶次為主。"""
import math

def thd(curve, amp, drive_db, n=48000, fs=48000, f=1000.0):
    g = 10 ** (drive_db / 20.0)
    xs = [amp * g * math.sin(2 * math.pi * f * i / fs) for i in range(n)]
    ys = [curve(x) for x in xs]
    # DFT 取諧波 1..12
    mags = []
    for h in range(1, 13):
        re = sum(y * math.cos(2 * math.pi * h * f * i / fs) for i, y in enumerate(ys))
        im = sum(y * math.sin(2 * math.pi * h * f * i / fs) for i, y in enumerate(ys))
        mags.append(2 * math.hypot(re, im) / n)
    fund = mags[0]
    tot = math.sqrt(sum(m * m for m in mags[1:]))
    odd = math.sqrt(sum(mags[h - 1] ** 2 for h in (3, 5, 7, 9, 11)))
    even = math.sqrt(sum(mags[h - 1] ** 2 for h in (2, 4, 6, 8, 10, 12)))
    return 100 * tot / fund, 100 * mags[1] / fund, (20 * math.log10(even / odd) if odd > 0 else 99), fund

def mk_bias(b):
    tb = math.tanh(b)
    norm = 1.0 / (1.0 - tb * tb)
    return lambda x: (math.tanh(b + x) - tb) * norm

def mk_tanh(k):
    return lambda x: math.tanh(k * x)

def mk_asym(kp, kn):
    return lambda x: math.tanh(kp * x) if x >= 0 else math.tanh(kn * x)

AMP = 10 ** (-12 / 20.0)   # -12 dBFS = 0.2512

print("=== A: tanh(k x) 純奇次（不會有偶次，當對照） ===")
for k in (0.5, 1.0, 2.0, 4.0):
    r = thd(mk_tanh(k), AMP, 6.0)
    print("  k=%.1f  THD=%.3f%%  H2=%.3f%%  even-odd=%+.1f dB" % (k, r[0], r[1], r[2]))

print("=== B: 偏壓 tanh（平滑、偶次） ===")
for b in (0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0):
    c = mk_bias(b)
    r6 = thd(c, AMP, 6.0)
    r0 = thd(c, AMP, 0.0)
    print("  b=%.2f  推力6dB THD=%.3f%%  H2=%.3f%%  even-odd=%+.1f dB | 推力0 THD=%.3f%%  DC=%+.5f"
          % (b, r6[0], r6[1], r6[2], r0[0], c(0.0)))

print("=== D: 非對稱 tanh（兩半不同斜率） ===")
for kp, kn in ((1.0, 1.4), (1.0, 1.8), (1.2, 2.0)):
    c = mk_asym(kp, kn)
    r6 = thd(c, AMP, 6.0)
    print("  kp=%.1f kn=%.1f  推力6dB THD=%.3f%%  H2=%.3f%%  even-odd=%+.1f dB" % (kp, kn, r6[0], r6[1], r6[2]))

print()
print("=== 候選：bias=0.3 掃推力，跟桌面版實測表比 ===")
c = mk_bias(0.3)
tbl = [(0, 0.29), (3, 0.54), (6, 0.98), (9, 1.82), (12, 3.40), (15, 6.38), (18, 11.71)]
for d, want in tbl:
    r = thd(c, AMP, d)
    print("  推力 %2d dB: 網頁 THD=%.2f%%（桌面版實測 %.2f%%）  偶-奇 %+.1f dB" % (d, r[0], want, r[2]))

print()
print("=== bias=0.3 在不同入力準位（推力 6 dB）===")
for db in (-24, -18, -12, -6, 0):
    a = 10 ** (db / 20.0)
    r = thd(c, a, 6.0)
    print("  入力 %3d dBFS: THD=%.2f%%  H2=%.2f%%" % (db, r[0], r[1]))
