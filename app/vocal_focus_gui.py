#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
甜嗓 SweetVox — 調整台（女聲前移／通透化）
• 最上面一顆「女聲控制」0～100%（0＝伴奏不退、100＝伴奏退到底）＝「伴奏退後量」的另一種刻度，兩顆同一參數、拉哪一顆都同步
• 拉滑桿即時改 Equalizer APO 設定（存檔後 APO 自動重載，播放中也能改）
• 「原聲 A/B」一鍵切換，馬上比對
• 「實測 5 秒」按下去會從 Audiolab M-DAC 側錄，直接給你看女聲/伴奏平衡差了幾 dB
需要管理員權限（要寫 C:\\Program Files\\EqualizerAPO\\config\\config.txt）→ 用 啟動調整台.cmd

2026-09-22 改版（依研究結果修方向）：
  * 10 kHz 以上改成「空氣感」滑桿。原本固定 -1.5 dB（砍掉），方向與「通透」相反。
  * 3 kHz 甜度預設 +2.5 → +1.2：靜態抬沒有動態搭配只會變刺，不會變甜。
"""
import json, os, math, struct, threading, time, datetime
import tkinter as tk
from tkinter import ttk, messagebox


def _dpi_setup():
    """宣告 DPI 感知。沒做這件事，系統縮放 150% 時 Windows 會把整個視窗放大後再畫一次 → 字全部糊掉。"""
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwarenessContext(-4)   # PER_MONITOR_AWARE_V2
        return "per-monitor-v2"
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "system"
    except Exception:
        return "無（系統會拉伸畫面）"


_DPI_MODE = _dpi_setup()
try:                      # 只在「實測 5 秒」時才需要；沒有也讓其他功能正常
    import pyaudiowpatch as pyaudio
except ImportError:       # pragma: no cover
    pyaudio = None

APO_DIR   = r"C:\Program Files\EqualizerAPO\config"
CUSTOM    = os.path.join(APO_DIR, "sweetvox_custom.txt")
CONFIG_TXT = os.path.join(APO_DIR, "config.txt")
HERE      = os.path.dirname(os.path.abspath(__file__))
STATE     = os.path.join(HERE, "state.json")
EXPORT    = r"E:\AI\workspace\vocal_focus"
LOOPBACK_KEY = "Audiolab"

# 免費 VST2（Airwindows：MIT 授權、可攜、不需安裝）
VST_AIR  = r"E:\AI\workspace\vocal_focus\vst\airwindows\WinVST64s\Air64.dll"
# 真空管暖度：實測 516 顆裡唯一「偶次諧波為主」的（Tube/Tube2/TubeDesk 都是奇次＝硬、刺）
VST_WARM = r"E:\AI\workspace\vocal_focus\vst\airwindows\WinVST64s\PurestWarm64.dll"

# ---------------- 女聲控制（最上面那一顆）----------------
# 「女聲控制」0～100% 就是「伴奏退後量」的另一種刻度，兩顆是同一個參數（拉哪一顆都同步）。
# 100% 對應伴奏退到最底＝跟下面那根滑桿同一個範圍。
PCT_MAX_DB = 15.0

def pct_to_side_db(pct):
    """0～100% → 伴奏退後量 dB（0→0.0、100→−15.0），對齊 0.5 dB"""
    pct = max(0.0, min(100.0, float(pct)))
    return -round(PCT_MAX_DB * pct / 100.0 / 0.5) * 0.5

def side_db_to_pct(db):
    """伴奏退後量 dB → 0～100%"""
    return int(max(0.0, min(100.0, round(-float(db) / PCT_MAX_DB * 100.0))))

# air = 10 kHz 以上高頻擷架（空氣感／通透），dB
DEFAULTS = dict(side=-7.0, sweet=1.2, mud=-3.0, sib=-1.0, warm=1.5, air=2.0,
                gain=0.0, vst_air=False, tube=True, tube_drive=6.0,
                centerbass=False, on=True, side_band=False, piano=False)

# 鋼琴模式的旋鈕標籤（同一顆旋鈕、換中心頻率）：只在 piano=True 時顯示
PIANO_LABELS = {"warm": "厚度 150 Hz", "mud": "低中頻 250", "sweet": "琴槌 3.5 kHz",
                "sib": "（停用）", "air": "泛音 10 kHz+"}

AIR_EXTRA_DB  = 3.2   # 勾「通透（Air 外掛）」時：峰值要多留的餘裕，也是可自動補回的音量上限
TUBE_AUTO_DB  = 3.0   # 勾「通透」時自動加的音量補償
GAIN_CEIL_DB  = 1.0   # 「整體音量補償」最多能往上推多少。滿刻度掃頻實測校準（tools/calibrate_gain_ceiling.py）：
                      # 乾淨鏈 +1.0 → 峰值 −0.80 dBFS（+1.5 就 −0.30＝削波）；這條鏈原本的 Air 上限 3.2 也保留
                      # ⚠ 只能定義這一份：前面給 PRESETS 用、下面給 build_config 用（曾在下面又多定義一次 → 預設與實際不一致）

PRESETS = {
    "淡": dict(side=-4.0, sweet=1.0, mud=-2.0, sib=-0.8, warm=1.0, air=1.0, centerbass=False, subcut=35.0),
    "中": dict(side=-7.0, sweet=1.2, mud=-3.0, sib=-1.0, warm=1.5, air=1.5, centerbass=False, subcut=35.0),
    "濃": dict(side=-11.0, sweet=2.0, mud=-3.5, sib=-1.2, warm=2.0, air=2.5, centerbass=True, subcut=35.0),
    # 深夜甜嗓：音響轉小聲、不想吵到家人。等響曲線告訴我們小聲時低音/高音都會變鈍
    # → 砍掉會穿牆的極低頻（85 Hz 以下）、抬清晰度（3 kHz）與空氣感、伴奏再退一點
    "深夜甜嗓": dict(side=-9.0, sweet=2.0, mud=-3.0, sib=0.0, warm=0.5, air=2.5,
                 centerbass=True, subcut=85.0, tube=True, tube_drive=6.0),
    # 發燒（乾淨）：實測 2026-09-25 — 原本那條鏈把音量壓掉 10.7 dB、立體相關拉到 +0.83（音場塌）、
    # 兩顆飽和外掛加了 0.73% THD。這一組＝不飽和、只在女聲頻段退兩側、不砍低頻的立體感，
    # 實測音量 −1.2 dB、立體相關 +0.28、THD 0.019%。
    # 鋼琴（發燒）：獨奏鋼琴用。中側矩陣預設完全不動（鋼琴的音場就是琴身寬度）、低頻不砍（A0 = 27.5 Hz）、
    # 不加飽和（THD 0.02% → 獨奏鋼琴聽得出來）、頻段換成鋼琴的（250 Hz 清濁／3.5 kHz 琴槌／10 kHz+ 泛音）。
    # 預設只衰減不加量 → 數學上不可能削波、音量差 ≈ 0（實測見 PLAN.md）。
    "鋼琴（發燒）": dict(piano=True, side=0.0, warm=0.0, mud=-1.5, sweet=0.0, sib=0.0, air=0.0,
                   subcut=0.0, centerbass=False, tube=False, tube_drive=0.0, vst_air=False,
                   gain=0.0, side_band=False),
    "發燒": dict(side=-6.0, sweet=1.5, mud=-2.0, sib=0.0, warm=1.0, air=1.0,
               centerbass=False, subcut=35.0, tube=False, tube_drive=0.0, vst_air=False,
               gain=GAIN_CEIL_DB, side_band=True),
}

# ---------------- 介面配色（深色底、女聲粉、真空管琥珀）----------------
BG      = "#15161a"
CARD    = "#1e2027"
CARD2   = "#272a33"
TXT     = "#e9eaee"
DIM     = "#98a0ad"
ACCENT  = "#ff8fb1"   # 甜嗓粉
ACCENT2 = "#ffc46b"   # 真空管琥珀
OK      = "#63d38f"
WARN    = "#ff6b6b"

# ---------------- 峰值安全計算（用 RBJ 公式精算，不憑感覺留餘裕）----------------
def _biquad(kind, f0, gain_db, q, fs=96000.0):
    A = 10 ** (gain_db / 40.0)
    w = 2 * math.pi * f0 / fs
    cw, sw = math.cos(w), math.sin(w)
    alpha = sw / (2 * q)
    if kind == "PK":
        b0, b1, b2 = 1 + alpha * A, -2 * cw, 1 - alpha * A
        a0, a1, a2 = 1 + alpha / A, -2 * cw, 1 - alpha / A
    elif kind == "LS":
        tsa = 2 * math.sqrt(A) * alpha
        b0 = A * ((A + 1) - (A - 1) * cw + tsa)
        b1 = 2 * A * ((A - 1) - (A + 1) * cw)
        b2 = A * ((A + 1) - (A - 1) * cw - tsa)
        a0 = (A + 1) + (A - 1) * cw + tsa
        a1 = -2 * ((A - 1) + (A + 1) * cw)
        a2 = (A + 1) + (A - 1) * cw - tsa
    else:  # HS
        tsa = 2 * math.sqrt(A) * alpha
        b0 = A * ((A + 1) + (A - 1) * cw + tsa)
        b1 = -2 * A * ((A - 1) + (A + 1) * cw)
        b2 = A * ((A + 1) + (A - 1) * cw - tsa)
        a0 = (A + 1) - (A - 1) * cw + tsa
        a1 = 2 * ((A - 1) - (A + 1) * cw)
        a2 = (A + 1) - (A - 1) * cw - tsa
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)

def _mag_db(c, f, fs=96000.0):
    b0, b1, b2, a1, a2 = c
    w = 2 * math.pi * f / fs
    cw1, sw1 = math.cos(w), math.sin(w)
    cw2, sw2 = math.cos(2 * w), math.sin(2 * w)
    nr = b0 + b1 * cw1 + b2 * cw2
    ni = -(b1 * sw1 + b2 * sw2)
    dr = 1 + a1 * cw1 + a2 * cw2
    di = -(a1 * sw1 + a2 * sw2)
    return 10 * math.log10((nr * nr + ni * ni) / (dr * dr + di * di))

def _chain_peak_db(cascades, fs=96000.0):
    best, f = -999.0, 20.0
    while f <= 20000:
        g = sum(_mag_db(c, f, fs) for c in cascades)
        if g > best: best = g
        f *= 1.02
    return best

SAFE_MARGIN_DB = 1.5   # 實測掃出：1.0 起全部不削波；取 1.5 多留 0.5 dB 餘裕（見 verify_safety_report.txt）

def _chains(v):
    """回傳 (mid 濾波器, mid 偏移 dB, side 濾波器, side 偏移 dB)。
    side 就是「正中比兩側高多少 dB」，差別只在用什麼方式做出來：
      full  ＝正中不動、兩側整條退 side dB（會一起把殘響、音場退掉）
      band  ＝兩側只在 2.5 kHz 附近退 side dB（低頻與極高頻的立體感留著）
      piano ＝鋼琴（發燒）：換成鋼琴的頻段（250 Hz / 3.5 kHz / 10 kHz+），不砍低頻、不寫兩側那條固定的 2 kHz
    註：「正中抬 side/2、兩側退 side/2」的對稱式實測是白工（前級會跟著峰值自動退，整體音量一模一樣），已移除。"""
    s = float(v["side"])
    band = bool(v.get("side_band"))
    if v.get("piano"):
        # 鋼琴：低頻不砍（A0 = 27.5 Hz）、側面鏈乾乾淨淨（只留 side 這個前級，預設 0＝完全不動音場）
        mid = [_biquad("LS", 150, v["warm"], 0.7), _biquad("PK", 250, v["mud"], 1.0),
               _biquad("PK", 3500, v["sweet"], 0.8), _biquad("HS", 10000, v["air"], 0.707)]
        return mid, 0.0, [], s
    mid = [_biquad("LS", 150, v["warm"], 0.7), _biquad("PK", 350, v["mud"], 1.4),
           _biquad("PK", 3000, v["sweet"], 0.9), _biquad("PK", 7500, v["sib"], 2.0),
           _biquad("HS", 10000, v["air"], 0.707)]
    side = [_biquad("PK", 2500, s, 0.7)] if band else []
    side.append(_biquad("PK", 2000, -1.5, 0.8))
    return mid, 0.0, side, s

def safe_preamp(v):
    """回傳「保證不削波」的全域 Preamp。公式：中/側兩條鏈峰值增益相加後除以 2（訊號在正中／兩側各佔一半），
    再加一層實測校準的安全邊界。"""
    mid, mid_off, side, side_off = _chains(v)
    gm = _chain_peak_db(mid) + mid_off
    gs = _chain_peak_db(side) + side_off
    # 最壞情況是「最大那條鏈的峰值增益」（訊號全在正中→走 mid；全在兩側→走 side）
    bound = max(10 ** (gm / 20.0), 10 ** (gs / 20.0))
    extra = AIR_EXTRA_DB if v.get("vst_air") else 0.0   # 實測：Air 外掛讓峰值多出約 2.8~3.2 dB
    if v.get("tube"):                                    # 真空管飽和：實測校準，推力越大峰值升越多
        extra += 0.5 + 0.11 * float(v.get("tube_drive", 0.0))
    if bound <= 1.0 + 1e-9 and extra == 0.0:
        # 整條鏈沒有任何正增益、也沒有飽和外掛 → 只會衰減，數學上不可能削波。
        # 這種情況不需要餘裕（鋼琴模式就是這條：預設只衰減 → 音量差 0.0 dB）。
        return 0.0
    return -(20 * math.log10(max(bound, 1e-6)) + 1.0) - extra - SAFE_MARGIN_DB

def applied_preamp(v):
    """真正會寫進設定檔的全域 Preamp（＝安全值 + 音量補償，夾在上限內）。"""
    base = safe_preamp(v)
    ceil = base + max(AIR_EXTRA_DB if v.get("vst_air") else 0.0, GAIN_CEIL_DB)
    return max(-24.0, min(base + float(v.get("gain", 0.0)), ceil))

# ---------------- 設定檔產生 ----------------
def build_config(v):
    preamp = applied_preamp(v)
    side_band = bool(v.get("side_band"))
    piano = bool(v.get("piano"))
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    L = []
    L.append(f"# 甜嗓 SweetVox ─ {'鋼琴（發燒）' if piano else '女聲前移／通透化'}（調整台寫入 {ts}）")
    L.append(f"# 自動餘裕 Preamp {preamp:.1f} dB：" + (
        "這條鏈只衰減、不加量 → 不可能削波；拉成正的時候才會自動讓位" if piano else
        "確保（甜度/溫暖/空氣感）推上去後不削波"))
    L.append(f"Preamp: {preamp:.1f} dB")
    L.append("")
    if v.get("vst_air"):
        L.append("# 通透：Airwindows Air（免費 VST2、MIT）。放在拆中側之前，兩邊一起延遲，")
        L.append("# 避免只延遲正中造成的梳狀濾波。注意它會讓整體音量掉約 4~5 dB，用『整體音量補償』補回。")
        L.append(f'VSTPlugin: Library "{VST_AIR}"')
        L.append("")
    L.append("# 拆成 MID（正中＝女聲）／SIDE（兩側＝伴奏）")
    L.append("Channel: all")
    L.append("Copy: R=0.5*L+-0.5*R")
    L.append("Copy: L=L+-1.0*R")
    L.append("")
    L.append("# MID：女聲" if not piano else "# 鋼琴：低頻不砍（A0 = 27.5 Hz）、中側矩陣預設不動")
    L.append("Channel: L")
    if piano:
        n = 1
        if float(v.get("subcut", 0.0)) > 0:     # 鋼琴模式預設 0＝完全不砍低頻
            L.append(f"Filter {n}: ON HPQ Fc {float(v['subcut']):.0f} Hz Q 0.7"); n += 1
        L.append(f"Filter {n}: ON LS Fc 150 Hz Gain {v['warm']:.1f} dB Q 0.7"); n += 1
        L.append(f"Filter {n}: ON PK Fc 250 Hz Gain {v['mud']:.1f} dB Q 1.0"); n += 1
        L.append(f"Filter {n}: ON PK Fc 3500 Hz Gain {v['sweet']:.1f} dB Q 0.8"); n += 1
        L.append(f"Filter {n}: ON HS Fc 10000 Hz Gain {v['air']:.1f} dB")
    else:
        if float(v.get("subcut", 0.0)) > 0:
            L.append(f"Filter 1: ON HPQ Fc {float(v['subcut']):.0f} Hz Q 0.7")
        L.append(f"Filter {'2' if float(v.get('subcut', 0.0)) > 0 else '1'}: ON LS Fc 150 Hz Gain {v['warm']:.1f} dB Q 0.7")
        base = 3 if float(v.get("subcut", 0.0)) > 0 else 2
        L.append(f"Filter {base}: ON PK Fc 350 Hz Gain {v['mud']:.1f} dB Q 1.4")
        L.append(f"Filter {base + 1}: ON PK Fc 3000 Hz Gain {v['sweet']:.1f} dB Q 0.9")
        L.append(f"Filter {base + 2}: ON PK Fc 7500 Hz Gain {v['sib']:.1f} dB Q 2.0")
        L.append(f"Filter {base + 3}: ON HS Fc 10000 Hz Gain {v['air']:.1f} dB")
    if v.get("tube"):
        L.append("")
        L.append("# 真空管暖度：Airwindows PurestWarm（MIT、VST2、零延遲）")
        L.append("# 只掛在正中（女聲）這條鏈；推力→飽和→等量衰減，音量不變")
        L.append(f"# 實測：推力 0 dB→THD 0.32%／推力 12 dB→THD 5.17%，兩者都是偶次諧波為主")
        L.append(f"Preamp: {float(v.get('tube_drive', 0.0)):+.1f} dB")
        L.append(f'VSTPlugin: Library "{VST_WARM}"')
        L.append(f"Preamp: {-float(v.get('tube_drive', 0.0)):+.1f} dB")
    L.append("")
    L.append("# SIDE：伴奏")
    L.append("Channel: R")
    if piano:
        L.append("# 鋼琴模式：只留這一顆前級（預設 0.0＝完全不動音場）；不寫流行樂用的 2 kHz 那條")
        L.append(f"Preamp: {float(v['side']):.1f} dB")
        if v["centerbass"]:
            L.append("Filter 1: ON HPQ Fc 100 Hz Q 0.7")
    elif side_band:
        L.append("# 只在女聲頻段（2.5 kHz 附近）退兩側：低頻與極高頻的立體感、殘響留下來")
        L.append(f"Filter 1: ON PK Fc 2500 Hz Gain {v['side']:.1f} dB Q 0.7")
        L.append("Filter 2: ON PK Fc 2000 Hz Gain -1.5 dB Q 0.8")
        if v["centerbass"]:
            L.append("Filter 3: ON HPQ Fc 100 Hz Q 0.7")
    else:
        L.append(f"Preamp: {float(v['side']):.1f} dB")
        L.append("Filter 1: ON PK Fc 2000 Hz Gain -1.5 dB Q 0.8")
        if v["centerbass"]:
            L.append("Filter 2: ON HPQ Fc 100 Hz Q 0.7")
    L.append("")
    L.append("# 還原回 L/R")
    L.append("Channel: all")
    L.append("Copy: L=L+R")
    L.append("Copy: R=L+-2.0*R")
    return "\n".join(L) + "\n"

def _write_retry(path, text, tries=8):
    """APO 讀設定檔的瞬間會短暫鎖住檔案 → 失敗就重試，不要一失敗就放棄"""
    last = None
    for _ in range(tries):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return
        except PermissionError as e:
            last = e
            time.sleep(0.15)
    raise last

def write_files(v):
    """寫入自訂設定 + config.txt（沒開＝原聲）。回傳 (ok, msg)"""
    try:
        if v["on"]:
            _write_retry(CUSTOM, build_config(v))
            head = ("# 女聲前移（調整台）。要 A/B：按介面上的【原聲 A/B】\n"
                    "Include: sweetvox_custom.txt\n")
        else:
            head = "# 女聲前移：目前關閉（原聲）\n# Include: sweetvox_custom.txt\n"
        _write_retry(CONFIG_TXT, head)
        got = open(CONFIG_TXT, encoding="utf-8").read()
        # 只看「沒有被 # 註解掉」的有效行
        active = [l.strip() for l in got.splitlines()
                  if l.strip() and not l.lstrip().startswith("#")]
        ok = ("Include: sweetvox_custom.txt" in active) == bool(v["on"])
        return (ok, "已寫入" if ok else "寫入後回讀不符")
    except PermissionError:
        return (False, "沒有寫入權限 → 請用『啟動甜嗓.cmd』（會跳管理員確認）")
    except Exception as e:
        return (False, f"寫入失敗：{e}")

# ---------------- 側錄量測 ----------------
def _find_loopback(pa):
    for i in range(pa.get_device_count()):
        d = pa.get_device_info_by_index(i)
        if LOOPBACK_KEY in d["name"] and "Loopback" in d["name"]:
            return i, d
    return None, None

def record(secs=3.5):
    pa = pyaudio.PyAudio()
    idx, d = _find_loopback(pa)
    if idx is None:
        pa.terminate(); raise RuntimeError("找不到 M-DAC 的 loopback 裝置（M-DAC 沒插好？）")
    rate = int(d["defaultSampleRate"])
    st = pa.open(format=pyaudio.paInt16, channels=2, rate=rate, input=True,
                 input_device_index=idx, frames_per_buffer=1024)
    fr = [st.read(1024, exception_on_overflow=False) for _ in range(int(rate / 1024 * secs))]
    st.stop_stream(); st.close(); pa.terminate()
    return rate, b"".join(fr)

def mid_side(raw):
    s = struct.unpack("<%dh" % (len(raw) // 2), raw)
    L, R = s[0::2], s[1::2]
    def db(x):
        if not x: return float("-inf")
        v = math.sqrt(sum(float(t) * t for t in x) / len(x)) / 32768.0
        return 20 * math.log10(v) if v > 0 else float("-inf")
    mid = [(a + b) / 2 for a, b in zip(L, R)]
    side = [(a - b) / 2 for a, b in zip(L, R)]
    return db(mid), db(side)

# ---------------- 介面 ----------------
class App:
    def __init__(self, root):
        self.root = root
        self.v = dict(DEFAULTS)
        try:
            with open(STATE, encoding="utf-8") as f:
                self.v.update(json.load(f))
        except Exception:
            pass
        for k, val in DEFAULTS.items():        # 舊 state.json 沒有 air 就補上
            self.v.setdefault(k, val)
        root.title("甜嗓 SweetVox — 調整台")
        # 依真實 DPI 放大（宣告 DPI 感知後，Tk 才知道要畫多大才不會被系統拉伸）
        self.dpi = root.winfo_fpixels("1i")
        self.s = max(1.0, self.dpi / 96.0)
        root.tk.call("tk", "scaling", self.dpi / 72.0)
        root.geometry(f"{int(700 * self.s)}x{int(680 * self.s)}")
        root.configure(bg=BG)
        try:
            root.option_add("*Font", ("Microsoft JhengHei UI", 10))
        except Exception:
            pass

        # ── 標題列 ──
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(head, text="甜嗓", bg=BG, fg=ACCENT,
                 font=("Microsoft JhengHei UI", 19, "bold")).pack(side="left")
        tk.Label(head, text=" SweetVox", bg=BG, fg=TXT,
                 font=("Microsoft JhengHei UI", 12)).pack(side="left", pady=(7, 0))
        tk.Label(head, text="女聲前移 · 通透 · 真空管暖度", bg=BG, fg=DIM,
                 font=("Microsoft JhengHei UI", 9)).pack(side="left", padx=(12, 0), pady=(9, 0))
        self.status = tk.Label(head, text="", bg=BG, fg=OK, justify="right",
                               font=("Microsoft JhengHei UI", 10, "bold"), wraplength=240)
        self.status.pack(side="right")

        # ── A/B 與模式 ──
        bar = tk.Frame(root, bg=CARD)
        bar.pack(fill="x", padx=16, pady=(0, 8))
        self.ab_btn = tk.Button(bar, text="", width=13, command=self.toggle_ab, bg=ACCENT, fg="#20131a",
                                activebackground="#ffa9c6", activeforeground="#20131a", relief="flat",
                                bd=0, pady=7, font=("Microsoft JhengHei UI", 10, "bold"))
        self.ab_btn.pack(side="left", padx=(8, 4), pady=8)
        self.preset_btns = {}
        for name in PRESETS:
            b = tk.Button(bar, text=name, width=10, command=lambda n=name: self.apply_preset(n),
                          bg=CARD2, fg=TXT, activebackground=ACCENT2, activeforeground="#201a10",
                          relief="flat", bd=0, pady=7)
            b.pack(side="left", padx=3, pady=8)
            self.preset_btns[name] = b
        tk.Button(bar, text="重設", width=5, command=self.reset, bg=CARD2, fg=DIM,
                  activebackground=CARD2, relief="flat", bd=0,
                  pady=7).pack(side="left", padx=(8, 6), pady=8)

        def section(title):
            f = tk.Frame(root, bg=CARD)
            f.pack(fill="x", padx=16, pady=5)
            tk.Label(f, text=title, bg=CARD, fg="#b9c0cc", anchor="w",
                     font=("Microsoft JhengHei UI", 9, "bold")).pack(fill="x", padx=12, pady=(8, 0))
            return f

        # ttk 主題：讓滑桿拉柄在深色底上看得見（clma/tk 預設拉柄是深色，會整根消失）
        sty = ttk.Style(root)
        try:
            sty.theme_use("clam")
        except Exception:
            pass
        sty.configure("Sweet.Horizontal.TScale", background=ACCENT, troughcolor="#0b0c10",
                      bordercolor=CARD, lightcolor=ACCENT, darkcolor=ACCENT, gripcount=0,
                      sliderlength=int(26 * self.s), sliderthickness=int(15 * self.s))
        sty.map("Sweet.Horizontal.TScale", background=[("active", "#ffc0d6")])
        sty.configure("SweetTube.Horizontal.TScale", background=ACCENT2, troughcolor="#0b0c10",
                      bordercolor=CARD, lightcolor=ACCENT2, darkcolor=ACCENT2, gripcount=0,
                      sliderlength=int(26 * self.s), sliderthickness=int(15 * self.s))
        sty.map("SweetTube.Horizontal.TScale", background=[("active", "#ffd79a")])

        # ── 女聲控制（最上面那一顆；跟下面的「伴奏退後量」是同一個參數）──
        sec0 = section("女聲控制")
        rowp = tk.Frame(sec0, bg=CARD)
        rowp.pack(fill="x", padx=12, pady=(4, 0))
        self.pct_val = tk.Label(rowp, text="", bg=CARD, fg=ACCENT, width=18, anchor="e",
                                font=("Consolas", 11))
        self.pct_val.pack(side="right")
        self.pct_sc = ttk.Scale(rowp, from_=0.0, to=100.0, orient="horizontal",
                                length=int(360 * self.s), style="Sweet.Horizontal.TScale",
                                command=self.on_pct)
        # 建構期間先塞值：這時 self.sliders／preamp_lbl 還沒建好，回呼跑下去會被 pythonw 吞掉例外
        self._pct_lock = True
        self.pct_sc.set(side_db_to_pct(self.v.get("side", 0.0)))
        self._pct_lock = False
        self.pct_sc.pack(side="left")
        tk.Label(sec0, text="0% ＝ 伴奏完全不退（原聲）　·　100% ＝ 伴奏退到最底（−15 dB）；跟下面「伴奏退後量」是同一顆",
                 bg=CARD, fg=DIM, anchor="w",
                 font=("Microsoft JhengHei UI", 8)).pack(fill="x", padx=12, pady=(0, 8))

        def slider(parent, key, label, lo, hi, res, length=None, style="Sweet.Horizontal.TScale"):
            length = int(320 * self.s) if length is None else length
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", padx=12)
            tk.Label(row, text=label, bg=CARD, fg=TXT, width=13, anchor="w").pack(side="left")
            self.slider_lbl[key] = (row.winfo_children()[-1], label)
            val = tk.Label(row, text="", bg=CARD, fg=ACCENT2, width=8, anchor="e",
                           font=("Consolas", 10))
            val.pack(side="right")
            sc = ttk.Scale(row, from_=lo, to=hi, orient="horizontal", length=length, style=style,
                           command=lambda x, k=key: self.on_slide(k, x))
            ox = getattr(self, "_init_lock", False)   # 建構期間塞初值→整段擋掉回呼（帳本 L49）
            self._init_lock = True
            sc.set(self.v[key])
            self._init_lock = ox
            sc.pack(side="left")
            self.sliders[key] = (sc, val)

        self.sliders = {}
        self.slider_lbl = {}
        sec1 = section("女聲（正中那條鏈）")
        slider(sec1, "sweet", "女聲甜度 3k", -2.0, 6.0, 0.5)
        slider(sec1, "mud", "去濁 350 Hz", -7.0, 0.0, 0.5)
        slider(sec1, "sib", "收齒音 7.5k", -5.0, 0.0, 0.5)
        slider(sec1, "air", "空氣感 10k+", -2.0, 4.0, 0.5)

        sec2 = section("伴奏（兩側）與音量")
        slider(sec2, "side", "伴奏退後量", 0.0, -PCT_MAX_DB, 0.5)
        self.cb = tk.BooleanVar(value=bool(self.v["centerbass"]))
        tk.Checkbutton(sec2, text="低頻置中（兩側 100 Hz 以下砍掉）", variable=self.cb,
                       command=self.on_cb, bg=CARD, fg=TXT, selectcolor=CARD2,
                       activebackground=CARD, activeforeground=TXT,
                       anchor="w").pack(fill="x", padx=12)
        self.band_cb = tk.BooleanVar(value=bool(self.v.get("side_band")))
        tk.Checkbutton(sec2, text="只退女聲頻段（2.5 kHz）：低頻與極高頻的立體感留著",
                       variable=self.band_cb, command=self.on_band, bg=CARD, fg=TXT,
                       selectcolor=CARD2, activebackground=CARD, activeforeground=TXT,
                       anchor="w").pack(fill="x", padx=12)
        slider(sec2, "gain", "整體音量補償", -6.0, 6.0, 0.5)

        sec3 = section("溫暖與通透（真空管）")
        slider(sec3, "warm", "溫暖 150 Hz", 0.0, 4.0, 0.5)
        self.tube_cb = tk.BooleanVar(value=bool(self.v.get("tube")))
        tk.Checkbutton(sec3, text="真空管暖度（PurestWarm：實測偶次諧波＝暖，不是刺）",
                       variable=self.tube_cb, command=self.on_tube, bg=CARD, fg=TXT,
                       selectcolor=CARD2, activebackground=CARD, activeforeground=TXT,
                       anchor="w").pack(fill="x", padx=12)
        rowt = tk.Frame(sec3, bg=CARD)
        rowt.pack(fill="x", padx=12)
        tk.Label(rowt, text="真空管推力", bg=CARD, fg=TXT, width=13, anchor="w").pack(side="left")
        self.tube_val = tk.Label(rowt, text="", bg=CARD, fg=ACCENT2, width=8, anchor="e",
                                 font=("Consolas", 10))
        self.tube_val.pack(side="right")
        self.tube_sc = ttk.Scale(rowt, from_=0.0, to=18.0, orient="horizontal",
                                 length=int(320 * self.s), style="SweetTube.Horizontal.TScale",
                                 command=self.on_tube_drive)
        self.tube_sc.set(float(self.v.get("tube_drive", 0.0)))
        self.tube_sc.pack(side="left")
        self.tube_info = tk.Label(sec3, text="", bg=CARD, fg=DIM, anchor="w",
                                  font=("Microsoft JhengHei UI", 8))
        self.tube_info.pack(fill="x", padx=12)
        self.vst_cb = tk.BooleanVar(value=bool(self.v.get("vst_air")))
        tk.Checkbutton(sec3, text="通透：加 Airwindows Air（勾了自動補 3 dB 音量）", variable=self.vst_cb,
                       command=self.on_vst, bg=CARD, fg=TXT, selectcolor=CARD2,
                       activebackground=CARD, activeforeground=TXT,
                       anchor="w").pack(fill="x", padx=12, pady=(0, 8))

        # ── 底部 ──
        foot = tk.Frame(root, bg=BG)
        foot.pack(fill="x", padx=16, pady=(8, 4))
        tk.Button(foot, text="實測 5 秒（看數字，不靠耳朵）", command=self.measure, bg=CARD2, fg=TXT,
                  activebackground=ACCENT, activeforeground="#20131a", relief="flat",
                  bd=0, pady=7).pack(side="left")
        tk.Button(foot, text="匯出這組設定", command=self.export, bg=CARD2, fg=TXT,
                  activebackground=ACCENT, activeforeground="#20131a", relief="flat", bd=0,
                  pady=7).pack(side="left", padx=6)
        self.preamp_lbl = tk.Label(foot, text="", bg=BG, fg=DIM, font=("Microsoft JhengHei UI", 9))
        self.preamp_lbl.pack(side="right")
        self.measure_lbl = tk.Label(root, text="", bg=BG, fg="#8fc7ff", justify="left",
                                    wraplength=660, font=("Microsoft JhengHei UI", 9))
        self.measure_lbl.pack(pady=(2, 10))

        self.refresh_labels()
        self._mark_preset(self._match_preset(self.v))   # 全部滑桿都建好之後才判定（建構期的初值回呼不算手動調）
        self.apply()
        # 版面依實際內容自動收邊（含 150% 縮放）；高度不夠會被切、太高會留一大片空白
        root.update_idletasks()
        w = int(700 * self.s)
        h = max(root.winfo_reqheight() + int(110 * self.s), int(520 * self.s))
        root.geometry(f"{w}x{h}")
        root.minsize(w, h)
        root.configure(bg=BG)

    # ---- 事件 ----
    def _sync_pct_from_state(self):
        """把「女聲控制」那顆拉到跟 side 一致（過程中不要讓它的回呼又回寫）"""
        sc = getattr(self, "pct_sc", None)
        if sc is None:
            return
        self._pct_lock = True
        try:
            sc.set(side_db_to_pct(self.v.get("side", 0.0)))
        finally:
            self._pct_lock = False

    def _note_manual_edit(self):
        """原聲狀態下他動了旋鈕＝在預調下一組：面板恢復顯示真值（狀態列仍寫原聲），不要調了看不到數字。"""
        if not self.v.get("on"):
            self._touched_in_bypass = True

    def on_pct(self, x):
        """女聲控制 0～100% → 伴奏退後量（跟下面那根滑桿同步）"""
        if getattr(self, "_paint_lock", False):    # 面板自己在重畫位置（原聲歸零／切回來），不算他調的
            return
        if getattr(self, "_pct_lock", False):
            return
        self._note_manual_edit()
        pct = int(round(float(x)))
        self.v["side"] = pct_to_side_db(pct)
        self._mark_preset(None)          # 手動調過就不再算哪個模式
        if "side" in getattr(self, "sliders", {}):
            self._side_lock = True
            try:
                self.sliders["side"][0].set(self.v["side"])
            finally:
                self._side_lock = False
        self.refresh_labels()
        self.schedule_apply()

    def on_slide(self, key, x):
        if getattr(self, "_paint_lock", False):    # 面板自己在重畫位置
            return
        if getattr(self, "_init_lock", False):    # 建構期間的初值回呼：不算「他手動調過」
            return
        if getattr(self, "_side_lock", False):      # 由「女聲控制」帶動，不要再繞回來
            return
        self._note_manual_edit()
        self.v[key] = round(float(x) / 0.5) * 0.5
        self._mark_preset(None)          # 手動調過就不再算哪個模式
        if key == "side":
            self._sync_pct_from_state()
        self.refresh_labels()
        self.schedule_apply()

    def on_cb(self):
        if getattr(self, "_paint_lock", False):
            return
        self._note_manual_edit()
        self.v["centerbass"] = bool(self.cb.get())
        self.schedule_apply()

    def on_band(self):
        if getattr(self, "_paint_lock", False):
            return
        self._note_manual_edit()
        self.v["side_band"] = bool(self.band_cb.get())
        self.refresh_labels()
        self.schedule_apply()

    def on_vst(self):
        """勾「通透」＝加 Airwindows Air（實測會吃掉約 4.6 dB 音量）→ 自動補 3 dB 回來；取消勾選也自動退回"""
        if getattr(self, "_paint_lock", False):
            return
        self._note_manual_edit()
        was = bool(self.v.get("vst_air"))
        now = bool(self.vst_cb.get())
        self.v["vst_air"] = now
        if now != was:
            g0 = float(self.v.get("gain", 0.0))
            g1 = g0 + (TUBE_AUTO_DB if now else -TUBE_AUTO_DB)
            self.v["gain"] = max(-6.0, min(6.0, round(g1 / 0.5) * 0.5))
            if "gain" in self.sliders:
                self.sliders["gain"][0].set(self.v["gain"])
        self.refresh_labels()
        self.schedule_apply()

    def on_tube(self):
        if getattr(self, "_paint_lock", False):
            return
        self._note_manual_edit()
        self.v["tube"] = bool(self.tube_cb.get())
        self.refresh_labels()
        self.schedule_apply()

    def on_tube_drive(self, x):
        if getattr(self, "_paint_lock", False):
            return
        self._note_manual_edit()
        self.v["tube_drive"] = round(float(x) / 3.0) * 3.0
        self.v["tube"] = bool(self.tube_cb.get()) or self.v["tube_drive"] > 0
        self.tube_cb.set(bool(self.v["tube"]))
        self.refresh_labels()
        self.schedule_apply()

    def schedule_apply(self):
        if getattr(self, "_job", None):
            self.root.after_cancel(self._job)
        self._job = self.root.after(250, self.apply)

    def apply(self):
        ok, msg = write_files(self.v)
        self._save_state()
        txt = "啟用中：甜嗓 SweetVox" if self.v["on"] else "目前：原聲（A/B 關閉）"
        self.status.config(text=f"{txt}　·　{msg}", fg=(OK if ok else WARN))
        self.ab_btn.config(text=("切回原聲" if self.v["on"] else "開啟女聲前移"),
                           bg=(ACCENT if self.v["on"] else CARD2),
                           fg=("#20131a" if self.v["on"] else TXT))
        self._paint_presets()               # 原聲時模式鈕不該還亮著（他 2026-09-25 指出）
        self.refresh_labels()               # 原聲時數字／旋鈕／勾選項全部歸零顯示（值保留）

    def _mark_preset(self, name):
        self._preset_name = name
        self._paint_presets()

    @staticmethod
    def _gain_room(v):
        """「整體音量補償」實際最多能再往上推幾 dB（超過會被夾住）。"""
        return max(AIR_EXTRA_DB if v.get("vst_air") else 0.0, GAIN_CEIL_DB)

    @staticmethod
    def _match_preset(v):
        """現在這組旋鈕值（夾住後＝真正生效的值）剛好等於哪一組模式？
        開起來時用來點亮那顆鈕；都比不到就都不亮。"""
        v = dict(v)
        v["gain"] = min(float(v.get("gain", 0.0)), App._gain_room(v))
        flags = [k for k, val in DEFAULTS.items() if isinstance(val, bool) and k != "on"]
        for name, p in PRESETS.items():
            ok = True
            for k in set(p.keys()) | set(flags):
                want = p.get(k, DEFAULTS.get(k))
                got = v.get(k)
                if isinstance(want, bool) or isinstance(got, bool):
                    ok = (bool(got) == bool(want))
                elif isinstance(want, (int, float)) and isinstance(got, (int, float)):
                    ok = abs(float(got) - float(want)) < 1e-9
                else:
                    ok = (got == want)
                if not ok:
                    break
            if ok:
                return name
        return None

    def _paint_presets(self):
        """模式鈕亮燈＝「這組值現在真的在跑」。切回原聲時全部不亮（旋鈕值沒變，只是沒啟用）；
        再切回來要把上一顆重新點亮。"""
        name = getattr(self, "_preset_name", None) if self.v.get("on") else None
        for n, b in getattr(self, "preset_btns", {}).items():
            hit = (n == name)
            b.config(bg=(ACCENT if hit else CARD2), fg=("#20131a" if hit else TXT))

    def _paint_controls(self):
        """控制項的位置＝「現在真的在跑什麼」：原聲時一律回到中性（值本身不動，切回來就彈回去）。
        位置一改就會觸發回呼 → 用 `_paint_lock` 擋（跟 `_init_lock` 同一招，見 lessons_ledger L49／L59）。"""
        editing = bool(self.v.get("on")) or getattr(self, "_touched_in_bypass", False)
        self._painted_editing = editing
        self._paint_lock = True
        try:
            for k, (sc, _) in getattr(self, "sliders", {}).items():
                sc.set(float(self.v.get(k, 0.0)) if editing else 0.0)
            if getattr(self, "pct_sc", None):
                self.pct_sc.set(side_db_to_pct(self.v.get("side", 0.0)) if editing else 0.0)
            for attr, key, default in (("cb", "centerbass", False), ("band_cb", "side_band", False),
                                       ("vst_cb", "vst_air", False), ("tube_cb", "tube", False)):
                w = getattr(self, attr, None)
                if w is not None:
                    w.set(bool(self.v.get(key, default)) and editing)
            if getattr(self, "tube_sc", None):
                self.tube_sc.set(float(self.v.get("tube_drive", 0.0)) if editing else 0.0)
        finally:
            self._paint_lock = False

    def refresh_labels(self):
        live = bool(self.v.get("on"))
        editing = live or getattr(self, "_touched_in_bypass", False)   # 原聲時他若正在調，就顯示真值（不然調了看不到數字）
        piano = bool(self.v.get("piano")) and editing
        for k, (sc, val) in getattr(self, "sliders", {}).items():
            real = float(self.v[k])
            txt = f"{(real if editing else 0.0):+.1f} dB"
            if editing and k == "gain":     # 顯示的值不可以比真正送進 APO 的值大（會被安全上限夾住）
                room = self._gain_room(self.v)
                if real > room + 1e-9:
                    txt = f"{room:+.1f} dB（上限；旋鈕值 {real:+.1f} 不生效）"
            val.config(text=txt)
        if getattr(self, "slider_lbl", None):      # 鋼琴模式換成鋼琴的頻段名稱（同一個旋鈕、不同中心頻率）
            for k, (lbl, base) in self.slider_lbl.items():
                lbl.config(text=(PIANO_LABELS.get(k, base) if piano else base))
        if getattr(self, "pct_val", None):
            if not editing:
                self.pct_val.config(text="原聲（面板歸零，值保留）")
            elif piano and abs(float(self.v.get("side", 0.0))) < 1e-9:
                self.pct_val.config(text="鋼琴模式：中側完全不動（0%）")
            else:
                pct = side_db_to_pct(self.v.get("side", 0.0))
                self.pct_val.config(text=f"{pct}%　→　伴奏 {self.v.get('side', 0.0):+.1f} dB")
        if editing != getattr(self, "_painted_editing", None):
            self._paint_controls()     # 只在「該顯示真值／該歸零」翻面時重畫位置，免得跟他手上的拖曳打架
        if not getattr(self, "preamp_lbl", None):     # 介面還在建的時候滑桿的 set() 就會回呼，先跳過
            return
        if editing:
            self.preamp_lbl.config(text=f"自動餘裕 Preamp：{applied_preamp(self.v):.1f} dB（精算過，峰值 ≤ -1 dBFS）")
        else:
            self.preamp_lbl.config(text="自動餘裕 Preamp：0.0 dB（原聲中，未套用）")
        d = float(self.v.get("tube_drive", 0.0)) if editing else 0.0
        # 實測表（1 kHz、-12 dBFS 入力、量到偶次比奇次高 +6.5 dB）
        tbl = [(0, 0.29), (3, 0.54), (6, 0.98), (9, 1.82), (12, 3.40), (15, 6.38), (18, 11.71)]
        if d <= tbl[0][0]:
            thd = tbl[0][1]
        elif d >= tbl[-1][0]:
            thd = tbl[-1][1]
        else:
            for (x0, y0), (x1, y1) in zip(tbl, tbl[1:]):
                if x0 <= d <= x1:
                    thd = y0 + (y1 - y0) * (d - x0) / (x1 - x0)
                    break
        state = "開" if (editing and self.v.get("tube")) else "關"
        self.tube_val.config(text=(f"{d:+.0f} dB" if state == "開" else "關"))
        if getattr(self, "tube_info", None):
            if state == "開":
                txt = f"偶次諧波為主（暖）；實測 THD {thd:.2f}%、零延遲、音量不變"
            else:
                txt = "未啟用（原聲中，值保留）" if not editing else "未啟用（推力拉到 >0 會自動開啟）"
            self.tube_info.config(text=txt)

    def toggle_ab(self):
        self.v["on"] = not self.v["on"]
        self._touched_in_bypass = False       # 每次切換都重新判定：原聲＝面板歸零顯示
        self.apply()

    def apply_preset(self, name):
        for k, val in DEFAULTS.items():        # 模式旗標先回預設，否則上一個模式的 piano/side_band 會殘留
            if isinstance(val, bool) and k != "on":
                self.v[k] = val
        self.v.update(PRESETS[name]); self.v["on"] = True
        self.cb.set(bool(self.v["centerbass"]))
        self.band_cb.set(bool(self.v.get("side_band")))
        self.vst_cb.set(bool(self.v.get("vst_air", False)))
        self.tube_cb.set(bool(self.v.get("tube", False)))
        self.tube_sc.set(float(self.v.get("tube_drive", 0.0)))
        for k, (sc, _) in self.sliders.items():
            sc.set(self.v[k])
        self._sync_pct_from_state()
        self._mark_preset(name)
        self.refresh_labels(); self.apply()

    def reset(self):
        self.v.update(DEFAULTS); self.cb.set(bool(self.v["centerbass"]))
        self.band_cb.set(bool(self.v.get("side_band")))
        self.vst_cb.set(bool(self.v.get("vst_air", False)))
        self.tube_cb.set(bool(self.v.get("tube", False)))
        self.tube_sc.set(float(self.v.get("tube_drive", 0.0)))
        for k, (sc, _) in self.sliders.items():
            sc.set(self.v[k])
        self._sync_pct_from_state()
        self._mark_preset(None)
        self.refresh_labels(); self.apply()

    def export(self):
        try:
            os.makedirs(EXPORT, exist_ok=True)
            p = os.path.join(EXPORT, "sweetvox_" + datetime.datetime.now().strftime("%m%d_%H%M") + ".txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write(build_config(self.v))
            self.measure_lbl.config(text=f"已匯出：{p}")
        except Exception as e:
            messagebox.showerror("匯出失敗", str(e))

    def _save_state(self):
        try:
            with open(STATE, "w", encoding="utf-8") as f:
                json.dump(self.v, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---- 實測 ----
    def measure(self):
        self.measure_lbl.config(text="量測中…（請讓音樂繼續播放，約 12 秒）")
        threading.Thread(target=self._measure_worker, daemon=True).start()

    def _measure_worker(self):
        try:
            cur_on = self.v["on"]
            # 1) 現在這組
            self.v["on"] = True
            write_files(self.v)
            time.sleep(0.6)
            raw = record(3.5)[1]
            m_now, s_now = mid_side(raw)
            # 2) 切成原聲
            tmp = dict(self.v); tmp["on"] = False
            write_files(tmp)
            time.sleep(0.6)
            raw2 = record(3.5)[1]
            m_off, s_off = mid_side(raw2)
            # 3) 還原
            self.v["on"] = cur_on
            write_files(self.v)
            if m_off < -70:
                msg = "M-DAC 上沒有聽到聲音（量到 -70 dB 以下）→ 請先播放音樂再按一次"
            else:
                d_now = m_now - s_now
                d_off = m_off - s_off
                lv_now = 20 * math.log10(math.sqrt(sum(float(t) * t for t in struct.unpack("<%dh" % (len(raw) // 2), raw)) / (len(raw) // 2)) + 1e-30)
                lv_off = 20 * math.log10(math.sqrt(sum(float(t) * t for t in struct.unpack("<%dh" % (len(raw2) // 2), raw2)) / (len(raw2) // 2)) + 1e-30)
                dl = lv_now - lv_off
                msg = ("原聲：女聲(中央) %.1f dB / 伴奏(兩側) %.1f dB → 差 %+.1f dB\n"
                       "現在：女聲(中央) %.1f dB / 伴奏(兩側) %.1f dB → 差 %+.1f dB\n"
                       "→ 女聲相對伴奏 %+.1f dB（正值＝女聲被往前推）\n"
                       "→ 整體音量 %+.1f dB（負值＝現在比較小聲；要比聽感請先把音量轉大 %.1f dB）"
                       % (m_off, s_off, d_off, m_now, s_now, d_now, d_now - d_off, dl, -dl))
        except Exception as e:
            msg = f"量測失敗：{e}"
        self.root.after(0, lambda: self.measure_lbl.config(text=msg))
        self.root.after(0, self.apply)

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
