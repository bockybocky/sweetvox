#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""比較「同一組旋鈕、不同的做法」對音質的客觀影響（不干擾線上播放）。

量五件事：音量變化、立體相關（音場寬度）、THD（失真）、女聲前移量（3 kHz 正中 vs 兩側的增益差）、
滿刻度掃頻峰值（會不會削波）。

用法:
  sep/.venv/Scripts/python.exe tools/measure_modes.py
"""
import os as _os; _ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 倉庫根目錄
import hashlib, importlib.util, json, os, re, subprocess, sys, time
import numpy as np
import soundfile as sf

HERE = _ROOT
BENCH = r"C:\Program Files\EqualizerAPO\Benchmark.exe"
APO_CFG_DIR = r"C:\Program Files\EqualizerAPO\config"
APO_CONFIG = os.path.join(APO_CFG_DIR, "config.txt")
BENCH_INC = os.path.join(APO_CFG_DIR, "sweetvox_bench.txt")
WORK = os.path.join(HERE, "test")
SR = 96000

spec = importlib.util.spec_from_file_location("g", os.path.join(HERE, "app", "vocal_focus_gui.py"))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
base = dict(g.DEFAULTS)
base.update(json.load(open(os.path.join(HERE, "app", "state.json"), encoding="utf-8")))
base["on"] = True
print("他目前的旋鈕：" + json.dumps({k: base[k] for k in ("side", "sweet", "mud", "sib", "warm", "air",
      "gain", "tube", "tube_drive", "vst_air", "centerbass", "subcut")}, ensure_ascii=False))

def V(**kw):
    st = dict(base); st.update(kw); return st

PIANO = dict(g.PRESETS["鋼琴（發燒）"])
FLAT = dict(side=0.0, sweet=0.0, mud=0.0, sib=0.0, warm=0.0, air=0.0, subcut=0.0,
            centerbass=False, tube=False, tube_drive=0.0, vst_air=False, gain=0.0,
            side_band=False, piano=False)

variants = [
    ("A 直通基準（全 0 dB、無飽和、中側矩陣留著）", V(**FLAT)),
    ("B 他現在在聽的這組（發燒＋真空管推力 9）", V()),
    ("C 鋼琴（發燒）預設（只衰減 → 不可能削波）", V(**PIANO)),
    ("D 鋼琴＋泛音 +1 dB", V(**{**PIANO, "air": 1.0})),
    ("E 鋼琴＋真空管推力 9（示範代價）", V(**{**PIANO, "tube": True, "tube_drive": 9.0})),
]

# ---- config.txt：測試鏈只放在 Device: Benchmark 區塊（線上裝置不受影響）----
CONFIG_BENCH = ("# 女聲前移：目前關閉（原聲）\n"
                "# Include: sweetvox_custom.txt\n"
                "# ↓ 只有 Benchmark.exe（--devicename Benchmark）讀這一段；線上 M-DAC 不受影響\n"
                "Device: Benchmark\n"
                "Include: sweetvox_bench.txt\n")
backup = open(APO_CONFIG, "rb").read()
bak_md5 = hashlib.md5(backup).hexdigest()

def wretryb(path, data, tries=40, delay=0.25):
    """還原備份時用二進位寫：文字模式會把 \\r\\n 變成 \\r\\r\\n，live 檔會被弄髒。"""
    last = None
    for _ in range(tries):
        try:
            with open(path, "wb") as f:
                f.write(data); f.flush(); os.fsync(f.fileno())
            return
        except PermissionError as e:
            last = e; time.sleep(delay)
    raise last

def restore():
    wretryb(APO_CONFIG, backup)
    now = hashlib.md5(open(APO_CONFIG, "rb").read()).hexdigest()
    print(f"\nconfig.txt 還原 md5 {now} {'OK' if now == bak_md5 else '**不一致**'}")
    if os.path.exists(BENCH_INC):
        os.remove(BENCH_INC)

# ---- 訊號 ----
rng = np.random.default_rng(11)
def pink(n):
    X = np.fft.rfft(rng.standard_normal(n)); f = np.fft.rfftfreq(n, 1 / SR); f[0] = f[1]
    x = np.fft.irfft(X / np.sqrt(f), n); return x / np.abs(x).max()

N = SR * 4
t = np.arange(SR * 2) / SR
s3 = 0.25 * np.sin(2 * np.pi * 3000 * t)
s1 = 0.25 * np.sin(2 * np.pi * 1000 * t)
_p1, _p2 = pink(N), pink(N)          # 兩條獨立亂數（量立體相關用）
probes = {
    "mid":       np.stack([_p1, _p1], axis=1),        # 純正中：L 與 R 完全一樣
    "side":      np.stack([_p1, -_p1], axis=1),       # 純兩側：L 與 R 完全反相
    "music":     np.stack([_p1, _p2], axis=1),        # 不相關雙聲道
    "sine1k":    np.stack([s1, s1], axis=1),
    "s3k_mid":   np.stack([s3, s3], axis=1),
    "s3k_side":  np.stack([s3, -s3], axis=1),
}
for k, v in probes.items():
    sf.write(os.path.join(WORK, f"q3_{k}.wav"), v.astype(np.float32), SR, subtype="FLOAT")

def bench(inp=None, tag="x"):
    if inp is None:      # 讓 Benchmark 自己產生滿刻度掃頻
        args = ["-r", str(SR), "-l", "5", "-f", "20", "-t", "20000", "-c", "2"]
    else:
        args = ["-i", inp, "-o", os.path.join(WORK, f"q3out_{tag}.wav")]
    r = subprocess.run([BENCH] + args + ["--nopause"], capture_output=True, text=True)
    m = re.search(r"Max output level: [\d.]+ \(([-\d.]+) dB\)", r.stdout)
    peak = float(m.group(1)) if m else None
    if inp is None:
        return None, peak
    return sf.read(os.path.join(WORK, f"q3out_{tag}.wav"), always_2d=True, dtype="float64")[0], peak

def rms(x): return float(np.sqrt((x ** 2).mean()))

def analyse(res):
    m = {}
    om, im = res["music"], probes["music"]
    m["level_db"] = 20 * np.log10(rms(om) / rms(im))
    def corr(x):
        a, b = x[:, 0] - x[:, 0].mean(), x[:, 1] - x[:, 1].mean()
        return float((a * b).sum() / (np.sqrt((a ** 2).sum() * (b ** 2).sum()) + 1e-30))
    m["corr_in"], m["corr_out"] = corr(im), corr(om)
    m["residual_mid_db"] = 20 * np.log10(np.abs(res["mid"][:, 0] - res["mid"][:, 1]).max() / (rms(res["mid"]) + 1e-30) + 1e-30)
    m["residual_side_db"] = 20 * np.log10(np.abs(res["side"][:, 0] + res["side"][:, 1]).max() / (rms(res["side"]) + 1e-30) + 1e-30)
    m["mid_keep_db"] = 20 * np.log10(rms(res["mid"]) / (rms(probes["mid"]) + 1e-30))
    m["side_keep_db"] = 20 * np.log10(rms(res["side"]) / (rms(probes["side"]) + 1e-30))
    # 女聲前移量：3 kHz 正中 vs 兩側，各自對輸入的增益差
    def gain(res_key, in_key):
        return 20 * np.log10(rms(res[res_key]) / rms(probes[in_key]))
    m["gain_3k_mid"] = gain("s3k_mid", "s3k_mid")
    m["gain_3k_side"] = gain("s3k_side", "s3k_side")
    m["vocal_forward_db"] = m["gain_3k_mid"] - m["gain_3k_side"]
    # THD
    x = res["sine1k"][:SR, 0]; X = np.fft.rfft(x)
    def rr(fc, w=3):
        k = int(round(fc * SR / SR)); return float(np.sqrt(np.sum(np.abs(X[k - w:k + w + 1]) ** 2)) / SR * 2)
    fund = rr(1000); hs = {k: rr(1000 * k) for k in range(2, 11)}
    m["thd_percent"] = float(np.sqrt(sum(v ** 2 for v in hs.values())) / (fund + 1e-30) * 100)
    m["even_db"] = 20 * np.log10(np.sqrt(sum(v ** 2 for k, v in hs.items() if k % 2 == 0)) / (fund + 1e-30) + 1e-30)
    m["odd_db"] = 20 * np.log10(np.sqrt(sum(v ** 2 for k, v in hs.items() if k % 2 == 1)) / (fund + 1e-30) + 1e-30)
    # 頻率響應
    n = min(len(im), len(om)); seg = 16384; n = (n // seg) * seg; win = np.hanning(seg)
    Sxx = np.zeros(seg // 2 + 1); Sxy = np.zeros(seg // 2 + 1, dtype=complex)
    for k in range(0, n, seg):
        X2 = np.fft.rfft(im[k:k + seg, 0] * win); Y2 = np.fft.rfft(om[k:k + seg, 0] * win)
        Sxx += np.abs(X2) ** 2; Sxy += Y2 * np.conj(X2)
    H = Sxy / (Sxx + 1e-30); fr = np.fft.rfftfreq(seg, 1 / SR)
    m["response_db"] = {str(fc): float(20 * np.log10(np.abs(H[int(np.argmin(np.abs(fr - fc)))]) + 1e-30))
                        for fc in (60, 250, 1000, 3000, 6000, 12000)}
    return m

def md5f(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()

def wretry(path, text, tries=40, delay=0.25):
    """config.txt 常常被 APO／介面握著（PermissionError）→ 重試，跟介面同一招。"""
    last = None
    for _ in range(tries):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush(); os.fsync(f.fileno())
            return
        except PermissionError as e:
            last = e; time.sleep(delay)
    raise last

def arm(inc_text):
    """把測試 config 寫進去，回傳「此刻的指紋」；之後每次呼叫 Benchmark 前後都要對得上。"""
    wretry(BENCH_INC, inc_text)
    wretry(APO_CONFIG, CONFIG_BENCH)
    return md5f(BENCH_INC), md5f(APO_CONFIG)

def still_armed(h):
    return (md5f(BENCH_INC), md5f(APO_CONFIG)) == h

out, tamper = {}, 0
try:
    for label, st in variants:
        for attempt in range(1, 5):
            h = arm(g.build_config(st))
            res, bad = {}, False
            for tag in probes:
                if not still_armed(h):
                    bad = True; break
                res[tag], _ = bench(os.path.join(WORK, f"q3_{tag}.wav"), tag)
                if not still_armed(h):
                    bad = True; break
            if not bad:
                if not still_armed(h):
                    bad = True
                else:
                    _, sweep_peak = bench(None, "sweep")
                    bad = not still_armed(h)
            if not bad:
                break
            tamper += 1
            print(f"  ⚠ 「{label}」量到一半設定檔被別的程序改寫（他動了介面），第 {attempt} 次重測…")
        else:
            print(f"  ✗ 「{label}」量不到：介面一直把 config.txt 搶回去")
            out[label] = {"error": "設定檔被搶走"}
            continue
        m = analyse(res)
        m["sweep_peak_dbfs"] = sweep_peak
        m["preamp_db"] = g.safe_preamp(st)
        out[label] = m
        print(f"\n── {label} ──")
        print(f"  音量 {m['level_db']:+6.2f} dB   立體相關 {m['corr_in']:+.3f} → {m['corr_out']:+.3f}"
              f"   THD {m['thd_percent']:.3f}%（偶 {m['even_db']:.0f} / 奇 {m['odd_db']:.0f} dBc）")
        print(f"  女聲前移（3 kHz 正中−兩側） {m['vocal_forward_db']:+.2f} dB"
              f"   滿刻度掃頻峰值 {m['sweep_peak_dbfs']:+.2f} dBFS   自動 Preamp {m['preamp_db']:+.1f} dB")
        print(f"  中/側殘差（越小＝矩陣越透明） {m['residual_mid_db']:.0f} / {m['residual_side_db']:.0f} dBFS"
              f"   中側保留 {m['mid_keep_db']:+.2f} / {m['side_keep_db']:+.2f} dB")
        print(f"  頻響 " + "  ".join(f"{k} {v:+.1f}" for k, v in m["response_db"].items()))
    print(f"\n量測期間設定檔被搶走次數：{tamper}（已自動重測）")
finally:
    restore()

with open(os.path.join(HERE, "MEASURE_piano_20260925.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"原始數據：{os.path.join(HERE, 'MEASURE_piano_20260925.json')}")
