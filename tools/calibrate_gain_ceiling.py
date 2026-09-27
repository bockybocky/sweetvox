#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校準「整體音量補償」的安全上限：對每個 gain 值跑一次滿刻度掃頻，看峰值有沒有超過 −0.5 dBFS。"""
import hashlib, importlib.util, json, os, re, subprocess
import numpy as np

HERE = r"E:\AI\workspace\vocal_focus"
BENCH = r"C:\Program Files\EqualizerAPO\Benchmark.exe"
APO = r"C:\Program Files\EqualizerAPO\config\config.txt"
INC = r"C:\Program Files\EqualizerAPO\config\sweetvox_bench.txt"
SR = 96000

spec = importlib.util.spec_from_file_location("g", os.path.join(HERE, "app", "vocal_focus_gui.py"))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
base = dict(g.DEFAULTS); base.update(json.load(open(os.path.join(HERE, "app", "state.json"), encoding="utf-8"))); base["on"] = True

CONFIG_BENCH = ("# 女聲前移：目前關閉（原聲）\n# Include: sweetvox_custom.txt\n"
                "Device: Benchmark\nInclude: sweetvox_bench.txt\n")
backup = open(APO, "rb").read(); bak = hashlib.md5(backup).hexdigest()

def sweep_peak():
    r = subprocess.run([BENCH, "-r", str(SR), "-l", "5", "-f", "20", "-t", "20000", "-c", "2", "--nopause"],
                       capture_output=True, text=True)
    m = re.search(r"Max output level: [\d.]+ \(([-\d.]+) dB\)", r.stdout)
    return float(m.group(1)) if m else None

cases = [
    ("E 發燒（band −6、乾淨）", dict(side=-6.0, sweet=1.5, mud=-2.0, sib=0.0, warm=1.0, air=1.0,
                                    centerbass=False, subcut=35.0, tube=False, vst_air=False, side_band=True)),
    ("F 頻段 −9、乾淨", dict(side=-9.0, tube=False, vst_air=False, side_band=True, centerbass=False)),
    ("他原本的 EQ、頻段 −9、乾淨", dict(side=-9.0, tube=False, vst_air=False, side_band=True)),
    ("原本那條（full −9＋真空管＋Air）", dict()),
]
print(f"{'案例':32s} {'gain':>5s} {'Preamp':>8s} {'滿刻度峰值':>11s}  判定")
rows = []
try:
    open(APO, "w", encoding="utf-8").write(CONFIG_BENCH)
    for label, kw in cases:
        for gain in (0.0, 0.5, 1.0, 1.5, 2.0):
            st = dict(base); st.update(kw); st["gain"] = gain
            open(INC, "w", encoding="utf-8").write(g.build_config(st))
            pk = sweep_peak()
            pre = g.safe_preamp(st)
            eff = max(-24.0, min(pre + gain, pre + max(3.2 if st.get("vst_air") else 0.0, g.GAIN_CEIL_DB)))
            ok = "OK" if pk is not None and pk <= -0.5 else "**削波**"
            print(f"{label:32s} {gain:5.1f} {eff:8.1f} {pk:11.2f}  {ok}")
            rows.append((label, gain, eff, pk, ok))
finally:
    open(APO, "wb").write(backup)
    now = hashlib.md5(open(APO, "rb").read()).hexdigest()
    print(f"\nconfig.txt 還原 md5 {now} {'OK' if now == bak else '**不一致**'}")
    if os.path.exists(INC): os.remove(INC)
json.dump(rows, open(os.path.join(HERE, "MEASURE_gain_ceiling_20260925.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
