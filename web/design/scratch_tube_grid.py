#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 (k, b) 上找真空管曲線參數：推力 6 dB、-12 dBFS 正弦、THD 落在 1~3%，偶次為主，且推力加大時 THD 單調上升。"""
import math

FS, F, N = 48000, 1000.0, 48000

def thd_of(curve, amp, drive_db):
    g = 10 ** (drive_db / 20.0)
    ys = [curve(amp * g * math.sin(2 * math.pi * F * i / FS)) for i in range(N)]
    dc = sum(ys) / N
    mags = []
    for h in range(1, 13):
        re = sum(y * math.cos(2 * math.pi * h * F * i / FS) for i, y in enumerate(ys))
        im = sum(y * math.sin(2 * math.pi * h * F * i / FS) for i, y in enumerate(ys))
        mags.append(2 * math.hypot(re, im) / N)
    fund = mags[0]
    tot = math.sqrt(sum(m * m for m in mags[1:]))
    odd = math.sqrt(sum(mags[h - 1] ** 2 for h in (3, 5, 7, 9, 11)))
    even = math.sqrt(sum(mags[h - 1] ** 2 for h in (2, 4, 6, 8, 10, 12)))
    return 100 * tot / fund, (20 * math.log10(even / odd) if odd else 99), dc

def mk(k, b):
    tb = math.tanh(k * b)
    norm = 1.0 / (k * (1.0 - tb * tb))
    def c(x):
        t = math.tanh(k * (x + b)) - tb
        if t > 1.0: t = 1.0
        elif t < -1.0: t = -1.0
        return t * norm
    return c

AMP = 10 ** (-12 / 20.0)
print("  k     b     THD@6   偶-奇    DC       THD@0  THD@12  THD@18")
best = []
for k in (0.6, 0.8, 1.0, 1.2, 1.5, 2.0):
    for b in (0.02, 0.05, 0.08, 0.12, 0.18, 0.25):
        c = mk(k, b)
        t6, eo, dc = thd_of(c, AMP, 6.0)
        row = (k, b, t6, eo, dc, thd_of(c, AMP, 0.0)[0], thd_of(c, AMP, 12.0)[0], thd_of(c, AMP, 18.0)[0])
        if 1.0 <= t6 <= 3.0:
            best.append(row)
        print("  %.2f  %.2f   %5.2f%%  %+5.1f  %+.5f  %5.2f%%  %5.2f%%  %5.2f%%"
              % (k, b, t6, eo, dc, row[5], row[6], row[7]))
print()
print("落在 1~3%% 的候選：")
for r in best:
    print("  k=%.2f b=%.2f THD@6=%.2f%% 偶-奇%+.1f dB DC=%+.5f  (@0 %.2f%% @12 %.2f%% @18 %.2f%%)"
          % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]))
