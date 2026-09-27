#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""女聲控制（0～100%）驗收 B：真的把介面建起來、拉那顆旋鈕，看它有沒有動到 side、
   有沒有同步另一根滑桿、有沒有把 preset 標記清掉——全程寫到暫存路徑，不碰 live 設定檔。

用法:
  C:\\Users\\Administrator\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe tools\\verify_female_control_gui.py
"""
import os as _os; _ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 倉庫根目錄
import hashlib, json, os, shutil, time, tkinter as tk

SRC      = _os.path.join(_ROOT, r"app\vocal_focus_gui.py")
STATE    = _os.path.join(_ROOT, r"app\state.json")
LIVE_APO = r"C:\Program Files\EqualizerAPO\config\sweetvox_custom.txt"
LIVE_CFG = r"C:\Program Files\EqualizerAPO\config\config.txt"
TMP      = r"C:\Users\Administrator\AppData\Local\Temp\svx_probe"
PROBE    = os.path.join(TMP, "vocal_focus_gui_probe.py")
PROBE_APO = os.path.join(TMP, "apo")
PROBE_STATE = os.path.join(TMP, "state.json")

fails = []
def chk(name, got, want, tol=0):
    ok = (abs(got - want) <= tol) if isinstance(want, (int, float)) and not isinstance(want, bool) else (got == want)
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        fails.append(name)

def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()

# ---- 0) 造測試替身：只把三個路徑常數換成暫存路徑，其餘逐字元相同 ----
os.makedirs(PROBE_APO, exist_ok=True)
shutil.copy2(STATE, PROBE_STATE)
src = open(SRC, encoding="utf-8").read()
reps = [
    ('APO_DIR   = r"C:\\Program Files\\EqualizerAPO\\config"', f'APO_DIR   = r"{PROBE_APO}"'),
    ('STATE     = os.path.join(HERE, "state.json")',          f'STATE     = r"{PROBE_STATE}"'),
    ('EXPORT    = r"E:\\AI\\workspace\\vocal_focus"',          f'EXPORT    = r"{TMP}"'),
]
probe = src
for a, b in reps:
    assert probe.count(a) == 1, f"替身替換失敗（找不到或重複）：{a}"
    probe = probe.replace(a, b)
# 斷言替換真的生效（帳本 L114 的教訓：假測試＝真上線）
chk("替身裡已經沒有 live APO 路徑", "C:\\Program Files\\EqualizerAPO" in probe, False)
chk("替身裡真的指向暫存 APO", PROBE_APO in probe, True)
chk("替身檔不含 live 設定檔名以外的差異（長度差＝替換字串差）", len(probe), len(src) + sum(len(b) - len(a) for a, b in reps))
open(PROBE, "w", encoding="utf-8").write(probe)

# ---- live 檔的基準（跑完要比對沒有被寫）----
before = {p: (md5(p), os.path.getmtime(p)) for p in (LIVE_APO, LIVE_CFG)}
before_state = md5(STATE)

import importlib.util
spec = importlib.util.spec_from_file_location("gp", PROBE)
gp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gp)
gp.STATE = PROBE_STATE

checkstate = json.load(open(STATE, encoding="utf-8"))
root = tk.Tk()
root.withdraw()                        # 不要搶螢幕
swallowed = []
root.report_callback_exception = lambda *a: swallowed.append(repr(a[1]))
app = gp.App(root)
root.update_idletasks(); root.update()

print("\n== B1 初始狀態＝他現在那一組 ==")
his = json.load(open(STATE, encoding="utf-8"))
want_side = float(his["side"])
want_pct = gp.side_db_to_pct(want_side)
print(f"  （他現在的 state.json：side={want_side:+.1f} dB → 女聲控制應顯示 {want_pct}%）")
chk("載入他的 state.json", app.v["side"], want_side)
chk(f"女聲控制顯示 {want_pct}%", f"{want_pct}%" in app.pct_val.cget("text"), True)
chk("顯示的 dB 正確", (f"{want_side:+.1f}" in app.pct_val.cget("text"))
    or ("鋼琴模式" in app.pct_val.cget("text") and want_pct == 0), True)
chk(f"旋鈕位置＝{want_pct}", round(float(app.pct_sc.get())), want_pct)
chk("（暫存）設定檔寫到暫存夾", os.path.exists(os.path.join(PROBE_APO, "sweetvox_custom.txt")), True)
chk("建構期間沒有被吞掉的例外", swallowed, [])

print("\n== B1b 開起來時的亮燈要跟「值」一致（他 2026-09-25 指出）==")
want_lit = app._match_preset(app.v) if app.v.get("on") else None
lit = [n for n, b in app.preset_btns.items() if b.cget("bg") == gp.ACCENT]
print(f"  他的值剛好比對到：{want_lit}；實際亮的鈕：{lit}")
chk("亮燈的鈕＝值相符的那一組", lit, [] if want_lit is None else [want_lit])

print("\n== B2 拉「女聲控制」（核心：它真的會改到 APO 的 side）==")
# 他現在可能停在「原聲 A/B 關閉」（state.json 的 on=false）：那種情況 write_files() 只會寫 config.txt、
# 不寫 sweetvox_custom.txt（設計如此）。這一段要驗的是「開啟時寫出的內容」，所以先把 on 打開。
# 也把他當下可能勾著的「頻段式」關掉，讓這一段固定驗「整條兩側退」的寫法（見 L56：斷言不可以跟著他的 state 漂）。
app.v["on"] = True
app.v["side_band"] = False
app.band_cb.set(False)
app.v["piano"] = False          # 他可能正停在「鋼琴（發燒）」：鋼琴是另一條鏈（側面不寫 2.5 kHz）→ 本段固定驗女聲那條
print(f"  （state.json 的 on={json.load(open(STATE, encoding='utf-8')).get('on')}；本段測試強制 on=True、side_band=False、piano=False）")
for want_pct, want_db in [(0, 0.0), (30, -4.5), (60, -9.0), (100, -15.0), (73, -11.0)]:
    app.on_pct(want_pct)
    chk(f"拉到 {want_pct}% → side", app.v["side"], want_db, 1e-9)
    chk(f"  {want_pct}% → 下面那根滑桿跟著動", round(float(app.sliders["side"][0].get()), 2), want_db, 1e-9)
    chk(f"  {want_pct}% → 標籤", f"{want_pct}%" in app.pct_val.cget("text"), True)
    app.apply()                        # 真的寫檔（暫存）
    body = open(os.path.join(PROBE_APO, "sweetvox_custom.txt"), encoding="utf-8").read()
    chk(f"  {want_pct}% → 寫進 APO 的 Preamp 行", f"Preamp: {want_db:.1f} dB" in body, True)

print("\n== B2b 頻段式（side_band）寫出來的是 2.5 kHz 濾波器，不是兩側 Preamp ==")
app.v["side_band"] = True
app.band_cb.set(True)
app.on_pct(60)
app.apply()
body = open(os.path.join(PROBE_APO, "sweetvox_custom.txt"), encoding="utf-8").read()
side_block = body.split("# SIDE：伴奏")[-1].split("# 還原回 L/R")[0]
chk("  有 2.5 kHz 濾波器行（−9.0 dB）", "Filter 1: ON PK Fc 2500 Hz Gain -9.0 dB Q 0.7" in body, True)
chk("  兩側那一段完全沒有 Preamp 行（整條退的寫法）", "Preamp:" in side_block, False)
chk("  還是有還原回 L/R 的四行", body.count("Copy:") == 4, True)
app.v["side_band"] = False
app.band_cb.set(False)

print("\n== B3 拉下面那根滑桿 → 女聲控制要跟著跑 ==")
for db, want_pct in [(-9.0, 60), (-11.0, 73), (0.0, 0), (-4.0, 27)]:
    app.on_slide("side", db)
    chk(f"伴奏退後量 {db} dB → 女聲控制", round(float(app.pct_sc.get())), want_pct)
    chk(f"  標籤 {want_pct}%", f"{want_pct}%" in app.pct_val.cget("text"), True)

print("\n== B4 模式鈕／重設也要同步，而且不可以無限回圈 ==")
app.on_pct(40)
app.on_slide("side", -5.0)
time.sleep(0.05)
before_v = dict(app.v)
app.apply_preset("深夜甜嗓")
chk("按『深夜甜嗓』→ side=-9.0", app.v["side"], -9.0)
chk("  女聲控制跟著 = 60%", round(float(app.pct_sc.get())), 60)
chk("  模式鈕亮起（甜嗓粉）", app.preset_btns["深夜甜嗓"].cget("bg"), gp.ACCENT)
chk("  其他模式鈕沒亮", app.preset_btns["淡"].cget("bg"), gp.CARD2)
app.on_pct(20)                          # 手動拉過 → 模式標記要清掉
chk("手動拉女聲控制後，模式標記清掉", app.preset_btns["深夜甜嗓"].cget("bg"), gp.CARD2)
app.reset()
chk("重設 → side=-7.0（預設）", app.v["side"], -7.0)
chk("  女聲控制 = 47%", round(float(app.pct_sc.get())), 47)
chk("state 字典沒有被回圈改壞（欄位數不變）", len(app.v), len(before_v))

print("\n== B4b 切回原聲時，模式鈕不可以還亮著（他 2026-09-25 指出）==")
app.apply_preset("發燒")
chk("按『發燒』→ 發燒鈕亮起", app.preset_btns["發燒"].cget("bg"), gp.ACCENT)
chk("  狀態列＝啟用中", "啟用中" in app.status.cget("text"), True)
app.toggle_ab()                          # 切回原聲
chk("切回原聲 → on=False", app.v["on"], False)
chk("  發燒鈕不再亮", app.preset_btns["發燒"].cget("bg"), gp.CARD2)
chk("  所有模式鈕都不亮", [b.cget("bg") for b in app.preset_btns.values()].count(gp.ACCENT), 0)
chk("  狀態列＝原聲", "原聲" in app.status.cget("text"), True)
chk("  旋鈕值沒被清掉（發燒那組還在）", app.v["side"], -6.0)
app.toggle_ab()                          # 再切回啟用
chk("再切回啟用 → 發燒鈕重新亮起（值還是那組）", app.preset_btns["發燒"].cget("bg"), gp.ACCENT)
app.on_slide("side", -4.0)               # 原聲狀態下手動拉 → 標記要清掉
app.toggle_ab()                          # 回原聲
chk("手動調過後切回原聲 → 沒有殘留亮燈", [b.cget("bg") for b in app.preset_btns.values()].count(gp.ACCENT), 0)
app.toggle_ab()
chk("  再啟用也不會亮起任何模式鈕", [b.cget("bg") for b in app.preset_btns.values()].count(gp.ACCENT), 0)
app.apply_preset("發燒")

print("\n== D 切回原聲時，數字與旋鈕都要歸零顯示（值保留）＝他 2026-09-25 的要求 ==")
app.apply_preset("發燒")
app.v["centerbass"] = True; app.v["tube"] = True; app.v["tube_drive"] = 6.0
app.band_cb.set(True); app.cb.set(True); app.tube_cb.set(True); app.tube_sc.set(6.0)
app.apply()
kept = dict(app.v)
app.toggle_ab()                                            # 切回原聲
chk("切回原聲 → on=False", app.v["on"], False)
chk("  值全部留著（除了 on 這個開關，逐鍵相同）",
    {k: val for k, val in app.v.items() if k != "on"}, {k: val for k, val in kept.items() if k != "on"})
chk("  滑桿數字全部歸零顯示", sorted({v.cget("text") for _, v in app.sliders.values()}), ["+0.0 dB"])
chk("  旋鈕位置全部歸零", [round(float(sc.get()), 3) for sc, _ in app.sliders.values()].count(0.0), len(app.sliders))
chk("  女聲控制歸零", round(float(app.pct_sc.get()), 3), 0.0)
chk("  女聲控制那行寫原聲", "原聲" in app.pct_val.cget("text"), True)
chk("  自動餘裕那行＝0.0 dB（原聲中）", ("0.0 dB" in app.preamp_lbl.cget("text") and "原聲" in app.preamp_lbl.cget("text")), True)
chk("  真空管那格寫關", app.tube_val.cget("text"), "關")
chk("  真空管說明寫原聲中", "原聲" in app.tube_info.cget("text"), True)
chk("  四個勾選項視覺上全空", [bool(w.get()) for w in (app.cb, app.band_cb, app.vst_cb, app.tube_cb)], [False] * 4)
chk("  （state 裡它們還是原本的值）", (app.v["centerbass"], app.v["tube"], app.v["side_band"]), (True, True, True))
chk("  模式燈全不亮", [b.cget("bg") for b in app.preset_btns.values()].count(gp.ACCENT), 0)
chk("  寫出去的檔案仍是原聲（不是他那條鏈）", "原聲" in open(os.path.join(PROBE_APO, "config.txt"), encoding="utf-8").read(), True)

print("\n== D2 按回『開啟女聲前移』→ 整組彈回來 ==")
app.toggle_ab()
chk("開啟後 on=True", app.v["on"], True)
chk("  值仍然是那組（除了 on）", {k: val for k, val in app.v.items() if k != "on"},
    {k: val for k, val in kept.items() if k != "on"})
chk("  滑桿位置＝他的值", round(float(app.sliders["side"][0].get()), 3), round(kept["side"], 3))
chk("  女聲控制＝他的百分比", round(float(app.pct_sc.get())), gp.side_db_to_pct(kept["side"]))
chk("  勾選項彈回來", [bool(w.get()) for w in (app.cb, app.band_cb, app.vst_cb, app.tube_cb)], [True, True, False, True])
chk("  滑桿數字回到真值（不再是 0）", app.sliders["sweet"][1].cget("text"), f"{kept['sweet']:+.1f} dB")

print("\n== D3 原聲狀態下他動手調 → 面板要恢復顯示真值（不然調了看不到數字）==")
app.toggle_ab()                                            # 回原聲
app.on_slide("sweet", 2.0)
chk("  調了之後數字顯示真值", app.sliders["sweet"][1].cget("text"), "+2.0 dB")
chk("  狀態列仍寫原聲（還沒啟用）", "原聲" in app.status.cget("text"), True)
chk("  已標記他在原聲中動過", app._touched_in_bypass, True)
app.toggle_ab(); app.toggle_ab()                           # 開→關：切換時重新判定
chk("  再切回原聲 → 又回到歸零顯示", app.sliders["sweet"][1].cget("text"), "+0.0 dB")
chk("  標記已重設", app._touched_in_bypass, False)
app.apply_preset("發燒")

print("\n== B5 版面自檢（150% 縮放）==")
W, H = root.winfo_width(), root.winfo_height()
print(f"  視窗 {W}x{H}，內容需要高度 {root.winfo_reqheight()}，DPI {root.winfo_fpixels('1i'):.0f}")
bad, tight = [], []
def walk(w):
    for c in w.winfo_children():
        y = c.winfo_rooty() - root.winfo_rooty(); x = c.winfo_rootx() - root.winfo_rootx()
        wd, h = c.winfo_width(), c.winfo_height()
        try:
            txt = str(c.cget("text"))[:26]
            rw, rh, aw, ah = c.winfo_reqwidth(), c.winfo_reqheight(), wd, h
        except Exception:
            txt, rw, rh, aw, ah = "", 0, 0, wd, h
        if (h > 1 and y + h > H + 1) or (wd > 1 and x + wd > W + 1) or y > H:
            bad.append((c.winfo_class(), txt, x, y, wd, h))
        if c.winfo_class() in ("Button", "Label", "Checkbutton") and aw > 1 and (aw + 2 < rw or ah + 2 < rh):
            tight.append((c.winfo_class(), txt, aw, rw, ah, rh))
        walk(c)
walk(root)
chk("沒有元件被視窗切掉", len(bad), 0)
for b in bad[:8]:
    print("   ", b)
chk("沒有文字被切（實寬/實高 < 需要）", len(tight), 0)
for t in tight[:8]:
    print("   ", t)

print("\n== B6 live 檔案完全沒被動到 ==")
chk("整場操作沒有被吞掉的例外（Tk 回呼）", swallowed, [])
for p, (h0, m0) in before.items():
    chk(f"{os.path.basename(p)} md5 不變", md5(p), h0)
    chk(f"{os.path.basename(p)} mtime 不變", round(os.path.getmtime(p), 3), round(m0, 3), 1e-6)
chk("他的 state.json md5 不變", md5(STATE), before_state)

root.destroy()
print("\n== 結果 ==")
print("全部通過 ✓" if not fails else f"失敗 {len(fails)} 項：{fails}")
raise SystemExit(0 if not fails else 1)
