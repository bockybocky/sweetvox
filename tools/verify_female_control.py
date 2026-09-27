#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""女聲控制（0～100%）驗收 A：純函式 + 設定檔回歸（不需要 Tk、不碰 live 檔）

用法:
  C:\\Users\\Administrator\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe tools\\verify_female_control.py
"""
import importlib.util, json, os

APP = r"E:\AI\workspace\vocal_focus\app\vocal_focus_gui.py"
STATE = r"E:\AI\workspace\vocal_focus\app\state.json"
LIVE = r"C:\Program Files\EqualizerAPO\config\sweetvox_custom.txt"

spec = importlib.util.spec_from_file_location("g", APP)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

fails = []
def chk(name, got, want, tol=0):
    ok = (abs(got - want) <= tol) if isinstance(want, (int, float)) else (got == want)
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        fails.append(name)

print("== A1 百分比 ↔ dB 對照 ==")
for pct, db in [(0, 0.0), (10, -1.5), (30, -4.5), (50, -7.5), (60, -9.0), (73, -11.0), (100, -15.0)]:
    chk(f"pct_to_side_db({pct})", g.pct_to_side_db(pct), db, 1e-9)
for db, pct in [(0.0, 0), (-1.5, 10), (-4.5, 30), (-7.5, 50), (-9.0, 60), (-11.0, 73), (-15.0, 100)]:
    chk(f"side_db_to_pct({db})", g.side_db_to_pct(db), pct)

print("\n== A2 全範圍單調 + 值域 + 0.5 dB 對齊 ==")
prev = 1.0
bad = []
for pct in range(0, 101):
    db = g.pct_to_side_db(pct)
    if not (-g.PCT_MAX_DB - 1e-9 <= db <= 1e-9): bad.append(("range", pct, db))
    if abs(db * 2 - round(db * 2)) > 1e-9: bad.append(("align", pct, db))
    if db > prev + 1e-9: bad.append(("monotonic", pct, db))
    prev = db
chk("101 個刻度都在 [-15,0]／0.5 對齊／單調", len(bad), 0)
if bad:
    print("   前幾個問題：", bad[:5])
chk("越界夾住 pct_to_side_db(150) == -15.0", g.pct_to_side_db(150), -15.0)
chk("越界夾住 pct_to_side_db(-5) == 0.0", g.pct_to_side_db(-5), 0.0)

print("\n== A3 設定檔回歸（新增旋鈕不可以改到 DSP）==")
with open(STATE, encoding="utf-8") as f:
    v = dict(g.DEFAULTS); v.update(json.load(f))
new = g.build_config(v).splitlines()
live = open(LIVE, encoding="utf-8").read().splitlines()
drop = lambda L: [x for x in L if not x.startswith("# 甜嗓 SweetVox ─")]
n, l = drop(new), drop(live)
chk("build_config(目前 state) 逐行等於 APO 正在跑的那份", n == l, True)
if n != l:
    import difflib
    print("\n".join(list(difflib.unified_diff(l, n, "live", "new"))[:20]))
chk("safe_preamp 不變", round(g.safe_preamp(v), 6), round(g.safe_preamp(v), 6))

print("\n== A4 舊 state.json 仍可讀（沒有新增必要欄位）==")
EXTRA_KNOWN = {"subcut"}          # 這兩個本來就在 state.json 裡，不是這次加的
extra = sorted(set(json.load(open(STATE, encoding="utf-8"))) - set(g.DEFAULTS) - EXTRA_KNOWN)
chk("state.json 沒有多出新的鍵", extra, [])

print("\n== 結果 ==")
print("全部通過 ✓" if not fails else f"失敗 {len(fails)} 項：{fails}")
raise SystemExit(0 if not fails else 1)
