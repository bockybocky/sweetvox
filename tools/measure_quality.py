#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""音質客觀量測：把測試訊號餵進「現在正在跑的 APO 設定」，量
  ① 中／側重新組合有沒有樣本對齊（有延遲 = 梳狀濾波 = 高頻糊掉）
  ② 延遲幾樣本  ③ 加了多重諧波失真（THD）多少  ④ 實際頻率響應與音量變化

用法（需要 numpy + soundfile，用 sep/.venv）：
  sep/.venv/Scripts/python.exe tools/measure_quality.py [--rate 96000] [--dir test]

判準（發燒友等級）：重新組合殘差 ≤ −100 dBFS、對齊誤差 0 樣本、THD < 0.01%、音量變化 0 dB。
"""
import os as _os; _ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 倉庫根目錄
import argparse, json, os, subprocess, sys
import numpy as np
import soundfile as sf

HERE = _ROOT
BENCH = r"C:\Program Files\EqualizerAPO\Benchmark.exe"

ap = argparse.ArgumentParser()
ap.add_argument("--rate", type=int, default=96000)      # 裝置 shared-mode 的取樣率
ap.add_argument("--dir", default=os.path.join(HERE, "test"))
a = ap.parse_args()
D = a.dir
os.makedirs(D, exist_ok=True)
SR = a.rate

rng = np.random.default_rng(20260925)

def pink(n, ch):
    """近似粉紅噪音（頻譜 1/f），兩聲道同一組或反相由呼叫端決定"""
    w = rng.standard_normal(n)
    X = np.fft.rfft(w)
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = f[1] if f[1] > 0 else 1.0
    X = X / np.sqrt(f)
    x = np.fft.irfft(X, n)
    x = x / np.abs(x).max() * 0.25
    return np.stack([x] * ch, axis=1) if ch == 2 else x[:, None]

# ---------------- 產生測試訊號 ----------------
def write(name, x):
    p = os.path.join(D, name)
    sf.write(p, x.astype(np.float32), SR, subtype="FLOAT")
    return p

N = SR * 4
noise = pink(N, 1)[:, 0]
mid  = np.stack([noise, noise], axis=1)
side = np.stack([noise, -noise], axis=1)
imp  = np.zeros((SR // 2, 2), dtype=np.float64)
imp[1000, :] = 0.5
t = np.arange(SR * 3) / SR
sine = 0.25 * np.sin(2 * np.pi * 1000 * t)          # 1 kHz，振幅 0.25

probes = {
    "q_mid":  write("q_mid.wav", mid),                    # 純正中（女聲）
    "q_side": write("q_side.wav", side),                  # 純兩側（伴奏）
    "q_imp":  write("q_imp.wav", imp),                     # 單一脈衝
    "q_sine": write("q_sine.wav", np.stack([sine, sine], axis=1)),
}

# ---------------- 跑 Benchmark（用「現在正在跑」的那份 config）----------------
outs = {}
for k, p in probes.items():
    o = os.path.join(D, f"qout_{k}.wav")
    r = subprocess.run([BENCH, "-i", p, "-o", o, "--nopause"],
                       capture_output=True, text=True, cwd=os.path.dirname(BENCH))
    if r.returncode != 0 or not os.path.exists(o):
        print(f"!! Benchmark 失敗 {k}: rc={r.returncode}\n{r.stdout}\n{r.stderr}")
        sys.exit(1)
    outs[k] = o

def load(p, n=None):
    x, sr = sf.read(p, always_2d=True, dtype="float64")
    return x[:n] if n else x

res = {"rate": SR, "files": {}}
def rms(x):
    return float(np.sqrt(np.mean(x ** 2)))

# ---- ① 純正中：L 與 R 必須逐樣本相同（不同 = 中/側重新組合沒對齊）----
i, o = load(probes["q_mid"]), load(outs["q_mid"])
diff = np.abs(o[:, 0] - o[:, 1])
lvl = rms(o)
res["mid_symmetry"] = {
    "out_rms_db": 20 * np.log10(lvl + 1e-30),
    "max_lr_diff": float(diff.max()),
    "max_lr_diff_db": 20 * np.log10(diff.max() / lvl + 1e-30),
    "rms_lr_diff_db": 20 * np.log10(np.sqrt(np.mean(diff ** 2)) / lvl + 1e-30),
}
# 對齊檢查：L 與 R 的互相關峰值延遲
def best_lag(x, y, maxlag=200):
    n = len(x)
    X, Y = np.fft.rfft(x, 2 * n), np.fft.rfft(y, 2 * n)
    c = np.fft.irfft(X * np.conj(Y))
    c = np.concatenate([c[-maxlag:], c[:maxlag + 1]])
    k = int(np.argmax(np.abs(c))) - maxlag
    return k, float(np.abs(c).max() / (np.abs(c).mean() + 1e-30))
lag, peak = best_lag(o[:, 0], o[:, 1])
res["mid_symmetry"]["lag_L_vs_R_samples"] = lag

# ---- ② 純兩側：L 與 R 必須互為反相 ----
i2, o2 = load(probes["q_side"]), load(outs["q_side"])
diff2 = np.abs(o2[:, 0] + o2[:, 1])
lvl2 = rms(o2)
lag2, _ = best_lag(o2[:, 0], -o2[:, 1])
res["side_symmetry"] = {
    "out_rms_db": 20 * np.log10(lvl2 + 1e-30),
    "max_lr_sum": float(diff2.max()),
    "max_lr_sum_db": 20 * np.log10(diff2.max() / lvl2 + 1e-30),
    "rms_lr_sum_db": 20 * np.log10(np.sqrt(np.mean(diff2 ** 2)) / lvl2 + 1e-30),
    "lag_L_vs_minusR_samples": lag2,
}

# ---- ③ 脈衝：延遲幾樣本、兩聲道是否同時到 ----
oi = load(outs["q_imp"])
pk = [int(np.argmax(np.abs(oi[:, c]))) for c in range(2)]
res["impulse"] = {
    "in_peak_index": 1000,
    "out_peak_index_L": pk[0], "out_peak_index_R": pk[1],
    "latency_samples_L": pk[0] - 1000, "latency_samples_R": pk[1] - 1000,
    "peak_abs": float(np.abs(oi).max()),
}
# 脈衝前後有無預鈴振（非因果／相位失真）
pre = np.abs(oi[:1000, :]).max()
res["impulse"]["pre_ringing_db"] = 20 * np.log10(pre / (np.abs(oi).max() + 1e-30) + 1e-30)

# ---- ④ 音量變化 + 頻率響應（粉紅噪音 Welch）----
def transfer(xin, xout, sr, seg=16384):
    n = min(len(xin), len(xout))
    n = (n // seg) * seg
    xin, xout = xin[:n, 0], xout[:n, 0]
    win = np.hanning(seg)
    Sxx = np.zeros(seg // 2 + 1); Syy = np.zeros_like(Sxx); Sxy = np.zeros_like(Sxx, dtype=complex)
    for k in range(0, n, seg):
        X = np.fft.rfft(xin[k:k + seg] * win); Y = np.fft.rfft(xout[k:k + seg] * win)
        Sxx += np.abs(X) ** 2; Syy += np.abs(Y) ** 2; Sxy += Y * np.conj(X)
    f = np.fft.rfftfreq(seg, 1 / sr)
    H = Sxy / (Sxx + 1e-30)
    return f, H

f, H = transfer(i, o, SR)
anchors = [30, 60, 120, 250, 350, 500, 1000, 2000, 3000, 5000, 7500, 10000, 14000, 18000]
resp = {}
for fc in anchors:
    k = int(np.argmin(np.abs(f - fc)))
    resp[str(fc)] = float(20 * np.log10(np.abs(H[k]) + 1e-30))
res["response_db_vs_input"] = resp
res["level_change_db"] = {
    "mid_probe": float(20 * np.log10(rms(o) / rms(i))),
    "side_probe": float(20 * np.log10(rms(o2) / rms(i2))),
}

# ---- ⑤ THD（1 kHz）----
oi_s = load(outs["q_sine"])[:, 0]
ii_s = load(probes["q_sine"])[:, 0]
M = SR  # 整 1 秒 = 1000 個週期，剛好對齊
X = np.fft.rfft(oi_s[:M]); Xin = np.fft.rfft(ii_s[:M])
fr = np.fft.rfftfreq(M, 1 / SR)
def bin_rms(spec, fc, w=3):
    k = int(round(fc * M / SR))
    return float(np.sqrt(np.sum(np.abs(spec[k - w:k + w + 1]) ** 2)) / M * 2)
fund = bin_rms(X, 1000)
harm = {h: bin_rms(X, 1000 * h) for h in range(2, 11)}
thd = float(np.sqrt(sum(v ** 2 for v in harm.values())) / (fund + 1e-30) * 100)
res["thd_1kHz"] = {
    "in_fundamental_rms": bin_rms(Xin, 1000),
    "out_fundamental_rms": fund,
    "harmonics_rms": {str(k): v for k, v in harm.items()},
    "thd_percent": thd,
    "thd_db_below_fundamental": float(20 * np.log10(thd / 100 + 1e-30)),
}
res["thd_1kHz"]["out_vs_in_level_db"] = float(20 * np.log10(fund / (bin_rms(Xin, 1000) + 1e-30)))

# ---------------- 驗收判準 ----------------
def verdict(name, ok, detail):
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    res.setdefault("checks", {})[name] = {"pass": bool(ok), "detail": detail}

print(f"\n裝置取樣率 {SR} Hz；Benchmark 用的是「現在正在跑」的那份 config\n")
print("== ① 純正中（女聲）：L 與 R 應該逐樣本相同 ==")
m = res["mid_symmetry"]
verdict("中/側組合對齊（L−R 殘差）", m["max_lr_diff_db"] <= -100,
        f"最大差 {m['max_lr_diff_db']:.1f} dBFS（RMS 差 {m['rms_lr_diff_db']:.1f} dB）、聲道間延遲 {m['lag_L_vs_R_samples']} 樣本")
print("\n== ② 純兩側（伴奏）：L 與 R 應該互為反相 ==")
s = res["side_symmetry"]
verdict("側面反相對稱（L+R 殘差）", s["max_lr_sum_db"] <= -100,
        f"最大差 {s['max_lr_sum_db']:.1f} dBFS（RMS 差 {s['rms_lr_sum_db']:.1f} dB）、延遲 {s['lag_L_vs_minusR_samples']} 樣本")
print("\n== ③ 脈衝 ==")
im = res["impulse"]
verdict("零延遲（脈衝峰不移動）", im["latency_samples_L"] == 0 and im["latency_samples_R"] == 0,
        f"L {im['latency_samples_L']} 樣本、R {im['latency_samples_R']} 樣本、預鈴振 {im['pre_ringing_db']:.0f} dB")
print("\n== ④ 音量與頻率響應 ==")
print(f"  音量變化：正中 {res['level_change_db']['mid_probe']:+.2f} dB、兩側 {res['level_change_db']['side_probe']:+.2f} dB")
print("  頻率響應（相對輸入）：" + "  ".join(f"{k}Hz {v:+.1f}" for k, v in resp.items()))
print("\n== ⑤ 1 kHz 諧波失真 ==")
th = res["thd_1kHz"]
verdict("THD（發燒友門檻 < 0.01%）", th["thd_percent"] < 0.01,
        f"THD {th['thd_percent']:.3f}%（比基頻低 {th['thd_db_below_fundamental']:.1f} dB）、基頻位準變化 {th['out_vs_in_level_db']:+.2f} dB")

out_json = os.path.join(HERE, "MEASURE_quality_20260925.json")
with open(out_json, "w", encoding="utf-8") as fp:
    json.dump(res, fp, ensure_ascii=False, indent=2)
print(f"\n原始數據：{out_json}")
