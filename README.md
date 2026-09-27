# 甜嗓 SweetVox

<p align="center"><img src="docs/screenshot.png" alt="甜嗓調整台介面" width="640"></p>

聽音樂時把**女聲往前推、伴奏往後退**的 Windows 桌面調音台。
底層用 [Equalizer APO](https://sourceforge.net/projects/equalizerapo/)（系統層等化器）把左右聲道拆成
「正中（通常是人聲）」和「兩側（通常是伴奏）」，各自調整後再無損還原。


## 版本

2026-09-27 快照。內容：
- 女聲控制單旋鈕（0～100%，對應兩側退 0～−15 dB）
- 「發燒」模式：只在女聲頻段（2.5 kHz）退兩側，音場保留，THD 0.011%
- 鋼琴（發燒）模式：不動音場、不砍低頻、不加飽和、只衰減，逐位元透明
- 網頁版（`web/sweetvox.js`，Web Audio 同一條鏈）與手機等化曲線產生器（`phone/`）

量測數字與設計取捨寫在 `PLAN.md`，原始量測在 `MEASURE_*.json`。

## 怎麼用

1. 安裝 Equalizer APO 1.4.2 官方版，裝置選你的輸出音效卡。
2. 用 Python 3.11 跑 `app/vocal_focus_gui.py`（`app/啟動甜嗓.cmd` 裡的 Python 路徑請改成你自己的）。
3. 介面會把設定寫到 `C:\Program Files\EqualizerAPO\config\sweetvox_custom.txt`，
   並在 `config.txt` 加一行 `Include: sweetvox_custom.txt`，即時生效。
4. 關掉效果：介面按「原聲」，或在 `config.txt` 那行前面加 `#`。

`sweetvox_custom.txt` 是目前使用中的一份設定範例。

### 要改的地方

程式預設找名稱含 `Audiolab` / `M-DAC` 的裝置（作者的音效卡）做側錄量測。
換成你的裝置：改 `app/vocal_focus_gui.py` 的 `LOOPBACK_KEY`，以及 `tools/lb_*.py` 裡的裝置名稱。

真空管／Air 兩個飽和效果用 Airwindows 的 VST2 外掛（MIT），本倉庫不附，要自己下載並改設定裡的路徑。預設是關的。

## 已知限制

- 「正中＝女聲」是假設。正中央的大鼓、貝斯也會一起往前。
- 伴奏也錄在正中央的老歌，效果會打折。
- 這是重新平衡，不是人聲分離。

## 目錄

| 路徑 | 內容 |
|---|---|
| `app/` | 桌面調音台（Tkinter） |
| `web/` | 網頁版與測試 |
| `phone/` | 手機等化曲線 |
| `tools/` | 量測、驗收、裝置選擇腳本 |
| `sep/live.py` | 即時人聲分離實驗（模型不附） |
| `vocal_focus_*.txt` | 第一版三段固定設定（light／med／strong） |

## 授權

MIT
