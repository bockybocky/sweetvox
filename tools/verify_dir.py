#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A/B 方向驗證：用同一段粉紅噪音（乾淨 WASAPI 播放管線），分別在兩組參數下側錄 M-DAC 輸出。
用法: python verify_dir.py <標籤1> <參數json> <標籤2> <參數json>
例:  python verify_dir.py old '{"sweet":2.5,"air":-1.5}' new '{"sweet":1.2,"air":1.5}'
"""
import importlib.util, json, os, subprocess, sys, time

APP = r"E:\AI\workspace\vocal_focus\app\vocal_focus_gui.py"
PINK = r"E:\AI\workspace\vocal_focus\test\pink96.wav"
OUTDIR = r"E:\AI\workspace\vocal_focus\test"
PLAYER = r"E:\AI\workspace\vocal_focus\tools\lb_play.py"

spec = importlib.util.spec_from_file_location("gui", APP)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

for tag, pj in ((sys.argv[1], sys.argv[2]), (sys.argv[3], sys.argv[4])):
    v = dict(g.DEFAULTS); v.update(json.loads(pj)); v["on"] = True
    ok, msg = g.write_files(v)
    print(f"[{tag}] 寫入 {ok} {msg}  sweet={v['sweet']} air={v['air']} side={v['side']} "
          f"(自動餘裕 {- (max(v['sweet'], v['warm'], v['air'], 0.0) + 1.0):.1f} dB)")
    time.sleep(0.6)
    out = os.path.join(OUTDIR, f"rec_{tag}.wav")
    r = subprocess.run([sys.executable, PLAYER, out, "4"],
                       capture_output=True, text=True)
    print("       " + (r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[-200:]))
print("最後把設定還原成預設：", g.write_files(dict(g.DEFAULTS, on=True)))
