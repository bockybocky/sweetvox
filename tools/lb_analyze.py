#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量一個 wav 的 L/R 與 MID/SIDE 能量（dBFS）。"""
import sys, wave, struct, math

path = sys.argv[1]
w = wave.open(path)
n, ch, sw, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
raw = w.readframes(n)
w.close()
if sw != 2 or ch != 2:
    print(f"只支援 16-bit 立體聲，這個檔是 sw={sw} ch={ch}"); sys.exit(1)
s = struct.unpack("<%dh" % (len(raw) // 2), raw)
L, R = s[0::2], s[1::2]

def rms_db(x):
    if not x: return float("-inf")
    v = math.sqrt(sum(float(t) * t for t in x) / len(x)) / 32768.0
    return 20 * math.log10(v) if v > 0 else float("-inf")

mid = [(a + b) / 2 for a, b in zip(L, R)]
side = [(a - b) / 2 for a, b in zip(L, R)]
print(f"{path}: {rate} Hz, {n} frames")
print(f"  L    {rms_db(L):8.2f} dBFS")
print(f"  R    {rms_db(R):8.2f} dBFS")
print(f"  MID  {rms_db(mid):8.2f} dBFS   (正中／女聲)")
print(f"  SIDE {rms_db(side):8.2f} dBFS   (兩側／伴奏)")
print(f"  MID - SIDE = {rms_db(mid) - rms_db(side):+.2f} dB")
