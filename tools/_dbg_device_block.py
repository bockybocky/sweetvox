#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""診斷：Device: Benchmark 條件區塊現在還生不生效？（找為什麼五組量到一樣）"""
import hashlib, os, subprocess, shutil
import numpy as np, soundfile as sf

BENCH = r"C:\Program Files\EqualizerAPO\Benchmark.exe"
DIR = r"C:\Program Files\EqualizerAPO\config"
CFG = os.path.join(DIR, "config.txt")
INC = os.path.join(DIR, "sweetvox_bench.txt")
WORK = r"E:\AI\workspace\vocal_focus\test"
SR = 96000
IN = os.path.join(WORK, "q3_music.wav")

backup = open(CFG, "rb").read()
print("原 config.txt："); print(open(CFG, encoding="utf-8").read())
print("-" * 60)

def run(label, cfg_text, inc_text):
    open(INC, "w", encoding="utf-8").write(inc_text)
    open(CFG, "w", encoding="utf-8").write(cfg_text)
    out = os.path.join(WORK, "q3out_diag.wav")
    r = subprocess.run([BENCH, "-i", IN, "-o", out, "--nopause"], capture_output=True, text=True)
    y, _ = sf.read(out, always_2d=True, dtype="float64")
    x, _ = sf.read(IN, always_2d=True, dtype="float64")
    lv = 20 * np.log10(np.sqrt((y ** 2).mean()) / np.sqrt((x ** 2).mean()))
    print(f"{label:52s} 音量 {lv:+7.2f} dB   stderr={r.stderr.strip()[:60]!r}")
    for line in (r.stdout or "").splitlines():
        if "onfig" in line or "rror" in line or "nclude" in line or "gain" in line:
            print("     log:", line.strip()[:100])
    return lv

try:
    # 1) 只有 Device 區塊（原本那招）
    run("1) Device: Benchmark + Include（原本那招）",
        "# 女聲前移：目前關閉（原聲）\n# Include: sweetvox_custom.txt\nDevice: Benchmark\nInclude: sweetvox_bench.txt\n",
        "Preamp: -20.0 dB\n")
    # 2) 前面多一行「有效」的 Include（模擬他現在 config.txt 是開著的）
    run("2) 前面多一行有效的 Include",
        "# 註解\nInclude: sweetvox_custom.txt\nDevice: Benchmark\nInclude: sweetvox_bench.txt\n",
        "Preamp: -20.0 dB\n")
    # 3) 沒有 Device 那行（應該兩個裝置都吃）
    run("3) 只有 Include: sweetvox_bench.txt（無 Device）",
        "# 註解\nInclude: sweetvox_bench.txt\n",
        "Preamp: -20.0 dB\n")
    # 4) Device 寫在 Include 之後
    run("4) Include 先、Device 後",
        "# 註解\nInclude: sweetvox_bench.txt\nDevice: Benchmark\nInclude: sweetvox_bench.txt\n",
        "Preamp: -20.0 dB\n")
finally:
    open(CFG, "wb").write(backup)
    print("-" * 60)
    print("config.txt 已還原，md5", hashlib.md5(open(CFG, "rb").read()).hexdigest())
    if os.path.exists(INC):
        os.remove(INC)
