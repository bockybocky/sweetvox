#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A/B 驗證（乾淨管線版）：套用兩組參數，各自用固定種子白噪音側錄 M-DAC 輸出。
用法: python verify_dir2.py <標籤1> <json1> <標籤2> <json2> [每組錄幾次]
"""
import importlib.util, json, os, subprocess, sys, time

APP    = r"E:\AI\workspace\vocal_focus\app\vocal_focus_gui.py"
PLAYER = r"E:\AI\workspace\vocal_focus\tools\lb_play2.py"
OUTDIR = r"E:\AI\workspace\vocal_focus\test"

spec = importlib.util.spec_from_file_location("gui", APP)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

reps = int(sys.argv[5]) if len(sys.argv) > 5 else 1
pairs = ((sys.argv[1], sys.argv[2]), (sys.argv[3], sys.argv[4]))
for rep in range(1, reps + 1):
    for tag, pj in pairs:
        if reps > 1:
            tag = f"{tag}{rep}"
        v = dict(g.DEFAULTS); v.update(json.loads(pj)); v["on"] = True
        ok, msg = g.write_files(v)
        pa = -(max(v["sweet"], v["warm"], v["air"], 0.0) + 1.0)
        print(f"[{tag}] {ok} {msg}  sweet={v['sweet']} air={v['air']} side={v['side']} 自動餘裕={pa:.1f}dB")
        time.sleep(0.6)
        out = os.path.join(OUTDIR, f"rec_{tag}.wav")
        r = subprocess.run([sys.executable, PLAYER, out, "4"], capture_output=True, text=True)
        print("       " + (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[-200:]))
print("還原預設：", g.write_files(dict(g.DEFAULTS, on=True)))
