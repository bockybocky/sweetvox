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
ROOT      = os.path.dirname(HERE)                      # 倉庫根目錄（app 的上一層）
EXPORT    = ROOT
LOOPBACK_KEY = "Audiolab"   # 優先找名稱含這個字的側錄裝置；找不到就用預設喇叭

# 免費 VST2（Airwindows：MIT 授權、可攜、不需安裝）
VST_AIR  = os.path.join(ROOT, "vst", "airwindows", "WinVST64s", "Air64.dll")
# 真空管暖度：實測 516 顆裡唯一「偶次諧波為主」的（Tube/Tube2/TubeDesk 都是奇次＝硬、刺）
VST_WARM = os.path.join(ROOT, "vst", "airwindows", "WinVST64s", "PurestWarm64.dll")

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
# 2026-10-08 房間量測的結論：63–200 Hz 隆起 +6~+14 dB，但**正確解法是窄陷波打峰**
# （room63 Q5.0 / room125 Q1.4），不是用 warm 寬削整段低頻。
#   曾經試過把所有模式的 warm 下移 6 dB（寬削）→ 量測顯示 80~160 Hz 被挖出一個洞，
#   最佳化（從實測反推房間曲線再解）給出 warm 回到 +2.0、靠兩顆窄濾波器處理峰，RMS 偏差 5.58→2.36 dB。
#   所以 warm 的預設值維持原樣，那個下移的改動已經撤回。
# room63 / room125 是量測得來的房間修正；**不放進任何模式**，按模式鈕時會保留
#   （房間修正是房間的屬性，不是聆聽模式的屬性）。預設 0＝行為與舊版完全一致。
# ── 方法論（介面上的另一頁）──
# 寫在程式裡而不是外部檔案：這樣不管把 vocal_focus_gui.py 複製到哪台機器，
# 「為什麼這樣調」都跟著走。內容與 docs/room-measurement.md 同源。
METHOD_TEXT = """【一】這個專案最大的一次改善：量房間

訊號鏈每一段都調過、EQ 參數在 ±2 dB 裡反覆微調了好幾天。
然後量了房間 —— 63～200 Hz 隆起 +6 ~ +14 dB。

    我們拿放大鏡在修一面有裂縫的牆。

修掉之後，實聽評語從「好聽」變成「超好聽」。
那是整個專案裡最大的一次改善，而它花的時間比之前任何一次微調都短。


【二】量房間的八個步驟

不需要校正過的量測麥克風。需要的是：一支任何麥克風、一個腳架
（腳架比麥克風重要），和一個「先證明尺是準的，再拿它量東西」的紀律。

第 0 步  任何麥克風都行，但一定要有腳架，而且要能用程式切 EQ 開關。

第 1 步  關掉麥克風所有「增強功能」。這步沒做，後面全部白費。
         怎麼確認：播大聲一點，錄到的也要變大。
         如果「播更大聲、錄到反而更小」，那是 AGC 還開著 ——
         實測 amp=0.12 錄到 −45.6 dBFS，amp=0.18 卻只有 −50.0 dBFS。
         有 AGC 不是「量得不準」，是完全沒有意義（量測鏈變成非線性）。

第 2 步  麥克風固定在你平常聽音樂的頭部位置，之後不要再碰它。
         這是整份方法論最重要的一句話。同一支麥克風、同一個房間，
         差別只在兩次量測之間它有沒有動：
             · 戴在頭上、人走過去按 EQ → 平均誤差 3.18 dB
             · 固定在腳架、切換由程式做 → 平均誤差 0.84 dB
         差 4 倍。因為 350 Hz 的波長約 1 公尺，移動 10 公分就改變駐波圖樣。

第 3 步  先校正尺，再量東西。不要先量房間。
         做法：EQ 開一次、關一次，兩次相減。
         差值應該精確等於你 EQ 的設計曲線（那條你算得出來）。
         麥克風的誤差、喇叭的響應、房間本身，在相減時全部抵消 ——
         這就是「不需要校正麥克風」的原因。
             · 通過：平均絕對誤差 0.84 dB（設計曲線總起伏 3.43 dB）
             · 失敗：平均絕對誤差 3.18 dB，連正負號都相反
         誤差跟訊號同量級 = 這把尺量不出你要量的東西，
         這時候得到的任何「房間曲線」都是假的。

第 4 步  量房間（EQ 關閉）：25 秒指數掃頻（ESS）＋ 反摺積。
         為什麼不用噪音：ESS 的反摺積會把非線性失真（諧波）推到脈衝響應
         的「負時間」去，跟線性部分分開 —— 喇叭有失真也不污染曲線。
         音量要高於環境噪音但不削波，目標峰值約 −20 dBFS。

第 5 步  分辨「這是房間」還是「這是麥克風」：把麥克風移開 50 公分再量一次。
             房間駐波跟位置強烈相關 → 會變
             麥克風自己的響應跟位置無關 → 不會變
         實測：低頻（≤315 Hz）移動後平均變 4.0 dB → 房間
               高頻（≥2.5 kHz）移動後平均變 1.2 dB → 麥克風
         所以曲線上 6.3 kHz 的 +7.9 dB 是麥克風的臨場感提升，不是房間，
         千萬不要去 EQ 它。沒做這步就照曲線修高頻，是最容易犯的錯。

第 6 步  決定修哪裡。
         能修的：峰。房間的隆起（駐波腹部）用 EQ 削很有效。
         不能修的：凹陷。實測 40 Hz −19 dB、50 Hz −11 dB 不要碰 ——
         那裡的聲波在你耳朵的位置互相抵消，推多少電力進去都抵消得掉，
         你只會讓喇叭在聽不到的頻率上做白工，甚至失真。
         凹陷要靠移動喇叭或座位解決，不是 EQ。

第 7 步  算出修正量，不要猜。既然第 3 步證明這把尺準，就可以反推：
             房間原始曲線 = 實測曲線 − 目前 EQ 的設計響應
             最佳參數     = 讓「原始曲線 + 新 EQ」最接近平坦的那組
         搜尋時一定要讓 Q 也進入搜尋。這是最大的教訓：
             · 寬的低頻架式濾波器削整段 → 50–250 Hz 偏差 5.09 dB
             · 窄濾波器但 Q 固定 1.0 → 偏差 3.81 dB
             · 讓 Q 自由（解出 Q=5.0）→ 偏差 2.36 dB　← 最好
         原因：+13 dB 的峰在 63 Hz，而旁邊 50 Hz 是凹陷。
         Q 太寬，削峰的同時會把凹陷挖更深。
         放開 Q 之後有個反直覺的結果：低頻架式濾波器反而可以回到 +2.0 dB ——
         用窄濾波器精準打掉峰之後，低頻的厚度回來了，但轟隆的峰被壓住。

第 8 步  套用、再量一次、最後用耳朵驗收。
             · 63 Hz：+9.0 → +0.1 dB
             · 80 Hz：+2.3 → +1.9 dB
             · 125 Hz：+6.3 → +1.3 dB
             · 200 Hz：+2.1 → +3.7 dB
         63–200 Hz 全部收在 ±4 dB 內。
         最後一關一定是耳朵。量測告訴你「哪裡錯了」和「改了多少」，
         但「這樣好不好聽」只有你能回答。平不一定等於好聽。


【三】實測否決掉的方法（留著當紀錄，不要重做）

真空管暖度（PurestWarm）
    加了 0.73% THD、立體相關拉到 +0.83（音場塌下來）。
    「發燒」模式就是為了關掉它而生的。控制項已從畫面撤掉。

通透：Airwindows Air
    需要外掛 DLL、吃掉 4.6 dB 音量再自動補回來。不划算，撤掉。

第 2 層：動態側鏈壓縮
    離線算出來的最佳曲線跟靜態的差不到 1 dB，聽不出來。不值得。

第 3 層：即時人聲分離（StemgenRT-5.8）
    技術上成功：延遲 29 ms、真峰 −1.00 dBFS、62 萬 hop 只 1 次 underrun、CPU 3.4%。
    但 M-DAC 會從 USB 掉下來造成爆音，所以不用這一層。
    另外一個重要的更正：criterion A 量的是「中央 vs 兩側」，
    不是「人聲 vs 伴奏」。用同一把尺重量之後，
    靜態 mid/side 的真實人聲／伴奏比是 +0.07 dB，兩者其實打平。


【四】常見錯誤一覽

  · 麥克風有 AGC
      症狀：曲線亂、兩次量測對不起來
      怎麼發現：播大聲一點，看錄到的有沒有也變大
  · 兩次量測之間麥克風動了
      症狀：校正測試的誤差跟訊號同量級
      怎麼發現：做第 3 步
  · 麥克風沒在聆聽位置
      症狀：數字漂亮但調完不好聽
      怎麼發現：想清楚你要量的是誰的耳朵
  · 把麥克風的響應當成房間
      症狀：照著修高頻，越修越怪
      怎麼發現：做第 5 步（移開 50 cm）
  · 去填補凹陷
      症狀：低頻失真、喇叭過載，聽感沒改善
      怎麼發現：凹陷不要碰就對了
  · Q 固定不搜尋
      症狀：削了峰，旁邊被挖洞
      怎麼發現：讓 Q 進入最佳化
  · 錄放用同一個全域串流
      症狀：永遠錄到靜音，誤判成線路不通
      怎麼發現：用兩個獨立的 stream

最後一條值得展開：在 Python 的 sounddevice 裡，
sd.play() / sd.rec() / sd.playrec() 共用模組層的同一個全域串流槽，
後呼叫的會把前一個停掉。要同時放與錄，必須自己開兩個獨立的
sd.InputStream 與 sd.OutputStream。


【五】寫入設定的鐵則

  1. 絕對不手改 Equalizer APO 的 live 設定檔。
     一律走 讀 state → apply_preset() → build_config() → write_files()。
  2. 寫完一定逐行比對實際生效的設定檔，差異必須是 0 行 ——
     確認「你以為在跑的」等於「真的在跑的」。
  3. 任何正增益都要用 Preamp 抵掉，再留 1 dB 餘裕。
  4. A/B 比較一定要等響度，不然你聽到的只是「比較大聲」。
  5. 只用官方 Equalizer APO，不用 VST3 分支。
  6. 不要用 ASIO／獨佔模式的播放器驗收（那條路繞過 APO）。

工具
  · tools/room_sweep.py → ESS 掃頻、反摺積、1/6 八度平滑、兩次相減
  · tools/set_bypass.py → 用程式切 EQ 開/關（人不要進房間）
  · tools/set_param.py → 改單一參數，走跟主程式相同的寫入與驗收路徑
"""

# V2.0：加入「用未校正麥克風量房間、相減校正、只削峰不填谷」那條鏈 ——
#       這是整個專案最大的一次改善（實聽從「好聽」變「超好聽」）。
VERSION = "V2.0"

DEFAULTS = dict(side=-7.0, sweet=1.2, mud=-3.0, sib=-1.0, warm=1.5, air=2.0,
                gain=0.0, vst_air=False, tube=True, tube_drive=6.0,
                centerbass=False, on=True, side_band=False, piano=False,
                room63=0.0, room125=0.0)

# 鋼琴模式的旋鈕標籤（同一顆旋鈕、換中心頻率）：只在 piano=True 時顯示
PIANO_LABELS = {"warm": "厚度 150 Hz", "mud": "低中頻 250", "sweet": "琴槌 3.5 kHz",
                "sib": "（停用）", "air": "泛音 10 kHz+"}

AIR_EXTRA_DB  = 3.2   # 勾「通透（Air 外掛）」時：峰值要多留的餘裕，也是可自動補回的音量上限
TUBE_AUTO_DB  = 3.0   # 勾「通透」時自動加的音量補償
GAIN_CEIL_DB  = 1.0   # 「整體音量補償」最多能往上推多少。滿刻度掃頻實測校準（tools/calibrate_gain_ceiling.py）：
                      # 乾淨鏈 +1.0 → 峰值 −0.80 dBFS（+1.5 就 −0.30＝削波）；這條鏈原本的 Air 上限 3.2 也保留
                      # ⚠ 只能定義這一份：前面給 PRESETS 用、下面給 build_config 用（曾在下面又多定義一次 → 預設與實際不一致）

# 介面上不顯示的模式：留在 PRESETS 裡（舊的 state.json 與開機模式判定都還能用），
# 只是主畫面不放按鈕 —— 淡/中/濃 彼此只差 side 與 sweet 的幾 dB，實際使用只在
# 「發燒」「深夜甜嗓」「鋼琴」之間切。
HIDDEN_PRESETS = ("淡", "中", "濃")

# 按鈕上的顯示文字（鍵名不能動：測試與既有 state.json 都靠它比對）
PRESET_LABELS = {"發燒": "發燒（人聲）"}

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
    # 2026-10-08：warm 1.0 → 2.0，對齊他實際在用、且實聽確認「超好聽」的那一組。
    # （低頻的峰交給 room63/room125 兩顆窄濾波器處理，所以 150 Hz 可以留著厚度）
    "發燒": dict(side=-6.0, sweet=1.5, mud=-2.0, sib=0.0, warm=2.0, air=1.0,
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
    # 房間修正（2026-10-08 加）：量測顯示 63–200 Hz 隆起 +6~+14 dB，
    # 移動麥克風 50 cm 再量一次確認是房間不是麥克風。
    # 放在**拆中側之前的 Channel: all**：房間的隆起左右都有，必須兩聲道等量削，
    # 不能只削 MID（那樣兩側的低頻會留著）。只能削不能加（滑桿上限 0），所以不影響削波餘裕。
    # 第二顆原本放 200 Hz，那是依「麥克風移開 50 cm」那次的數字選的——不是他聽歌的位置。
    # 聆聽位置實測：63 Hz +9.0、125 Hz +6.3、200 Hz 只有 +2.1 → 改成 125 Hz。
    # 63 Hz 用 Q5.0（窄）：那是個 +13 dB 的窄峰，旁邊 50 Hz 反而是凹陷 —— 用寬的會把凹陷挖更深。
    # 最佳化（從實測反推房間原始曲線再解）：Q 固定 1.0 時最好只能到 3.81 dB RMS 偏差，
    # 放開 Q 之後 Q5.0 可以到 2.36 dB，而且讓 warm 回到 +2.0（低頻厚度回來、峰仍被壓住）。
    room = [(63.0, float(v.get("room63", 0.0)), 5.0),
            (125.0, float(v.get("room125", 0.0)), 1.4)]
    room = [r for r in room if abs(r[1]) > 0.05]
    if room:
        L.append("# 房間修正：左右兩聲道等量（量測得來，不是憑耳朵）")
        L.append("Channel: all")
        for i, (f0, g, q) in enumerate(room, start=1):
            L.append(f"Filter {i}: ON PK Fc {f0:.0f} Hz Gain {g:.1f} dB Q {q}")
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
    try:                  # 沒有指定的音效卡 → 用 Windows 預設喇叭的側錄
        d = pa.get_default_wasapi_loopback()
        return d["index"], d
    except Exception:
        return None, None

def record(secs=3.5):
    pa = pyaudio.PyAudio()
    idx, d = _find_loopback(pa)
    if idx is None:
        pa.terminate(); raise RuntimeError("找不到可以側錄的輸出裝置（喇叭或音效卡沒插好？）")
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
        root.title(f"甜嗓 SweetVox {VERSION} — 調整台")
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
        tk.Label(head, text=VERSION, bg=BG, fg=ACCENT2,
                 font=("Microsoft JhengHei UI", 11, "bold")).pack(side="left", padx=(6, 0), pady=(7, 0))
        tk.Label(head, text="女聲前移 · 房間修正", bg=BG, fg=DIM,
                 font=("Microsoft JhengHei UI", 9)).pack(side="left", padx=(10, 0), pady=(9, 0))
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
        self._meth_win = None        # 方法論那一頁（同時只開一個）
        self.preset_btns = {}
        for name in PRESETS:
            b = tk.Button(bar, text=PRESET_LABELS.get(name, name), width=12,
                          command=lambda n=name: self.apply_preset(n),
                          bg=CARD2, fg=TXT, activebackground=ACCENT2, activeforeground="#201a10",
                          relief="flat", bd=0, pady=7)
            # 淡/中/濃：建立但不放上畫面。鍵名與按鈕物件都保留（模式判定、亮燈、測試都照常），
            # 只是主畫面不顯示 —— 它們彼此只差 side 與 sweet 幾 dB，實際只在發燒/深夜/鋼琴之間切。
            if name not in HIDDEN_PRESETS:
                b.pack(side="left", padx=3, pady=8)
            self.preset_btns[name] = b
        tk.Button(bar, text="重設旋鈕", width=8, command=self.reset, bg=CARD2, fg=DIM,
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
        # 退休的控制項放這裡：這個 Frame 永遠不 pack，所以畫面上看不到，
        # 但 self.sliders["side"]、self.tube_cb、self.tube_sc 等都照常建立 ——
        # apply_preset、_paint_controls、以及既有測試都不受影響。
        retired = tk.Frame(root, bg=CARD)

        sec1 = section("女聲（正中那條鏈）")
        slider(sec1, "sweet", "女聲甜度 3k", -2.0, 6.0, 0.5)
        slider(sec1, "mud", "去濁 350 Hz", -7.0, 0.0, 0.5)
        slider(sec1, "sib", "收齒音 7.5k", -5.0, 0.0, 0.5)
        slider(sec1, "air", "空氣感 10k+", -2.0, 4.0, 0.5)

        sec2 = section("伴奏（兩側）與音量")
        # 「伴奏退後量」退休：它跟最上面那顆「女聲控制」是同一個參數的兩種刻度，
        # 同一件事放兩個控制項只會讓人困惑。女聲控制那顆仍然完整可用。
        slider(retired, "side", "伴奏退後量", 0.0, -PCT_MAX_DB, 0.5)
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

        sec3 = section("低頻厚度")
        # 2026-10-08：下限從 0.0 放到 -6.0。房間量測顯示 63–200 Hz 隆起 +6~+14 dB
        # （移動麥克風 50 cm 再量一次，確認是房間不是麥克風），所以這顆需要能「削」不只是「加」。
        # 實測 warm=-5 把 63–200 Hz 的平均從 +10.3 dB 壓到 +4.5 dB，他聽過說好聽。
        slider(sec3, "warm", "溫暖 150 Hz", -6.0, 4.0, 0.5)

        # 房間修正（2026-10-08 加）：150 Hz 那顆架式壓不到 63 Hz 與 200 Hz 的兩個殘留峰。
        # 只能削不能加（上限 0）→ 不影響既有的削波餘裕計算。作用在左右兩聲道。
        sec_room = section("房間修正（量測得來，不是憑耳朵）")
        rowr = tk.Frame(sec_room, bg=CARD2)      # 底色加深一階，讓這盞燈從卡片上跳出來
        rowr.pack(fill="x", padx=12, pady=(2, 6))
        self.room_lamp = tk.Label(rowr, text="●", bg=CARD2, fg=DIM,
                                  font=("Microsoft JhengHei UI", 22))
        self.room_lamp.pack(side="left", padx=(10, 0), pady=6)
        self.room_lamp_txt = tk.Label(rowr, text="", bg=CARD2, fg=DIM, anchor="w",
                                      justify="left",
                                      font=("Microsoft JhengHei UI", 11, "bold"))
        self.room_lamp_txt.pack(side="left", padx=(8, 0), pady=6)
        slider(sec_room, "room63", "房間 63 Hz", -16.0, 0.0, 0.5)
        slider(sec_room, "room125", "房間 125 Hz", -16.0, 0.0, 0.5)
        self.tube_cb = tk.BooleanVar(value=bool(self.v.get("tube")))
        # 真空管退休：2026-09-25 的實測 —— 加了 0.73% THD、立體相關拉到 +0.83（音場塌），
        # 「發燒」模式就是為了關掉它而生的。參數保留，畫面不放。
        tk.Checkbutton(retired, text="真空管暖度（PurestWarm：實測偶次諧波＝暖，不是刺）",
                       variable=self.tube_cb, command=self.on_tube, bg=CARD, fg=TXT,
                       selectcolor=CARD2, activebackground=CARD, activeforeground=TXT,
                       anchor="w").pack(fill="x", padx=12)
        rowt = tk.Frame(retired, bg=CARD)
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
        self.tube_info = tk.Label(retired, text="", bg=CARD, fg=DIM, anchor="w",
                                  font=("Microsoft JhengHei UI", 8))
        self.tube_info.pack(fill="x", padx=12)
        self.vst_cb = tk.BooleanVar(value=bool(self.v.get("vst_air")))
        # Air 外掛退休：需要外掛 DLL、吃掉 4.6 dB 音量再自動補回來。參數保留，畫面不放。
        tk.Checkbutton(retired, text="通透：加 Airwindows Air（勾了自動補 3 dB 音量）", variable=self.vst_cb,
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
        tk.Button(foot, text="方法論（為什麼這樣調）", command=self.show_method, bg=CARD2, fg=TXT,
                  activebackground=ACCENT, activeforeground="#20131a", relief="flat", bd=0,
                  pady=7).pack(side="left")
        # Preamp 這行自己佔一列。跟三顆鈕擠同一列時右半句（「峰值 ≤ -1 dBFS」）會被切掉，
        # 而那正是這行要講的重點。
        self.preamp_lbl = tk.Label(root, text="", bg=BG, fg=DIM, anchor="w",
                                   font=("Microsoft JhengHei UI", 9))
        self.preamp_lbl.pack(fill="x", padx=16, pady=(6, 0))
        self.measure_lbl = tk.Label(root, text="", bg=BG, fg="#8fc7ff", justify="left",
                                    wraplength=660, font=("Microsoft JhengHei UI", 9))
        self.measure_lbl.pack(pady=(2, 10))

        self.refresh_labels()
        self._mark_preset(self._match_preset(self.v))   # 全部滑桿都建好之後才判定（建構期的初值回呼不算手動調）
        self.apply()
        # 版面依實際內容自動收邊（含 150% 縮放）；高度不夠會被切、太高會留一大片空白
        root.update_idletasks()
        w = int(700 * self.s)
        self._win_w = w
        self._fit_window()
        root.configure(bg=BG)

    # ---- 事件 ----
    def _fit_window(self):
        """依實際內容收邊。量測訊息欄平常是空的，先留 110 px 只會在底下空一大片；
        等真的有訊息（可能好幾行）再長高，所以每次改訊息都要再呼叫一次。"""
        self.root.update_idletasks()
        w = getattr(self, "_win_w", int(700 * self.s))
        h = max(self.root.winfo_reqheight() + int(16 * self.s), int(520 * self.s))
        self.root.minsize(w, int(520 * self.s))      # 先放寬，否則縮不回去
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(w, h)

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
        self._paint_room()
        self.refresh_labels()               # 原聲時數字／旋鈕／勾選項全部歸零顯示（值保留）

    def _mark_preset(self, name):
        self._preset_name = name
        self._paint_presets()
        self._paint_room()

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

    def _paint_room(self):
        """房間修正燈。語意跟模式鈕一致：亮＝這組值現在真的在跑。
        切回原聲時整條鏈沒作用 → 燈熄（值保留）。兩顆都 0 → 視為沒設定。"""
        if not hasattr(self, "room_lamp"):
            return
        r63 = float(self.v.get("room63", 0.0))
        r125 = float(self.v.get("room125", 0.0))
        has = abs(r63) > 0.05 or abs(r125) > 0.05
        running = bool(self.v.get("on")) and has
        if running:
            self.room_lamp.config(fg=OK)
            self.room_lamp_txt.config(
                text=f"房間修正作用中\n63 Hz {r63:+.1f} dB　125 Hz {r125:+.1f} dB（左右兩聲道）", fg=OK)
        elif has:
            self.room_lamp.config(fg=DIM)
            self.room_lamp_txt.config(text="房間修正已設定\n但目前是原聲，整條鏈沒作用", fg=DIM)
        else:
            self.room_lamp.config(fg=DIM)
            self.room_lamp_txt.config(text="房間修正未設定\n先量過房間再調，不要憑耳朵猜", fg=DIM)

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
        # 房間修正是**房間**的屬性，不是聆聽模式的屬性（跟模式鈕同一條規則）。
        # 它是量出來的，重設旋鈕不該把量測結果一起丟掉 —— 要改請用房間修正那一區。
        keep = {k: self.v[k] for k in ("room63", "room125") if k in self.v}
        self.v.update(DEFAULTS); self.v.update(keep)
        self.cb.set(bool(self.v["centerbass"]))
        self.band_cb.set(bool(self.v.get("side_band")))
        self.vst_cb.set(bool(self.v.get("vst_air", False)))
        self.tube_cb.set(bool(self.v.get("tube", False)))
        self.tube_sc.set(float(self.v.get("tube_drive", 0.0)))
        for k, (sc, _) in self.sliders.items():
            sc.set(self.v[k])
        self._sync_pct_from_state()
        self._mark_preset(None)
        self.refresh_labels(); self.apply()

    def show_method(self):
        """另開一頁放方法論。用 Toplevel 而不是分頁：主畫面的版面是量過高度自動收邊的，
        塞進 Notebook 會把那套邏輯連帶改掉；而且方法論是「偶爾查」，不是「隨時看」。"""
        if getattr(self, "_meth_win", None) is not None and self._meth_win.winfo_exists():
            self._meth_win.lift()                 # 已經開著就拉到前面，不要開第二個
            return
        w = tk.Toplevel(self.root)
        self._meth_win = w
        w.title(f"甜嗓 SweetVox {VERSION} — 方法論")
        w.configure(bg=BG)
        w.geometry(f"{int(760 * self.s)}x{int(700 * self.s)}")

        head = tk.Frame(w, bg=BG)
        head.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(head, text="方法論", bg=BG, fg=ACCENT,
                 font=("Microsoft JhengHei UI", 17, "bold")).pack(side="left")
        tk.Label(head, text="先證明尺是準的，再拿它量東西", bg=BG, fg=DIM,
                 font=("Microsoft JhengHei UI", 9)).pack(side="left", padx=(12, 0), pady=(8, 0))
        tk.Button(head, text="關閉", command=w.destroy, bg=CARD2, fg=TXT,
                  activebackground=ACCENT, activeforeground="#20131a",
                  relief="flat", bd=0, padx=14, pady=5).pack(side="right")

        box = tk.Frame(w, bg=CARD)
        box.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        sb = tk.Scrollbar(box, orient="vertical")
        sb.pack(side="right", fill="y")
        txt = tk.Text(box, bg=CARD, fg=TXT, bd=0, relief="flat", wrap="word",
                      padx=16, pady=14, spacing1=1, spacing3=3,
                      yscrollcommand=sb.set, insertwidth=0,
                      font=("Microsoft JhengHei UI", 10))
        txt.pack(side="left", fill="both", expand=True)
        sb.config(command=txt.yview)

        # 大標（【一】…）上色，其餘照原樣 —— 掃一遍比寫 regex 好讀
        txt.tag_configure("h", foreground=ACCENT,
                          font=("Microsoft JhengHei UI", 12, "bold"), spacing1=14, spacing3=6)
        txt.tag_configure("step", foreground=ACCENT2,
                          font=("Microsoft JhengHei UI", 10, "bold"), spacing1=8)
        txt.insert("1.0", METHOD_TEXT)
        for i, line in enumerate(METHOD_TEXT.splitlines(), start=1):
            if line.startswith("【"):
                txt.tag_add("h", f"{i}.0", f"{i}.end")
            elif line.startswith("第 ") and " 步" in line[:6]:
                txt.tag_add("step", f"{i}.0", f"{i}.end")
        txt.config(state="disabled")              # 只給看，不給改
        txt.bind("<MouseWheel>", lambda e: (txt.yview_scroll(-e.delta // 120, "units"), "break")[1])

    def export(self):
        try:
            os.makedirs(EXPORT, exist_ok=True)
            p = os.path.join(EXPORT, "sweetvox_" + datetime.datetime.now().strftime("%m%d_%H%M") + ".txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write(build_config(self.v))
            self.measure_lbl.config(text=f"已匯出：{p}")
            self._fit_window()
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
        self._fit_window()
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
        self.root.after(0, lambda: (self.measure_lbl.config(text=msg), self._fit_window()))
        self.root.after(0, self.apply)

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
