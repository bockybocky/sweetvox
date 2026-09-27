# 甜嗓 SweetVox 網頁版 — 交付報告

工作名稱：**【甜嗓網頁版】**
日期：2026-09-23
工作資料夾：`E:\AI\workspace\vocal_focus\web\`
依 `SPEC_web.md` 執行；桌面版 `E:\AI\workspace\vocal_focus\app\vocal_focus_gui.py` **沒有被改**（md5 前後相同，見第 6 節）。

---

## 1. 交付物

| 檔案 | 大小 | md5 | 說明 |
|---|---|---|---|
| `sweetvox.js` | 45,675 B | `27ebc38521fbc04e8d2196efc1beeb1f` | 唯一的交付程式。一般 `<script defer>` 載入，非 ES module、無外部套件、不發任何網路請求 |
| `demo.html` | 939 B | `ba018f6b5ad4e33cb2175f4d71103161` | 本機試用頁：只放一個 `<div data-lab-demo="sweetvox" data-lang="zh-TW">` ＋ 載入 `sweetvox.js` |
| `test_sweetvox.mjs` | 35,463 B | `2cc89d4e1eaa212ef47d72b881343c0c` | 驗收程式（V1～V7），自己叫 Python 產生參考值、自己開無頭 Chrome |
| `REPORT.md` | 本檔 | — | 做了什麼、驗收數字、已知限制 |
| `web.done` | 5 B | — | `rc=0` |

（這四支的 md5 就是最後一次驗收跑的那一版：`test_results.json` 的 `artifacts` 欄位有同樣的數字。）

輔助檔（不是交付程式，但驗收要看得到，所以留在同一夾）：

| 檔案 | 說明 |
|---|---|
| `make_python_reference.py` | 直接 import 桌面版 `vocal_focus_gui.py`（唯讀），用它的 `_biquad`/`_mag_db`/`safe_preamp`/`build_config` 算出參考值 |
| `python_reference.json` | 上一支產生的參考值（桌面版 md5：`c70aba72f54344a0c6bdf7092f18ee6a`） |
| `test_results.json` | 驗收程式的完整結果（每個數字都在裡面） |
| `test_run_log.txt` | 驗收程式的原始輸出（就是下面那些數字的來源） |
| `shots/` | `demo_{light,dark}_{360,1200}.png` 四張截圖 |
| `design/` | 挑真空管曲線參數用的兩支試算（`scratch_tube_design.py`、`scratch_tube_grid.py`），證明 k/b 不是憑感覺選的 |

怎麼跑驗收：

```
cd E:\AI\workspace\vocal_focus\web
node test_sweetvox.mjs          # 全部通過時 exit code 0；結果寫進 test_results.json
```

不需要 `npm install` 任何東西：Node 內建的 WebSocket / fetch 直接跟 Chrome 的 DevTools Protocol 講話，Chrome 用本機已安裝的（`C:\Program Files\Google\Chrome\Application\chrome.exe`，實測 Chrome 153 `--headless=new`）。

---

## 2. 介面（Iris 要接的合約）

- 掛載：`<div data-lab-demo="sweetvox" data-lang="zh-TW"></div>` ＋ `<script defer src="sweetvox.js"></script>`；
  檔案最底部就是合約指定的那行 `document.querySelectorAll('[data-lab-demo="sweetvox"]').forEach(mountSweetvox);`
- `mountSweetvox(mount)` 在 div 裡自己長出全部介面；`data-lang="en"` 走英文，其他一律繁中（兩套字在檔內 `STRINGS` 物件）。
- 樣式：全部 `swx-` 前綴，一段 `<style id="swx-style">` 只插一次（重複 mount 不會重複插）；顏色用 CSS 變數並在使用處給預設值
  （例如 `var(--swx-accent, #ff8fb1)`），所以部落格可以用 `--swx-*` 覆寫；深色底走 `@media (prefers-color-scheme: dark)`。
- 可及性：每個滑桿都在 `<label>` 裡並顯示目前值；「甜嗓／原音」切換鈕用 `aria-pressed`；預設鈕也是 `aria-pressed`。
- 介面功能：選檔（mp3／m4a／wav／flac）→ 播放／暫停 → 甜嗓／原音切換 → 四個預設＋重設 → 8 個滑桿＋2 個勾選 → 下載 Equalizer APO 設定檔。
- 介面上有一行字老實寫：「這個頁面只碰得到你自己選的那個檔案，聽不到 YouTube Music（或其他播放器）的聲音」。
- 另外 `window.SweetVox` 曝露了一組純函式與離線渲染（`safePreamp`、`configPreamp`、`buildConfigText`、`filterSpecs`、`buildGraph`、`renderOffline`…）。
  驗收程式就是靠它量數字的；一般頁面不需要用到。這組 API 有動到的話要重跑驗收。

## 3. 處理鏈（跟桌面版對齊）

`<audio>` → `MediaElementSource` → `ChannelSplitter`＋`GainNode` 拆
MID＝(L+R)/2、SIDE＝(L−R)/2 → 兩條鏈各自處理 → 還原 L＝MID+SIDE、R＝MID−SIDE → 全域 Preamp → 輸出。

- MID 鏈：`HPQ subcut`（Q0.7）→ `LS 150 warm`（Q0.7）→ `PK 350 mud`（Q1.4）→ `PK 3000 sweet`（Q0.9）→ `PK 7500 sib`（Q2.0）→ `HS 10000 air`。
- 真空管（只在 MID）：WaveShaper 的偏壓 tanh 曲線 `y = norm·(tanh(k(x+b)) − tanh(kb))`，k=0.6、b=0.18，
  推力＝前推 drive dB → 飽和 → 後拉等量 dB（音量不變）；曲線後面補一顆 10 Hz 高通擋掉飽和產生的直流。
- SIDE 鏈：音量 side dB → `PK 2000 −1.5 dB`（Q0.8）→ centerbass 開時加 `HPQ 100`（Q0.7）。
- 全域 Preamp：跟桌面版同一套公式（`safe_preamp` ＋ `build_config` 的上下限），`vst_air` 一律當關。
- 四個預設數字照桌面版 `PRESETS` 原樣搬；下載的 txt 逐行等於桌面版 `build_config()`。
- 濾波器增益正好 0 的那一段會走旁通（乾路徑），因為 0 dB 的 biquad 雖然振幅是 1，相位仍不是 1；
  旁通後「全部濾波 0」時輸出才會跟輸入逐樣本相同（V6 就是量這個）。

## 4. 驗收結果（判定：通過／失敗／無法判定）

驗收環境：Windows 11、Node v24.21.0、Chrome 153 `--headless=new`、離線渲染取樣率 96 kHz（＝桌面版算係數用的 `fs`）。

| # | 測什麼 | 門檻 | 實測 | 判定 |
|---|---|---|---|---|
| V1 | 四個預設 MID 鏈頻率響應（20 Hz～20 kHz 每 1/12 八度，共 120 點 × 4 預設）對 Python `_biquad`/`_mag_db` | 峰值／低通段 ≤ 0.1 dB；架式段 ≤ 0.8 dB | 峰值段最大 **0.007 dB**（濃 @ 339.0 Hz）；架式段最大 **0.010 dB**（濃 @ 95.1 Hz） | **通過** |
| V2 | 四個預設 Preamp 對 Python `safe_preamp()` | 差 ≤ 0.05 dB | 最大差 **0.0000 dB**（淡 −4.656／中 −5.154／濃 −6.060／深夜甜嗓 −6.101） | **通過** |
| V3 | 「下載設定檔」的文字對 Python `build_config()`（去掉時間戳那行）逐行比對 | 完全相同 | 四個預設＋下載鈕實際吐出的 Blob＋**用滑鼠按介面上的預設鈕之後**的文字，全部逐行相同（34～35 行） | **通過** |
| V4 | 「中」預設，純正中 3 kHz 正弦 vs 純兩側 3 kHz 正弦的增益差 | 同方向且 ≥ 3 dB | 正中 **−4.26 dB**、兩側 **−13.19 dB** → 差 **+8.93 dB**（女聲往前推） | **通過** |
| V5 | 四個預設 × 滿刻度粉紅雜訊 10 秒（峰值刻度 0 dBFS） | 峰值 ≤ −0.5 dBFS | 最差 **−7.12 dBFS**（淡）；中 −8.55、濃 −10.30、深夜甜嗓 −10.86 | **通過** |
| V6 | 全部濾波 0、tube 關、Preamp 0 → 輸出＝輸入 | 最大誤差 < 1e-6 | L **5.96e-8**、R **5.96e-8** | **通過** |
| V7 | 無頭 Chrome 開 `demo.html`，淺色／深色 × 寬 360／1200 各截一張 | 介面完整、無橫向捲軸、無主控台錯誤 | 四張截圖（60～68 KB）；四種組合 `documentElement.scrollWidth` 都等於視窗寬、沒有任何子元素超出邊界；主控台 **0 筆**錯誤 | **通過** |

補充：V1 用的是真的 `BiquadFilterNode.getFrequencyResponse()`，設定也走 `sweetvox.js` 自己的 `setBiquad()`（不是測試另外設一次），
所以量到的是程式實際會發出的響應。

### 4.1 附加量測（規格第 4 節要求、以及自己加驗的）

**真空管 THD（1 kHz 正弦、−12 dBFS 入力、Preamp 強制 0、跑真的渲染鏈）**

| 推力 | 網頁 WaveShaper THD | 偶次−奇次 | 桌面版 PurestWarm 實測表 |
|---|---|---|---|
| 0 dB | 0.82 % | +13.1 dB | 0.29 % |
| 3 dB | 1.17 % | +10.0 dB | 0.54 % |
| **6 dB** | **1.70 %** | **+6.9 dB** | 0.98 % |
| 9 dB | 2.52 % | +3.7 dB | 1.82 % |
| 12 dB | 3.84 % | +0.5 dB | 3.40 % |
| 18 dB | 9.53 % | −6.5 dB | 11.71 % |

規格要求「推力 6 dB 時 1 kHz 正弦的 THD 在 1%～3%」→ 實測 **1.70%**，判定 **通過**；
推力 6 dB 時偶次諧波比奇次高 6.9 dB（桌面版同一支量到的是 +6.5 dB），偶次為主的性格有做出來。
（推力關掉時整條鏈的 THD 是 0.0043% ＝ 純粹是 render 的浮點誤差。）

**A/B 切換不中斷播放** — 驗收程式自己產生一段 6 秒 wav 塞進檔案選擇器、按播放、切兩次：
播放位置 1.173 → 1.781 → 2.381 秒（一直往前），`paused` 全程 false，`aria-pressed` 正確翻轉 → 判定 **通過**。
（「不爆音」這點無頭環境沒有音訊裝置可以聽，只能說切換只做 25 ms 交叉淡化、不動 `<audio>` 的播放／位置，沒有中斷播放的機制。）

**實際播放取樣率 vs 驗算基準** — 播放時 `AudioContext` 用的是裝置取樣率（通常是 48 kHz），而桌面版算係數用 96 kHz，
同一組 RBJ 係數在兩個取樣率下的數位響應會有一點差：實測最大 **0.204 dB @ 13.7 kHz**（濃），其他預設 0.09～0.17 dB。
這是雙線性轉換的差，低頻幾乎無感，只有 10 kHz 以上的架式段邊緣差 0.2 dB 以內。

## 5. 已知限制（老實講）

1. **碰不到 YouTube Music**：網頁只能處理你選的那個檔案。想聽串流音樂的甜嗓，只能用桌面版＋Equalizer APO。這行字已經寫在介面上。
2. **真空管不是 PurestWarm**：網頁沒有 VST。用 WaveShaper 做偏壓 tanh 的偶次諧波飽和，數字對照見上表：
   低推力時諧波比桌面版多一些（0 dB 推力 0.82% vs 0.29%），中高推力接近。聽起來不會一模一樣。
   另外 `oversample='none'`（跟桌面版一樣零延遲），推力拉很大時理論上會有 aliasing——實測推力 18 dB 的 THD 9.53% 裡看不出異常，但這點沒有專門量。
3. **架式濾波器的 Q**：Web Audio 的 `lowshelf`／`highshelf` 固定斜率（S=1，等效 Q≈0.7071），不吃 Q 參數；
   桌面版寫的是 Q 0.7（150 Hz）與 Q 0.707（10 kHz）。實測這條差 **最大 0.010 dB**，遠低於規格允許的 0.8 dB，所以實務上沒有影響。
4. **Web Audio 的高通／低通，Q 的單位是 dB**：不換算的話截止頻率上會差 3.8 dB（一開始真的中了這個，V1 第一輪量到 3.8 dB 的差）。
   `setBiquad()` 已經做 `20·log10(Q)` 換算，換算後 V1 的差降到 0.007 dB。這一點寫在程式註解裡，以後改的人不要再踩。
5. **曲線定義域**：`WaveShaper` 的輸入定義域固定是 ±1，所以曲線前後各乘一次 headroom（÷4、×4，淨增益不變），
   讓 ±1 對應到實際訊號的 ±4（約 +12 dBFS）才不會在大音量時撞到硬切。同理，**推力拉很大＋檔案本身很滿刻度時，輸出會被壓縮**（飽和本來就會這樣）。
6. **下載的設定檔裡有 Charles 本機的路徑**：真空管那兩行是 `VSTPlugin: Library "E:\AI\...\PurestWarm64.dll"`。
   規格要求「跟桌面版 build_config() 同內容」，所以我逐行照抄；別人下載後要自己改路徑或把真空管那兩行刪掉，不然 APO 會找不到外掛。
7. **「整體音量補償」往上加不會有變化**：桌面版同一條公式（沒有 Air 外掛時上限就是 `safe_preamp`），只有往下調有效。
   這點寫在介面提示文字裡，不是 bug。
8. **subcut（35／85 Hz 高通）只有預設在帶**，介面沒有獨立旋鈕——跟桌面版一樣（桌面版的 subcut 也只由預設決定）。
9. **沒在真的部落格頁面測過**：只在 `file://` 下測。掛進 blog.getrealpha.com 之後要確認兩件事：
   ① 頁面自己的 CSS 不要蓋掉 `swx-` 的樣式；② 下載紐在 https 下仍能存檔（用的是 Blob ＋ `a.click()`，正常會動，但沒有實測過 https）。
10. **格式支援取決於瀏覽器**：flac／m4a 在 Chrome／Firefox 沒問題，Safari（尤其 iOS）對某些 m4a／flac 可能不吃；
    iOS 上第一次播放一定要使用者自己按「播放」（程式已經設計成按鈕觸發 AudioContext）。
11. **手機寬 360px** 在無頭 Chrome 上沒有橫向捲軸、沒有元素超界；但**真機**（iOS Safari／Android Chrome 的網址列與字型差異）沒有實測。
12. **A/B 切換的「不爆音」**：機制上只做 25 ms 交叉淡化，聽感沒人在這台無頭環境聽過；要確認請 Charles 在有音效卡的瀏覽器上實際聽。

## 6. 沒動到的東西（可回滾）

- 桌面版 `E:\AI\workspace\vocal_focus\app\vocal_focus_gui.py`：驗收前後 md5 都是 `c70aba72f54344a0c6bdf7092f18ee6a`（同一支 `make_python_reference.py` 每次跑都會重新印出來比對）。
- Equalizer APO 目前的設定（`C:\Program Files\EqualizerAPO\config\`）**完全沒碰**，沒有寫入任何檔。
- 沒有動 `E:\AI\workspace\vocal_focus\web\` 以外的任何檔案。
- 沒用到顯卡，沒碰 `gpu_gate`、沒碰 comfy 相關工作。
- 要回滾：把 `sweetvox.js`／`demo.html` 兩支從部落格拿掉就好；桌面版與 APO 從頭到尾沒被改。

## 7. 給 Iris 的接線備忘

- 只要 `sweetvox.js` 一個檔（`demo.html` 是本機試用，不用上線）。
- 分頁裡放 `<div data-lab-demo="sweetvox" data-lang="zh-TW"></div>`，再 `<script defer src="/path/sweetvox.js"></script>`；
  同一個頁面可以放多個 div（會各自獨立、共用一份樣式表）。
- 想改配色：在有 `swx-` 元素的祖先節點上設 `--swx-accent`（預設粉 `#ff8fb1`）、`--swx-accent2`（琥珀 `#c8842a`）、
  `--swx-txt`、`--swx-bg`、`--swx-card`、`--swx-line`、`--swx-dim`、`--swx-accent-ink`、`--swx-accent2-ink`、`--swx-focus` 即可。
- 要驗收就 `node test_sweetvox.mjs`（會用到本機 Python 與 Chrome，不會寫任何檔到 web\ 以外）。
