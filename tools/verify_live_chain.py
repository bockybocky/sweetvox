#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""唯讀量測「現在線上那條鏈」（完全不動 config.txt，所以他聽音樂不會被打斷）。

原理：`config.txt` 頂層的 `Include: sweetvox_custom.txt` 對**所有裝置**生效（含 Benchmark，見 lessons L63），
所以直接叫 `Benchmark.exe -i <探針> -o <out>` 量出來的就是線上那條鏈。
（跟 measure_modes.py 的差別：那支會把測試鏈寫進 config.txt 的 Device: Benchmark 區塊，量測期間線上鏈是被關掉的。）

用 sep\\.venv 的 python 跑（只有那個環境有 numpy）。用法：
    python verify_live_chain.py [--tag 發燒]
輸出：E:\\AI\\workspace\\vocal_focus\\VERIFY_live_<tag>.json ＋ 螢幕對照 2026-09-25 的實測值
"""
import os as _os; _ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 倉庫根目錄
import argparse, datetime, hashlib, json, os, re, subprocess, sys
import numpy as np, soundfile as sf

BENCH = r"C:\Program Files\EqualizerAPO\Benchmark.exe"
APO   = r"C:\Program Files\EqualizerAPO\config"
WORK  = _os.path.join(_ROOT, r"test\liveverify")
HOME  = _ROOT
SR    = 96000

# 2026-09-25 同值實測（MEASURE_final_20260925.json 的 B 發燒模式）
REF = dict(vocal_forward_db=8.1376, level_db=-3.9816, corr_out=-0.18475,
           thd_percent=0.010524, sweep_peak_dbfs=-0.804828)

os.makedirs(WORK, exist_ok=True)
rng = np.random.default_rng(11)

def pink(n):
    X = np.fft.rfft(rng.standard_normal(n)); f = np.fft.rfftfreq(n, 1 / SR); f[0] = f[1]
    x = np.fft.irfft(X / np.sqrt(f), n); return x / np.abs(x).max()

N = SR * 4
t = np.arange(SR * 2) / SR
s3 = 0.25 * np.sin(2 * np.pi * 3000 * t); s1 = 0.25 * np.sin(2 * np.pi * 1000 * t)
_p1, _p2 = pink(N), pink(N)
probes = {"mid": np.stack([_p1, _p1], 1), "side": np.stack([_p1, -_p1], 1),
          "music": np.stack([_p1, _p2], 1), "sine1k": np.stack([s1, s1], 1),
          "s3k_mid": np.stack([s3, s3], 1), "s3k_side": np.stack([s3, -s3], 1)}
for k, v in probes.items():
    sf.write(os.path.join(WORK, f"lv_{k}.wav"), v.astype(np.float32), SR, subtype="FLOAT")

def md5f(p): return hashlib.md5(open(p, "rb").read()).hexdigest()

def bench(inp, tag):
    out = os.path.join(WORK, f"lvout_{tag}.wav")
    args = ["-i", inp, "-o", out] if inp else ["-r", str(SR), "-l", "5", "-f", "20", "-t", "20000", "-c", "2"]
    r = subprocess.run([BENCH] + args + ["--nopause"], capture_output=True, text=True, timeout=300)
    m = re.search(r"Max output level: [\d.]+ \(([-\d.]+) dB\)", r.stdout or "")
    peak = float(m.group(1)) if m else None
    if inp is None:
        return None, peak, r
    y = sf.read(out, always_2d=True, dtype="float64")[0]
    return y, peak, r

def rms(x): return float(np.sqrt((x ** 2).mean()))

cfg_md5_before = md5f(os.path.join(APO, "config.txt"))
inc_md5_before = md5f(os.path.join(APO, "sweetvox_custom.txt"))
res, peaks = {}, []
for k, v in probes.items():
    y, pk, r = bench(os.path.join(WORK, f"lv_{k}.wav"), k)
    res[k] = y
    if pk is not None: peaks.append(pk)

m = {}
om, im = res["music"], probes["music"]
m["level_db"] = 20 * np.log10(rms(om) / rms(im))
def corr(x):
    a, b = x[:, 0] - x[:, 0].mean(), x[:, 1] - x[:, 1].mean()
    return float((a * b).sum() / (np.sqrt((a ** 2).sum() * (b ** 2).sum()) + 1e-30))
m["corr_in"], m["corr_out"] = corr(im), corr(om)
m["residual_mid_db"] = 20 * np.log10(np.abs(res["mid"][:, 0] - res["mid"][:, 1]).max() / (rms(res["mid"]) + 1e-30) + 1e-30)
g = lambda rk, ik: 20 * np.log10(rms(res[rk]) / rms(probes[ik]))
m["gain_3k_mid"], m["gain_3k_side"] = g("s3k_mid", "s3k_mid"), g("s3k_side", "s3k_side")
m["vocal_forward_db"] = m["gain_3k_mid"] - m["gain_3k_side"]
x = res["sine1k"][:SR, 0]; X = np.fft.rfft(x)
def rr(fc, w=3):
    k = int(round(fc)); return float(np.sqrt(np.sum(np.abs(X[k - w:k + w + 1]) ** 2)) / SR * 2)
fund = rr(1000); hs = {k: rr(1000 * k) for k in range(2, 11)}
m["thd_percent"] = float(np.sqrt(sum(v ** 2 for v in hs.values())) / (fund + 1e-30) * 100)
# 滿刻度掃頻（同一份 config，唯讀）
_, peak, _ = bench(None, "sweep")
m["sweep_peak_dbfs"] = peak

# 量測期間有沒有被別人（介面／APO）改走
cfg_same = md5f(os.path.join(APO, "config.txt")) == cfg_md5_before
inc_same = md5f(os.path.join(APO, "sweetvox_custom.txt")) == inc_md5_before
m["_config_untouched"], m["_include_untouched"] = cfg_same, inc_same

print("== 線上那條鏈實測（%s）==" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
for k in ("vocal_forward_db", "level_db", "corr_out", "thd_percent", "sweep_peak_dbfs"):
    ref = REF.get(k)
    d = (m[k] - ref) if (ref is not None and m[k] is not None) else None
    print("  %-18s %+9.4f   (2026-09-25 同值 %s%s)" % (
        k, m[k] if m[k] is not None else float("nan"), ("%+.4f" % ref) if ref is not None else "—",
        ("   差 %+.4f" % d) if d is not None else ""))
print("  config.txt/include 量測前後未被改動:", cfg_same, inc_same)
out = os.path.join(HOME, "VERIFY_live_%s.json" % datetime.datetime.now().strftime("%Y%m%d_%H%M"))
json.dump({"measured": m, "ref_20260925": REF,
           "config_md5": cfg_md5_before, "include_md5": inc_md5_before},
          open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("寫出:", out)
