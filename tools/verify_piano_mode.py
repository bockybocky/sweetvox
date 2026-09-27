#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""鋼琴（發燒）模式驗收 C：設定檔內容 ＋ 真的把介面建起來按那顆鈕。

驗的是「鋼琴模式到底改了什麼、有沒有偷偷變成另一條鏈」：
  低頻完全不砍、側面鏈不寫流行樂那條 2 kHz、頻段換成 250 Hz / 3.5 kHz / 10 kHz+、
  不加飽和、全域 Preamp = 0.0（音量不變）、整條鏈沒有任何正增益（數學上不可能削波）。
全程寫暫存路徑，不碰 live 設定檔（跑完比對 md5/mtime）。

用法:
  C:\\Users\\Administrator\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe tools\\verify_piano_mode.py
"""
import os as _os; _ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 倉庫根目錄
import hashlib, importlib.util, json, os, re, shutil, tkinter as tk

SRC      = _os.path.join(_ROOT, r"app\vocal_focus_gui.py")
STATE    = _os.path.join(_ROOT, r"app\state.json")
LIVE_APO = r"C:\Program Files\EqualizerAPO\config\sweetvox_custom.txt"
LIVE_CFG = r"C:\Program Files\EqualizerAPO\config\config.txt"
TMP      = r"C:\Users\Administrator\AppData\Local\Temp\svx_probe"
PROBE    = os.path.join(TMP, "vocal_focus_gui_probe_piano.py")
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

os.makedirs(PROBE_APO, exist_ok=True)
shutil.copy2(STATE, PROBE_STATE)
src = open(SRC, encoding="utf-8").read()
reps = [
    ('APO_DIR   = r"C:\\Program Files\\EqualizerAPO\\config"', f'APO_DIR   = r"{PROBE_APO}"'),
    ('STATE     = os.path.join(HERE, "state.json")',          f'STATE     = r"{PROBE_STATE}"'),
    ('EXPORT    = ROOT',          f'EXPORT    = r"{TMP}"'),
]
probe = src
for a, b in reps:
    assert probe.count(a) == 1, f"替身替換失敗：{a}"
    probe = probe.replace(a, b)
chk("替身裡已經沒有 live APO 路徑", "C:\\Program Files\\EqualizerAPO" in probe, False)
open(PROBE, "w", encoding="utf-8").write(probe)
before = {p: (md5(p), os.path.getmtime(p)) for p in (LIVE_APO, LIVE_CFG)}
before_state = md5(STATE)

spec = importlib.util.spec_from_file_location("gp", PROBE)
gp = importlib.util.module_from_spec(spec); spec.loader.exec_module(gp)
gp.STATE = PROBE_STATE

print("\n== C1 鋼琴模式的設定檔內容 ==")
st = dict(gp.DEFAULTS); st.update(gp.PRESETS["鋼琴（發燒）"]); st["on"] = True
cfg = gp.build_config(st)
chk("標題＝鋼琴（發燒）", "鋼琴（發燒）" in cfg.splitlines()[0], True)
chk("低頻完全不砍（沒有 HPQ 這行）", "HPQ" in cfg, False)
chk("  低中頻＝250 Hz Q1.0（−1.5 dB）", "PK Fc 250 Hz Gain -1.5 dB Q 1.0" in cfg, True)
chk("  琴槌＝3.5 kHz Q0.8", "PK Fc 3500 Hz Gain 0.0 dB Q 0.8" in cfg, True)
chk("  泛音＝10 kHz+ shelf", "HS Fc 10000 Hz Gain 0.0 dB" in cfg, True)
chk("  沒有流行樂的 350 Hz／3 kHz／7.5 kHz 頻段", any(x in cfg for x in ("Fc 350 Hz", "Fc 3000 Hz", "Fc 7500 Hz")), False)
chk("側面鏈不寫流行樂那條 2 kHz 固定衰減", "Fc 2000 Hz" in cfg, False)
chk("側面鏈只留前級（Preamp: 0.0 dB）＝完全不動音場", "Preamp: 0.0 dB" in cfg, True)
chk("不加飽和（沒有 VSTPlugin）", "VSTPlugin" in cfg, False)
chk("中側矩陣還在（4 行 Copy，實測逐位元透明）", cfg.count("Copy:"), 4)
chk("全域 Preamp ＝ 0.0 dB（音量不變）", re.findall(r"^Preamp: ([-\d.]+) dB", cfg, re.M)[0], "0.0")
gains = [float(m) for m in re.findall(r"Gain ([-\d.]+) dB", cfg)]
chk("整條鏈沒有任何正增益（數學上不可能削波）", max(gains) <= 0.0, True)
chk("safe_preamp 對這組回 0.0（只衰減就不留餘裕）", gp.safe_preamp(st), 0.0)
chk("applied_preamp ＝ 0.0", gp.applied_preamp(st), 0.0)
loud = dict(st); loud["air"] = 2.0                      # 他若把泛音拉上去 → 安全機制要接手
chk("泛音拉 +2 dB 後仍會自動讓位（Preamp < 0）", gp.applied_preamp(loud) < -1.0, True)
chk("  那組的峰值仍然不會超過 −0.5 dBFS（餘裕 ≥ 2.5 dB）", round(gp.applied_preamp(loud), 2) <= -2.5, True)

print("\n== C2 模式旗標不會殘留 ==")
mixed = dict(gp.DEFAULTS); mixed.update(gp.PRESETS["鋼琴（發燒）"])
mixed.update(gp.PRESETS["發燒"])
chk("（純檢查）發燒那組本身沒有 piano 鍵", "piano" in gp.PRESETS["發燒"], False)
chk("DEFAULTS 有 piano=False（切模式時才會清掉）", gp.DEFAULTS["piano"], False)

print("\n== C3 真的把介面建起來按「鋼琴（發燒）」==")
root = tk.Tk(); root.withdraw()
swallowed = []
root.report_callback_exception = lambda *a: swallowed.append(repr(a[1]))
app = gp.App(root)
root.update_idletasks(); root.update()
app.v["on"] = True
app.apply_preset("鋼琴（發燒）")
chk("按下後 piano 旗標＝True", app.v["piano"], True)
chk("  女聲控制回到 0%（中側不動）", app.v["side"], 0.0)
chk("  模式鈕亮起", app.preset_btns["鋼琴（發燒）"].cget("bg"), gp.ACCENT)
chk("  女聲控制那張卡的文字說明", "鋼琴模式" in app.pct_val.cget("text"), True)
lbls = {k: v[0].cget("text") for k, v in app.slider_lbl.items()}
chk("  旋鈕標籤換成鋼琴頻段（低中頻 250）", lbls["mud"], "低中頻 250")
chk("  琴槌 3.5 kHz", lbls["sweet"], "琴槌 3.5 kHz")
chk("  泛音 10 kHz+", lbls["air"], "泛音 10 kHz+")
chk("  齒音標成停用", lbls["sib"], "（停用）")
chk("  伴奏退後量那顆標籤不變（它是同一顆旋鈕）", lbls["side"], "伴奏退後量")
app.apply()
body = open(os.path.join(PROBE_APO, "sweetvox_custom.txt"), encoding="utf-8").read()
chk("  寫出的檔案真的是鋼琴那條", "PK Fc 250 Hz Gain -1.5 dB Q 1.0" in body, True)
app.apply_preset("發燒")
chk("按回『發燒』→ piano 旗標清掉", app.v["piano"], False)
chk("  標籤換回女聲的（女聲甜度 3k）", app.slider_lbl["sweet"][0].cget("text"), "女聲甜度 3k")
chk("  齒音標籤換回來", app.slider_lbl["sib"][0].cget("text"), "收齒音 7.5k")
chk("整場沒有被 Tk 吞掉的例外", swallowed, [])

print("\n== C4 live 檔案完全沒被動到 ==")
for p, (h0, m0) in before.items():
    chk(f"{os.path.basename(p)} md5 不變", md5(p), h0)
    chk(f"{os.path.basename(p)} mtime 不變", round(os.path.getmtime(p), 3), round(m0, 3), 1e-6)
chk("他的 state.json md5 不變", md5(STATE), before_state)

print(f"\n== 結果 ==\n{'全部通過 ✓' if not fails else '失敗 %d 項：%s' % (len(fails), fails)}")
raise SystemExit(1 if fails else 0)
