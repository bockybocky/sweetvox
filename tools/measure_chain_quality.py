#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量「甜嗓那條鏈」的客觀音質指標（不干擾線上播放）。

關鍵手法：APO 設定支援 `Device: <名稱>` 條件區塊，而 Benchmark.exe 解析設定時用的裝置名稱是
"Benchmark"（--devicename 預設值）。所以把測試鏈放在 `Device: Benchmark` 區塊裡 →
**只有離線量測吃得到，線上裝置（M-DAC）一點都不受影響**，也不需要來回切換 config.txt。

用法:
  tools/measure_chain_quality.py            # 量：他的現在的鏈 / 去掉飽和外掛 / 只有拆中側 三種
"""
import os as _os; _ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 倉庫根目錄
import hashlib, importlib.util, json, os, shutil, subprocess, sys
import numpy as np
import soundfile as sf

HERE = _ROOT
BENCH = r"C:\Program Files\EqualizerAPO\Benchmark.exe"
APO_CFG_DIR = r"C:\Program Files\EqualizerAPO\config"
APO_CONFIG = os.path.join(APO_CFG_DIR, "config.txt")
BENCH_INC = os.path.join(APO_CFG_DIR, "sweetvox_bench.txt")
WORK = os.path.join(HERE, "test")
SR = 96000

# ---- 載入桌面版的設定計算 ----
spec = importlib.util.spec_from_file_location("g", os.path.join(HERE, "app", "vocal_focus_gui.py"))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
state = dict(g.DEFAULTS)
state.update(json.load(open(os.path.join(HERE, "app", "state.json"), encoding="utf-8")))

def cfg_current():
    st = dict(state); st["on"] = True
    return g.build_config(st)

def cfg_nosat():
    st = dict(state); st["on"] = True; st["tube"] = False; st["vst_air"] = False; st["gain"] = 0.0
    return g.build_config(st)

def cfg_split_only():
    return ("# 測試：只拆中側再還原，不任何濾波/前級/VST（檢查矩陣本身是否透明）\n"
            "Preamp: 0.0 dB\n"
            "Channel: all\n"
            "Copy: R=0.5*L+-0.5*R\n"
            "Copy: L=L+-1.0*R\n"
            "Channel: all\n"
            "Copy: L=L+R\n"
            "Copy: R=L+-2.0*R\n")

# ---- config.txt 換成「只有離線工具吃得到」的版本 ----
CONFIG_BENCH = ("# 女聲前移：目前關閉（原聲）\n"
                "# Include: sweetvox_custom.txt\n"
                "# ↓ 只有 Benchmark.exe（--devicename Benchmark）會讀這一段，線上 M-DAC 不受影響\n"
                "Device: Benchmark\n"
                "Include: sweetvox_bench.txt\n")

backup = open(APO_CONFIG, "rb").read()
bak_md5 = hashlib.md5(backup).hexdigest()
print(f"config.txt 原樣備份 md5 {bak_md5}（量完會還原並核對）")

def restore():
    with open(APO_CONFIG, "wb") as f:
        f.write(backup)
    now = hashlib.md5(open(APO_CONFIG, "rb").read()).hexdigest()
    print(f"config.txt 還原：md5 {now} {'OK' if now == bak_md5 else '**不一致**'}")
    if os.path.exists(BENCH_INC):
        os.remove(BENCH_INC)

# ---- 測試訊號 ----
rng = np.random.default_rng(7)
def pink(n):
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR); f[0] = f[1]
    x = np.fft.irfft(X / np.sqrt(f), n)
    return x / np.abs(x).max()

N = SR * 4
noise = pink(N)
imp = np.zeros(SR // 2); imp[1000] = 0.5
t = np.arange(SR * 3) / SR
sine = 0.25 * np.sin(2 * np.pi * 1000 * t)
probes = {
    "mid":     np.stack([noise, noise], axis=1),                 # 純正中
    "side":    np.stack([noise, -noise], axis=1),                # 純兩側
    "music":   np.stack([pink(N), pink(N)], axis=1),             # 不相關雙聲道（像真的音樂）
    "imp":     np.stack([imp, imp], axis=1),
    "sine":    np.stack([sine, sine], axis=1),
}
for k, v in probes.items():
    sf.write(os.path.join(WORK, f"q2_{k}.wav"), v.astype(np.float32), SR, subtype="FLOAT")

def bench(inp, tag):
    out = os.path.join(WORK, f"q2out_{tag}.wav")
    r = subprocess.run([BENCH, "-i", inp, "-o", out, "--nopause"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        print("Benchmark 失敗：", r.stdout[-400:], r.stderr[-400:]); restore(); sys.exit(1)
    return sf.read(out, always_2d=True, dtype="float64")[0], r.stdout

def metrics(res, inp):
    """res: dict tag → 輸出陣列"""
    m = {}
    o, i = res["mid"][:len(probes["mid"])], probes["mid"]
    m["mid_lr_diff_db"] = 20 * np.log10(np.abs(o[:, 0] - o[:, 1]).max() / (np.sqrt((o ** 2).mean()) + 1e-30) + 1e-30)
    o2 = res["side"][:len(probes["side"])]
    m["side_lr_sum_db"] = 20 * np.log10(np.abs(o2[:, 0] + o2[:, 1]).max() / (np.sqrt((o2 ** 2).mean()) + 1e-30) + 1e-30)
    oi = res["imp"]
    pk = [int(np.argmax(np.abs(oi[:, c]))) for c in range(2)]
    m["latency_samples"] = [pk[0] - 1000, pk[1] - 1000]
    m["pre_ring_db"] = 20 * np.log10(np.abs(oi[950:1000]).max() / (np.abs(oi).max() + 1e-30) + 1e-30)
    # 音量與峰值因數（音樂型訊號）
    om, im = res["music"], probes["music"]
    m["level_db"] = 20 * np.log10((np.sqrt((om ** 2).mean()) + 1e-30) / (np.sqrt((im ** 2).mean()) + 1e-30))
    m["crest_in_db"] = 20 * np.log10(np.abs(im).max() / (np.sqrt((im ** 2).mean()) + 1e-30))
    m["crest_out_db"] = 20 * np.log10(np.abs(om).max() / (np.sqrt((om ** 2).mean()) + 1e-30))
    # 立體相關性（左右相似度）
    def corr(x):
        a, b = x[:, 0] - x[:, 0].mean(), x[:, 1] - x[:, 1].mean()
        return float((a * b).sum() / (np.sqrt((a ** 2).sum() * (b ** 2).sum()) + 1e-30))
    m["corr_in"], m["corr_out"] = corr(im), corr(om)
    # THD（1 kHz）
    x = res["sine"][:SR, 0]
    X = np.fft.rfft(x)
    def rr(fc, w=3):
        k = int(round(fc * SR / SR))
        return float(np.sqrt(np.sum(np.abs(X[k - w:k + w + 1]) ** 2)) / SR * 2)
    fund = rr(1000)
    hs = {k: rr(1000 * k) for k in range(2, 11)}
    m["thd_percent"] = float(np.sqrt(sum(v ** 2 for v in hs.values())) / (fund + 1e-30) * 100)
    m["even_db"] = 20 * np.log10(np.sqrt(sum(v ** 2 for k, v in hs.items() if k % 2 == 0)) / (fund + 1e-30) + 1e-30)
    m["odd_db"] = 20 * np.log10(np.sqrt(sum(v ** 2 for k, v in hs.items() if k % 2 == 1)) / (fund + 1e-30) + 1e-30)
    # 頻率響應（不相關雙聲道粉紅噪音，取 L）
    n = min(len(im), len(om)); seg = 16384; n = (n // seg) * seg
    win = np.hanning(seg); Sxx = np.zeros(seg // 2 + 1); Sxy = np.zeros(seg // 2 + 1, dtype=complex)
    for k in range(0, n, seg):
        X = np.fft.rfft(im[k:k + seg, 0] * win); Y = np.fft.rfft(om[k:k + seg, 0] * win)
        Sxx += np.abs(X) ** 2; Sxy += Y * np.conj(X)
    H = Sxy / (Sxx + 1e-30)
    fr = np.fft.rfftfreq(seg, 1 / SR)
    m["response_db"] = {str(fc): float(20 * np.log10(np.abs(H[int(np.argmin(np.abs(fr - fc)))]) + 1e-30))
                        for fc in (30, 60, 120, 250, 500, 1000, 3000, 5000, 8000, 12000, 16000)}
    return m

variants = [
    ("現在的鏈（真空管開＋通透/Air 開＋補償 +6）", cfg_current()),
    ("去掉飽和外掛（只有 EQ＋拆中側）", cfg_nosat()),
    ("只有拆中側（矩陣本身，透明性測試）", cfg_split_only()),
]

allres = {}
try:
    with open(APO_CONFIG, "w", encoding="utf-8") as f:
        f.write(CONFIG_BENCH)
    for label, cfg in variants:
        with open(BENCH_INC, "w", encoding="utf-8") as f:
            f.write(cfg)
        res = {}
        for tag in probes:
            res[tag], _ = bench(os.path.join(WORK, f"q2_{tag}.wav"), tag)
        m = metrics(res, probes)
        allres[label] = m
        print(f"\n── {label} ──")
        print(f"  中/側組合殘差：正中 L−R {m['mid_lr_diff_db']:8.1f} dBFS   兩側 L+R {m['side_lr_sum_db']:8.1f} dBFS")
        print(f"  延遲 {m['latency_samples']} 樣本　預鈴振 {m['pre_ring_db']:.0f} dB")
        print(f"  音量 {m['level_db']:+.2f} dB　峰值因數 {m['crest_in_db']:.1f} → {m['crest_out_db']:.1f} dB")
        print(f"  立體相關 {m['corr_in']:+.3f} → {m['corr_out']:+.3f}")
        print(f"  THD {m['thd_percent']:.3f}%　偶次 {m['even_db']:.1f} dBc　奇次 {m['odd_db']:.1f} dBc")
        print("  頻率響應：" + "  ".join(f"{k} {v:+.1f}" for k, v in m["response_db"].items()))
finally:
    restore()

with open(os.path.join(HERE, "MEASURE_chain_quality_20260925.json"), "w", encoding="utf-8") as f:
    json.dump(allres, f, ensure_ascii=False, indent=2)
print(f"\n原始數據：{os.path.join(HERE, 'MEASURE_chain_quality_20260925.json')}")
