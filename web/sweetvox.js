/*!
 * 甜嗓 SweetVox — 網頁版（女聲前移 · 通透 · 真空管暖度）
 * 版本 1.0.0 ｜ 2026-09-23 ｜ 工作資料夾 E:\AI\workspace\vocal_focus\web\
 *
 * 一般 <script defer> 載入即可，不用 ES module、不用任何外部套件、不發任何網路請求。
 *
 *   <div data-lab-demo="sweetvox" data-lang="zh-TW"></div>
 *   <script defer src="sweetvox.js"></script>
 *
 * 處理鏈跟桌面版 E:\AI\workspace\vocal_focus\app\vocal_focus_gui.py 的 build_config() 一致：
 *   <audio> → MediaElementSource → 拆 MID／SIDE → 各自處理 → 還原 L/R → 全域 Preamp → 輸出
 * 音訊全程在你的瀏覽器裡處理，不上傳、不連外。
 *
 * 對外（Iris 會用到的）：
 *   window.mountSweetvox(mountEl)  — 在指定的 div 裡建出整個介面
 *   window.SweetVox                — 純函式與離線渲染（驗收程式用，見 REPORT.md）
 */
(function (global) {
  'use strict';

  var VERSION = '1.0.0';

  /* =========================================================================
     1. 常數 —— 跟桌面版同一套數字
     ========================================================================= */

  var FS_REF = 96000.0;          // 桌面版算係數用的取樣率（跟 APO 實測一致）
  var AIR_EXTRA_DB = 3.2;        // 桌面版「通透（Air 外掛）」預留的餘裕；網頁沒有 Air 外掛，vst_air 一律當關
  var TUBE_AUTO_DB = 3.0;
  var SAFE_MARGIN_DB = 1.5;

  // 桌面版設定檔裡指到的 VST（下載下來的 txt 要跟桌面版逐行一樣，所以路徑照抄）
  var VST_WARM = 'E:\\AI\\workspace\\vocal_focus\\vst\\airwindows\\WinVST64s\\PurestWarm64.dll';

  // 真空管曲線（WaveShaper）：溫和的偶次諧波飽和
  //   y = norm * ( tanh(k*(x + b)) - tanh(k*b) )
  //   k=0.6、b=0.18 的實測（1 kHz 正弦、-12 dBFS 入力、推力 6 dB）：THD 1.7%、偶次比奇次高 6.8 dB
  //   WaveShaper 的輸入定義域固定是 ±1，所以進曲線前先除以 TUBE_HEADROOM、出來再乘回來
  //   （淨增益不變，但曲線的 ±1 等於實際訊號的 ±4 ≈ +12 dBFS，大音量時不會撞到硬切）
  var TUBE_K = 0.6, TUBE_BIAS = 0.18, TUBE_HEADROOM = 4.0, TUBE_CURVE_N = 4096;
  var TUBE_DC_FC = 10.0;         // 真空管前面那段會產生一點直流 → 後面掛 10 Hz 高通擋掉

  var DEFAULTS = {
    side: -7.0, sweet: 1.2, mud: -3.0, sib: -1.0, warm: 1.5, air: 2.0,
    gain: 0.0, vst_air: false, tube: true, tube_drive: 6.0,
    centerbass: false, on: true, subcut: 35.0,
    side_pk_db: -1.5          // SIDE 鏈固定的 2000 Hz -1.5 dB（介面不給調；V6 結構測試要能設 0）
  };

  // 四個預設（照桌面版 PRESETS 原樣搬）
  var PRESETS = [
    { id: '淡', name: { 'zh-TW': '淡', en: 'Light' },
      v: { side: -4.0, sweet: 1.0, mud: -2.0, sib: -0.8, warm: 1.0, air: 1.0, centerbass: false, subcut: 35.0 } },
    { id: '中', name: { 'zh-TW': '中', en: 'Medium' },
      v: { side: -7.0, sweet: 1.2, mud: -3.0, sib: -1.0, warm: 1.5, air: 1.5, centerbass: false, subcut: 35.0 } },
    { id: '濃', name: { 'zh-TW': '濃', en: 'Strong' },
      v: { side: -11.0, sweet: 2.0, mud: -3.5, sib: -1.2, warm: 2.0, air: 2.5, centerbass: true, subcut: 35.0 } },
    { id: '深夜甜嗓', name: { 'zh-TW': '深夜甜嗓', en: 'Late night' },
      v: { side: -9.0, sweet: 2.0, mud: -3.0, sib: 0.0, warm: 0.5, air: 2.5,
           centerbass: true, subcut: 85.0, tube: true, tube_drive: 6.0 } }
  ];

  /* =========================================================================
     2. 文字（兩套都放在這一個物件裡）
     ========================================================================= */

  var STRINGS = {
    'zh-TW': {
      title: '甜嗓', title2: 'SweetVox', sub: '女聲前移 · 通透 · 真空管暖度',
      note: '這個頁面只碰得到你自己選的那個檔案，聽不到 YouTube Music（或其他播放器）的聲音。全程在你的瀏覽器裡處理，不會上傳。',
      pick: '選一個音樂檔（mp3／m4a／wav／flac）', nofile: '還沒選檔',
      play: '播放', pause: '暫停',
      ab_on: '甜嗓', ab_off: '原音', ab_hint_on: '（按一下切回原音）', ab_hint_off: '（按一下切甜嗓）',
      reset: '重設', presets: '預設',
      sec_voice: '女聲（正中那條鏈）', sec_side: '伴奏（兩側）與音量', sec_tube: '溫暖與通透（真空管）',
      l_sweet: '女聲甜度 3k', l_mud: '去濁 350 Hz', l_sib: '收齒音 7.5k', l_air: '空氣感 10k+',
      l_side: '伴奏退後量', l_gain: '整體音量補償', l_warm: '溫暖 150 Hz', l_drive: '真空管推力',
      cb_centerbass: '低頻置中（兩側 100 Hz 以下砍掉）',
      cb_tube: '真空管暖度（溫和的偶次諧波飽和）',
      preamp: '自動餘裕 Preamp：', 
      dl: '下載 Equalizer APO 設定檔',
      dl_hint: '給 Windows 使用者：下載後放到 Equalizer APO 的 config 資料夾，重開機或重新載入設定才會生效。',
      gain_hint: '網頁上沒有桌面版的 Air 外掛，所以「整體音量補償」往上加不會有變化（跟桌面版同一條公式，往下才有效）。',
      tube_hint: '推力拉到 0 以上會自動開啟。實測（-12 dBFS、1 kHz 正弦、推力 6 dB）THD 約 1.7%，偶次諧波為主。',
      err_noaudio: '這個瀏覽器不支援 Web Audio，沒辦法即時試聽（下面的設定檔還是可以下載）。',
      err_load: '這個檔案讀不進來（格式或授權問題），換一個試試。',
      nofile_short: '先選一個音樂檔。',
      version: '網頁版'
    },
    en: {
      title: 'SweetVox', title2: '', sub: 'Vocal forward · clarity · tube warmth',
      note: 'This page only sees the file you pick. It cannot hear YouTube Music (or any other player). Everything runs inside your browser — nothing is uploaded.',
      pick: 'Choose a music file (mp3／m4a／wav／flac)', nofile: 'no file chosen',
      play: 'Play', pause: 'Pause',
      ab_on: 'SweetVox', ab_off: 'Original', ab_hint_on: ' (click for original)', ab_hint_off: ' (click for SweetVox)',
      reset: 'Reset', presets: 'Presets',
      sec_voice: 'Vocal (center chain)', sec_side: 'Backing (sides) & level', sec_tube: 'Warmth & air (tube)',
      l_sweet: 'Sweetness 3k', l_mud: 'De-mud 350 Hz', l_sib: 'De-ess 7.5k', l_air: 'Air 10k+',
      l_side: 'Backing push-back', l_gain: 'Overall level', l_warm: 'Warmth 150 Hz', l_drive: 'Tube drive',
      cb_centerbass: 'Center the bass (cut below 100 Hz on the sides)',
      cb_tube: 'Tube warmth (gentle even-harmonic saturation)',
      preamp: 'Auto headroom preamp: ',
      dl: 'Download Equalizer APO config',
      dl_hint: 'For Windows: put the file in Equalizer APO\u2019s config folder and reload the config.',
      gain_hint: 'There is no Air plugin on the web version, so raising "Overall level" has no effect (same formula as the desktop version \u2014 only lowering works).',
      tube_hint: 'Turning drive above 0 switches it on. Measured: -12 dBFS 1 kHz sine at 6 dB drive \u2192 THD \u2248 1.7%, mostly even harmonics.',
      err_noaudio: 'This browser has no Web Audio support, so live monitoring is unavailable (you can still download the config).',
      err_load: 'This file could not be loaded. Try another one.',
      nofile_short: 'Pick a music file first.',
      version: 'web'
    }
  };

  function langOf(mount) {
    var l = (mount && mount.dataset && mount.dataset.lang) || '';
    return String(l).toLowerCase() === 'en' ? 'en' : 'zh-TW';
  }

  /* =========================================================================
     3. 數學 —— 逐行照桌面版的 _biquad / _mag_db / _chain_peak_db / safe_preamp
     ========================================================================= */

  function biquadCoef(kind, f0, gainDb, q, fs) {
    fs = fs || FS_REF;
    var A = Math.pow(10, gainDb / 40);
    var w = 2 * Math.PI * f0 / fs;
    var cw = Math.cos(w), sw = Math.sin(w);
    var alpha = sw / (2 * q);
    var b0, b1, b2, a0, a1, a2, tsa;
    if (kind === 'PK') {
      b0 = 1 + alpha * A; b1 = -2 * cw; b2 = 1 - alpha * A;
      a0 = 1 + alpha / A; a1 = -2 * cw; a2 = 1 - alpha / A;
    } else if (kind === 'LS') {
      tsa = 2 * Math.sqrt(A) * alpha;
      b0 = A * ((A + 1) - (A - 1) * cw + tsa);
      b1 = 2 * A * ((A - 1) - (A + 1) * cw);
      b2 = A * ((A + 1) - (A - 1) * cw - tsa);
      a0 = (A + 1) + (A - 1) * cw + tsa;
      a1 = -2 * ((A - 1) + (A + 1) * cw);
      a2 = (A + 1) + (A - 1) * cw - tsa;
    } else if (kind === 'HS') {
      tsa = 2 * Math.sqrt(A) * alpha;
      b0 = A * ((A + 1) + (A - 1) * cw + tsa);
      b1 = -2 * A * ((A - 1) + (A + 1) * cw);
      b2 = A * ((A + 1) + (A - 1) * cw - tsa);
      a0 = (A + 1) - (A - 1) * cw + tsa;
      a1 = 2 * ((A - 1) - (A + 1) * cw);
      a2 = (A + 1) - (A - 1) * cw - tsa;
    } else if (kind === 'HP') {
      b0 = (1 + cw) / 2; b1 = -(1 + cw); b2 = (1 + cw) / 2;
      a0 = 1 + alpha; a1 = -2 * cw; a2 = 1 - alpha;
    } else {
      throw new Error('unknown filter kind: ' + kind);
    }
    return [b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0];
  }

  function magDb(c, f, fs) {
    fs = fs || FS_REF;
    var b0 = c[0], b1 = c[1], b2 = c[2], a1 = c[3], a2 = c[4];
    var w = 2 * Math.PI * f / fs;
    var cw1 = Math.cos(w), sw1 = Math.sin(w);
    var cw2 = Math.cos(2 * w), sw2 = Math.sin(2 * w);
    var nr = b0 + b1 * cw1 + b2 * cw2;
    var ni = -(b1 * sw1 + b2 * sw2);
    var dr = 1 + a1 * cw1 + a2 * cw2;
    var di = -(a1 * sw1 + a2 * sw2);
    return 10 * Math.log10((nr * nr + ni * ni) / (dr * dr + di * di));
  }

  function chainPeakDb(cascades, fs) {
    fs = fs || FS_REF;
    var best = -999.0, f = 20.0, g, i;
    while (f <= 20000) {
      g = 0;
      for (i = 0; i < cascades.length; i++) g += magDb(cascades[i], f, fs);
      if (g > best) best = g;
      f *= 1.02;
    }
    return best;
  }

  // 桌面版 safe_preamp()：回傳「保證不削波」的全域 Preamp
  function safePreamp(v) {
    v = v || {};
    var mid = [biquadCoef('LS', 150, num(v.warm, 0), 0.7, FS_REF),
               biquadCoef('PK', 350, num(v.mud, 0), 1.4, FS_REF),
               biquadCoef('PK', 3000, num(v.sweet, 0), 0.9, FS_REF),
               biquadCoef('PK', 7500, num(v.sib, 0), 2.0, FS_REF),
               biquadCoef('HS', 10000, num(v.air, 0), 0.707, FS_REF)];
    var side = [biquadCoef('PK', 2000, -1.5, 0.8, FS_REF)];
    var gm = chainPeakDb(mid, FS_REF);
    var gs = chainPeakDb(side, FS_REF) + num(v.side, 0);
    var bound = Math.max(Math.pow(10, gm / 20), Math.pow(10, gs / 20));
    var extra = v.vst_air ? AIR_EXTRA_DB : 0.0;      // 網頁沒有 Air 外掛，一律當關
    if (v.tube) extra += 0.5 + 0.11 * num(v.tube_drive, 0);
    return -(20 * Math.log10(Math.max(bound, 1e-6)) + 1.0) - extra - SAFE_MARGIN_DB;
  }

  // 桌面版 build_config() 裡真正寫進檔案的那個 Preamp（含 Clamp）
  function configPreamp(v) {
    v = v || {};
    var base = safePreamp(v);
    var ceil = base + (v.vst_air ? AIR_EXTRA_DB : 0.0);
    var preamp = base + num(v.gain, 0);
    if (preamp > ceil) preamp = ceil;
    if (preamp < -24.0) preamp = -24.0;
    return preamp;
  }

  function num(x, d) {
    var n = (x === null || x === undefined) ? NaN : Number(x);
    return isFinite(n) ? n : d;
  }

  /* =========================================================================
     4. 設定檔文字 —— 逐行照桌面版 build_config()
     ========================================================================= */

  function f1(x) { return num(x, 0).toFixed(1); }
  function f0(x) { return num(x, 0).toFixed(0); }
  function fplus1(x) { var n = num(x, 0); return (n < 0 ? '-' : '+') + Math.abs(n).toFixed(1); }
  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function timestampStr(d) {
    d = d || new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) + ' ' +
           pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds());
  }

  function buildConfigText(v, dateObj) {
    v = v || {};
    var base = safePreamp(v);
    var ceil = base + (v.vst_air ? AIR_EXTRA_DB : 0.0);
    var preamp = base + num(v.gain, 0);
    if (preamp > ceil) preamp = ceil;
    if (preamp < -24.0) preamp = -24.0;
    var L = [];
    L.push('# 甜嗓 SweetVox ─ 女聲前移／通透化（調整台寫入 ' + timestampStr(dateObj) + '）');
    L.push('# 自動餘裕 Preamp ' + f1(preamp) + ' dB：確保（甜度/溫暖/空氣感）推上去後不削波');
    L.push('Preamp: ' + f1(preamp) + ' dB');
    L.push('');
    if (v.vst_air) {   // 網頁永遠是關的；留著是為了跟桌面版逐行相同
      L.push('# 通透：Airwindows Air（免費 VST2、MIT）。放在拆中側之前，兩邊一起延遲，');
      L.push('# 避免只延遲正中造成的梳狀濾波。注意它會讓整體音量掉約 4~5 dB，用『整體音量補償』補回。');
      L.push('VSTPlugin: Library "E:\\AI\\workspace\\vocal_focus\\vst\\airwindows\\WinVST64s\\Air64.dll"');
      L.push('');
    }
    L.push('# 拆成 MID（正中＝女聲）／SIDE（兩側＝伴奏）');
    L.push('Channel: all');
    L.push('Copy: R=0.5*L+-0.5*R');
    L.push('Copy: L=L+-1.0*R');
    L.push('');
    L.push('# MID：女聲');
    L.push('Channel: L');
    L.push('Filter 1: ON HPQ Fc ' + f0(num(v.subcut, 35.0)) + ' Hz Q 0.7');
    L.push('Filter 2: ON LS Fc 150 Hz Gain ' + f1(num(v.warm, 0)) + ' dB Q 0.7');
    L.push('Filter 3: ON PK Fc 350 Hz Gain ' + f1(num(v.mud, 0)) + ' dB Q 1.4');
    L.push('Filter 4: ON PK Fc 3000 Hz Gain ' + f1(num(v.sweet, 0)) + ' dB Q 0.9');
    L.push('Filter 5: ON PK Fc 7500 Hz Gain ' + f1(num(v.sib, 0)) + ' dB Q 2.0');
    L.push('Filter 6: ON HS Fc 10000 Hz Gain ' + f1(num(v.air, 0)) + ' dB');
    if (v.tube) {
      L.push('');
      L.push('# 真空管暖度：Airwindows PurestWarm（MIT、VST2、零延遲）');
      L.push('# 只掛在正中（女聲）這條鏈；推力→飽和→等量衰減，音量不變');
      L.push('# 實測：推力 0 dB→THD 0.32%／推力 12 dB→THD 5.17%，兩者都是偶次諧波為主');
      L.push('Preamp: ' + fplus1(num(v.tube_drive, 0)) + ' dB');
      L.push('VSTPlugin: Library "' + VST_WARM + '"');
      L.push('Preamp: ' + fplus1(-num(v.tube_drive, 0)) + ' dB');
    }
    L.push('');
    L.push('# SIDE：伴奏');
    L.push('Channel: R');
    L.push('Preamp: ' + f1(num(v.side, 0)) + ' dB');
    L.push('Filter 1: ON PK Fc 2000 Hz Gain -1.5 dB Q 0.8');
    if (v.centerbass) {
      L.push('Filter 2: ON HPQ Fc 100 Hz Q 0.7');
    }
    L.push('');
    L.push('# 還原回 L/R');
    L.push('Channel: all');
    L.push('Copy: L=L+R');
    L.push('Copy: R=L+-2.0*R');
    return L.join('\n') + '\n';
  }

  /* =========================================================================
     5. 真空管飽和曲線（WaveShaper 用的表）
     ========================================================================= */

  var _tubeCurve = null;

  function tubeCurve() {
    if (_tubeCurve) return _tubeCurve;
    var n = TUBE_CURVE_N, out = new Float32Array(n);
    // 曲線的輸入座標 u∈[-1,1] 對應實際訊號 x = u*TUBE_HEADROOM
    //   → 曲線用 k*H、b/H（等價於對實際訊號套 k、b），輸出再乘回 H
    var H = TUBE_HEADROOM;
    var k = TUBE_K * H, b = TUBE_BIAS / H, tb = Math.tanh(k * b);
    var norm = 1.0 / (k * (1.0 - tb * tb));    // 讓 u→0 的斜率＝1（小訊號不被改變音量）
    for (var i = 0; i < n; i++) {
      var u = -1 + 2 * i / (n - 1);
      out[i] = norm * (Math.tanh(k * (u + b)) - tb);
    }
    _tubeCurve = out;
    return out;
  }

  /* =========================================================================
     6. 處理鏈（web 節點圖）—— 跟桌面版同一條鏈
     ========================================================================= */

  // 這條鏈上的濾波器（MID 與 SIDE），給「實際節點」與「驗收程式」共用同一份資料
  function filterSpecs(v) {
    v = v || {};
    var mid = [];
    if (num(v.subcut, 35.0) > 0) {
      mid.push({ kind: 'HP', node: 'highpass', f0: num(v.subcut, 35.0), gain: 0, q: 0.7 });
    }
    mid.push({ kind: 'LS', node: 'lowshelf', f0: 150, gain: num(v.warm, 0), q: 0.7 });
    mid.push({ kind: 'PK', node: 'peaking', f0: 350, gain: num(v.mud, 0), q: 1.4 });
    mid.push({ kind: 'PK', node: 'peaking', f0: 3000, gain: num(v.sweet, 0), q: 0.9 });
    mid.push({ kind: 'PK', node: 'peaking', f0: 7500, gain: num(v.sib, 0), q: 2.0 });
    mid.push({ kind: 'HS', node: 'highshelf', f0: 10000, gain: num(v.air, 0), q: 0.707 });
    var side = [
      { kind: 'PK', node: 'peaking', f0: 2000, gain: num(v.side_pk_db, -1.5), q: 0.8 }
    ];
    if (v.centerbass) {
      side.push({ kind: 'HP', node: 'highpass', f0: 100, gain: 0, q: 0.7 });
    }
    return { mid: mid, side: side };
  }

  // 這個 stage 要不要真的接進電路（增益 0 的架式／峰值＝數學上的 1，跳過才不會有相位差）
  function specActive(spec) {
    if (spec.kind === 'HP') return true;      // 清單裡有就代表要開
    return Math.abs(num(spec.gain, 0)) > 1e-12;
  }

  // 把一個 filterSpec 套到 Web Audio 的 BiquadFilterNode 上。
  // ⚠️ Web Audio 的 highpass／lowpass，Q 的單位是「dB」不是線性 Q（實測：Q=0.7 會變成線性 Q=1.084，
  //    在截止頻率上差 3.8 dB）→ 這裡換算成 dB 送進去，才會跟桌面版 APO 的 Q 一樣。
  function setBiquad(bq, spec) {
    bq.type = spec.node;
    bq.frequency.value = spec.f0;
    if (spec.node === 'highpass' || spec.node === 'lowpass') {
      bq.Q.value = 20 * Math.log10(spec.q);
    } else {
      bq.Q.value = spec.q;    // 架式的 Q：Web Audio 一律用固定斜率（S=1），設了不影響
    }
    if (spec.node === 'peaking' || spec.node === 'lowshelf' || spec.node === 'highshelf') {
      bq.gain.value = num(spec.gain, 0);
    }
  }

  function makeStage(ctx, spec) {
    var st = { spec: spec };
    st.input = ctx.createGain();
    st.output = ctx.createGain();
    st.biquad = ctx.createBiquadFilter();
    setBiquad(st.biquad, spec);
    st.wet = ctx.createGain();
    st.dry = ctx.createGain();
    st.input.connect(st.biquad);
    st.biquad.connect(st.wet);
    st.wet.connect(st.output);
    st.input.connect(st.dry);
    st.dry.connect(st.output);
    return st;
  }

  function setStageActive(st, on, ramp, now) {
    var w = on ? 1 : 0, d = on ? 0 : 1;
    if (ramp) {
      st.wet.gain.setTargetAtTime(w, now, 0.01);
      st.dry.gain.setTargetAtTime(d, now, 0.01);
    } else {
      st.wet.gain.value = w;
      st.dry.gain.value = d;
    }
  }

  /**
   * 建出「甜嗓」這條鏈（不含 <audio> 與 A/B 切換）。
   * 回傳 { input, output, preamp, midStages, sideStages, tube, sideGain }
   */
  function buildGraph(ctx, v) {
    var specs = filterSpecs(v);
    var input = ctx.createGain();
    var splitter = ctx.createChannelSplitter(2);
    input.connect(splitter);

    // ---- 拆 MID／SIDE：MID=(L+R)/2、SIDE=(L-R)/2 ----
    var midSum = ctx.createGain(), sideSum = ctx.createGain();
    var gLM = ctx.createGain(), gRM = ctx.createGain(), gLS = ctx.createGain(), gRS = ctx.createGain();
    gLM.gain.value = 0.5; gRM.gain.value = 0.5; gLS.gain.value = 0.5; gRS.gain.value = -0.5;
    splitter.connect(gLM, 0); splitter.connect(gRM, 1);
    splitter.connect(gLS, 0); splitter.connect(gRS, 1);
    gLM.connect(midSum); gRM.connect(midSum);
    gLS.connect(sideSum); gRS.connect(sideSum);

    // ---- MID 鏈 ----
    var midStages = [], i, prev = midSum;
    for (i = 0; i < specs.mid.length; i++) {
      var st = makeStage(ctx, specs.mid[i]);
      prev.connect(st.input);
      prev = st.output;
      midStages.push(st);
    }

    // ---- 真空管暖度（只在 MID）----
    var tube = { input: ctx.createGain(), output: ctx.createGain() };
    tube.pre = ctx.createGain();
    tube.shaper = ctx.createWaveShaper();
    tube.shaper.curve = tubeCurve();
    tube.shaper.oversample = 'none';           // 跟桌面版一樣零延遲（見 REPORT 的限制說明）
    tube.post = ctx.createGain();
    tube.dc = ctx.createBiquadFilter();
    tube.dc.type = 'highpass';
    tube.dc.frequency.value = TUBE_DC_FC;
    tube.dc.Q.value = 20 * Math.log10(0.707);   // 高通 Q 用 dB（見 setBiquad 的說明）
    tube.wet = ctx.createGain();
    tube.dry = ctx.createGain();
    tube.input.connect(tube.pre);
    tube.pre.connect(tube.shaper);
    tube.shaper.connect(tube.post);
    tube.post.connect(tube.dc);
    tube.dc.connect(tube.wet);
    tube.wet.connect(tube.output);
    tube.input.connect(tube.dry);
    tube.dry.connect(tube.output);
    prev.connect(tube.input);
    var midOut = tube.output;

    // ---- SIDE 鏈 ----
    var sideGain = ctx.createGain();
    sideSum.connect(sideGain);
    var sideStages = [];
    prev = sideGain;
    for (i = 0; i < specs.side.length; i++) {
      var st2 = makeStage(ctx, specs.side[i]);
      prev.connect(st2.input);
      prev = st2.output;
      sideStages.push(st2);
    }
    var sideOut = prev;

    // ---- 還原 L/R：L = MID+SIDE、R = MID-SIDE ----
    var outL = ctx.createGain(), outR = ctx.createGain();
    var midToL = ctx.createGain(), midToR = ctx.createGain();
    var sideToL = ctx.createGain(), sideToR = ctx.createGain();
    midToL.gain.value = 1; midToR.gain.value = 1;
    sideToL.gain.value = 1; sideToR.gain.value = -1;
    midOut.connect(midToL); midToL.connect(outL);
    sideOut.connect(sideToL); sideToL.connect(outL);
    midOut.connect(midToR); midToR.connect(outR);
    sideOut.connect(sideToR); sideToR.connect(outR);

    // ---- 全域 Preamp（＝桌面版寫進 config 的那個值）----
    var merger = ctx.createChannelMerger(2);
    outL.connect(merger, 0, 0);
    outR.connect(merger, 0, 1);
    var preamp = ctx.createGain();
    merger.connect(preamp);
    var output = ctx.createGain();
    preamp.connect(output);

    var g = {
      input: input, output: output, preamp: preamp, midStages: midStages,
      sideStages: sideStages, sideGain: sideGain, tube: tube, splitter: splitter
    };
    applyState(g, v, false, 0);
    return g;
  }

  /** 把參數套到已建好的節點上（ramp=true 給即時試聽用，避免切換爆音） */
  function applyState(g, v, ramp, now) {
    v = v || {};
    var i;
    for (i = 0; i < g.midStages.length; i++) {
      var st = g.midStages[i];
      setBiquad(st.biquad, st.spec);
      setStageActive(st, specActive(st.spec), ramp, now);
    }
    for (i = 0; i < g.sideStages.length; i++) {
      var st2 = g.sideStages[i];
      setBiquad(st2.biquad, st2.spec);
      setStageActive(st2, specActive(st2.spec), ramp, now);
    }
    if (ramp) g.sideGain.gain.setTargetAtTime(Math.pow(10, num(v.side, 0) / 20), now, 0.01);
    else g.sideGain.gain.value = Math.pow(10, num(v.side, 0) / 20);
    setStageActive(g.tube, !!v.tube, ramp, now);
    var d = num(v.tube_drive, 0);
    var gp = Math.pow(10, d / 20);
    // 推力：先推 d dB → 飽和 → 再拉回 d dB（音量不變）。中間再乘一次曲線的 headroom 反向補償。
    var preGain = gp / TUBE_HEADROOM, postGain = TUBE_HEADROOM / gp;
    if (ramp) {
      g.tube.pre.gain.setTargetAtTime(preGain, now, 0.01);
      g.tube.post.gain.setTargetAtTime(postGain, now, 0.01);
    } else {
      g.tube.pre.gain.value = preGain;
      g.tube.post.gain.value = postGain;
    }
    var pv = configPreamp(v);
    var p = Math.pow(10, pv / 20);
    if (ramp) g.preamp.gain.setTargetAtTime(p, now, 0.01);
    else g.preamp.gain.value = p;
    return pv;
  }

  /* =========================================================================
     7. 離線渲染（驗收程式 V4／V5／V6 用；也可給別的頁面做批次處理）
     ========================================================================= */

  function makeSignal(ctx, n, sr, sig) {
    sig = sig || { type: 'sine', freq: 1000, amp: 0.25, mode: 'mid' };
    var buf = ctx.createBuffer(2, n, sr);
    var L = buf.getChannelData(0), R = buf.getChannelData(1), i;
    if (sig.type === 'sine') {
      var amp = num(sig.amp, 0.25), f = num(sig.freq, 1000), w = 2 * Math.PI * f / sr;
      var mode = sig.mode || 'mid';
      for (i = 0; i < n; i++) {
        var s = amp * Math.sin(w * i);
        if (mode === 'side') { L[i] = s; R[i] = -s; }
        else if (mode === 'left') { L[i] = s; R[i] = 0; }
        else if (mode === 'right') { L[i] = 0; R[i] = s; }
        else { L[i] = s; R[i] = s; }
      }
    } else if (sig.type === 'pink' || sig.type === 'white') {
      var s1 = num(sig.seed, 1) >>> 0, s2 = (num(sig.seed, 1) + 7919) >>> 0;
      var pk = 0;
      var b = [0, 0, 0, 0, 0, 0, 0];
      var c = [0, 0, 0, 0, 0, 0, 0];
      for (i = 0; i < n; i++) {
        s1 = (s1 * 1664525 + 1013904223) >>> 0;
        var w1 = (s1 / 4294967296) * 2 - 1;
        s2 = (s2 * 1664525 + 1013904223) >>> 0;
        var w2 = (s2 / 4294967296) * 2 - 1;
        var p1, p2;
        if (sig.type === 'pink') {
          // Paul Kellet 的 economy pink filter（兩聲道各自一組狀態）
          b[0] = 0.99886 * b[0] + w1 * 0.0555179;
          b[1] = 0.99332 * b[1] + w1 * 0.0750759;
          b[2] = 0.96900 * b[2] + w1 * 0.1538520;
          b[3] = 0.86650 * b[3] + w1 * 0.3104856;
          b[4] = 0.55000 * b[4] + w1 * 0.5329522;
          b[5] = -0.7616 * b[5] - w1 * 0.0168980;
          p1 = (b[0] + b[1] + b[2] + b[3] + b[4] + b[5] + b[6] + w1 * 0.5362) * 0.11;
          b[6] = w1 * 0.115926;
          c[0] = 0.99886 * c[0] + w2 * 0.0555179;
          c[1] = 0.99332 * c[1] + w2 * 0.0750759;
          c[2] = 0.96900 * c[2] + w2 * 0.1538520;
          c[3] = 0.86650 * c[3] + w2 * 0.3104856;
          c[4] = 0.55000 * c[4] + w2 * 0.5329522;
          c[5] = -0.7616 * c[5] - w2 * 0.0168980;
          p2 = (c[0] + c[1] + c[2] + c[3] + c[4] + c[5] + c[6] + w2 * 0.5362) * 0.11;
          c[6] = w2 * 0.115926;
        } else {
          p1 = w1; p2 = w2;
        }
        L[i] = p1; R[i] = p2;
        if (Math.abs(p1) > pk) pk = Math.abs(p1);
        if (Math.abs(p2) > pk) pk = Math.abs(p2);
      }
      if (pk > 0) {                            // 滿刻度：整體縮到峰值 = amp
        var g = num(sig.amp, 1.0) / pk;
        for (i = 0; i < n; i++) { L[i] *= g; R[i] *= g; }
      }
    } else {
      throw new Error('unknown signal type: ' + sig.type);
    }
    return buf;
  }

  /**
   * renderOffline({ state, sampleRate, seconds, signal, preampDb })
   * 回傳 Promise<{ left, right, preampDb }>（Float32Array）
   */
  function renderOffline(opts) {
    opts = opts || {};
    var sr = num(opts.sampleRate, 96000);
    var secs = num(opts.seconds, 2);
    var n = Math.round(sr * secs);
    var OAC = global.OfflineAudioContext || global.webkitOfflineAudioContext;
    if (!OAC) return Promise.reject(new Error('no OfflineAudioContext'));
    var ctx = new OAC(2, n, sr);
    var v = assign({}, DEFAULTS, opts.state || {});
    var g = buildGraph(ctx, v);
    if (opts.preampDb !== null && opts.preampDb !== undefined) {
      g.preamp.gain.value = Math.pow(10, num(opts.preampDb, 0) / 20);
    }
    var src = ctx.createBufferSource();
    src.buffer = makeSignal(ctx, n, sr, opts.signal);
    src.connect(g.input);
    g.output.connect(ctx.destination);
    src.start(0);
    return ctx.startRendering().then(function (rendered) {
      return {
        left: rendered.getChannelData(0),
        right: rendered.getChannelData(1),
        preampDb: 20 * Math.log10(g.preamp.gain.value),
        state: v
      };
    });
  }

  function assign(t) {
    for (var i = 1; i < arguments.length; i++) {
      var s = arguments[i];
      if (!s) continue;
      for (var k in s) if (Object.prototype.hasOwnProperty.call(s, k)) t[k] = s[k];
    }
    return t;
  }

  /* =========================================================================
     8. 介面
     ========================================================================= */

  var CSS = '' +
  '.swx-root{box-sizing:border-box;width:100%;max-width:100%;font-family:system-ui,-apple-system,"Segoe UI","Microsoft JhengHei UI","Noto Sans TC",sans-serif;' +
    'font-size:14px;line-height:1.5;color:var(--swx-txt,#1d1f24);background:var(--swx-bg,#ffffff);' +
    'border:1px solid var(--swx-line,#dfe3e8);border-radius:14px;padding:14px;overflow-wrap:anywhere}' +
  '.swx-root *{box-sizing:border-box}' +
  '.swx-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;margin:0 0 8px}' +
  '.swx-title{font-size:19px;font-weight:700;color:var(--swx-accent,#ff8fb1)}' +
  '.swx-title2{font-size:12px;color:var(--swx-txt,#1d1f24)}' +
  '.swx-sub{font-size:12px;color:var(--swx-dim,#5c6472)}' +
  '.swx-note{font-size:12px;color:var(--swx-dim,#5c6472);background:var(--swx-card,#f4f5f7);' +
    'border-radius:8px;padding:8px 10px;margin:0 0 10px}' +
  '.swx-file{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 10px}' +
  '.swx-fileinput{position:absolute;width:1px;height:1px;opacity:0;overflow:hidden}' +
  '.swx-filebtn{display:inline-block;background:var(--swx-accent,#ff8fb1);color:var(--swx-accent-ink,#20131a);' +
    'border-radius:8px;padding:8px 12px;font-weight:600;cursor:pointer;max-width:100%}' +
  '.swx-filebtn:focus-within{outline:2px solid var(--swx-focus,#3b82f6);outline-offset:2px}' +
  '.swx-filename{font-size:12px;color:var(--swx-dim,#5c6472);min-width:0;overflow-wrap:anywhere}' +
  '.swx-bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 10px}' +
  '.swx-btn{border:1px solid var(--swx-line,#dfe3e8);background:var(--swx-card,#f4f5f7);color:var(--swx-txt,#1d1f24);' +
    'border-radius:8px;padding:7px 12px;font:inherit;cursor:pointer}' +
  '.swx-btn:hover{border-color:var(--swx-accent,#ff8fb1)}' +
  '.swx-btn:focus-visible{outline:2px solid var(--swx-focus,#3b82f6);outline-offset:2px}' +
  '.swx-btn[disabled]{opacity:.5;cursor:default}' +
  '.swx-play{font-weight:600;min-width:76px}' +
  '.swx-ab[aria-pressed="true"]{background:var(--swx-accent,#ff8fb1);color:var(--swx-accent-ink,#20131a);' +
    'border-color:var(--swx-accent,#ff8fb1);font-weight:700}' +
  '.swx-ab-hint{font-size:11px;color:var(--swx-dim,#5c6472)}' +
  '.swx-preamp{font-size:12px;color:var(--swx-dim,#5c6472);margin-left:auto}' +
  '.swx-presets{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:0 0 10px}' +
  '.swx-presets .swx-seg[aria-pressed="true"]{background:var(--swx-accent2,#c8842a);color:var(--swx-accent2-ink,#fff);' +
    'border-color:var(--swx-accent2,#c8842a)}' +
  '.swx-sec{margin:0 0 6px}' +
  '.swx-sec-t{font-size:12px;font-weight:700;color:var(--swx-dim,#5c6472);margin:0 0 4px}' +
  '.swx-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(232px,1fr));gap:2px 14px}' +
  '.swx-row{display:flex;align-items:center;gap:8px;min-width:0;padding:2px 0}' +
  '.swx-lbl{flex:0 0 8.6em;font-size:13px;min-width:0}' +
  '.swx-range{flex:1 1 60px;min-width:0;width:100%;accent-color:var(--swx-accent,#ff8fb1);margin:0}' +
  '.swx-val{flex:0 0 4.6em;text-align:right;font-variant-numeric:tabular-nums;font-size:12px;' +
    'color:var(--swx-accent2,#c8842a)}' +
  '.swx-checks{display:flex;flex-wrap:wrap;gap:6px 16px;margin:6px 0 10px}' +
  '.swx-check{display:flex;align-items:center;gap:6px;font-size:13px;min-width:0}' +
  '.swx-check input{accent-color:var(--swx-accent,#ff8fb1);flex:0 0 auto}' +
  '.swx-hint{font-size:11px;color:var(--swx-dim,#5c6472);margin:2px 0 0}' +
  '.swx-foot{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:10px 0 0;' +
    'padding-top:10px;border-top:1px solid var(--swx-line,#dfe3e8)}' +
  '.swx-dl{background:var(--swx-accent2,#c8842a);color:var(--swx-accent2-ink,#fff);border-color:transparent;font-weight:600}' +
  '.swx-status{font-size:12px;color:var(--swx-warn,#c0392b);margin:6px 0 0;min-height:1em}' +
  '.swx-audio{display:none}' +
  '@media (prefers-color-scheme:dark){' +
    '.swx-root{color:var(--swx-txt,#e9eaee);background:var(--swx-bg,#15161a);border-color:var(--swx-line,#2c313b)}' +
    '.swx-title2{color:var(--swx-txt,#e9eaee)}' +
    '.swx-sub,.swx-note,.swx-filename,.swx-preamp,.swx-sec-t,.swx-ab-hint,.swx-hint{color:var(--swx-dim,#98a0ad)}' +
    '.swx-note,.swx-btn{background:var(--swx-card,#1e2027);border-color:var(--swx-line,#2c313b);color:var(--swx-txt,#e9eaee)}' +
    '.swx-val{color:var(--swx-accent2,#ffc46b)}' +
    '.swx-presets .swx-seg[aria-pressed="true"]{background:var(--swx-accent2,#c8842a);color:var(--swx-accent2-ink,#201a10)}' +
    '.swx-dl{background:var(--swx-accent2,#c8842a);color:var(--swx-accent2-ink,#201a10)}' +
    '.swx-foot{border-top-color:var(--swx-line,#2c313b)}' +
  '}' +
  '@media (max-width:420px){' +
    '.swx-lbl{flex-basis:7.4em}' +
    '.swx-root{padding:11px}' +
  '}';

  function ensureStyle() {
    if (document.getElementById('swx-style')) return;
    var s = document.createElement('style');
    s.id = 'swx-style';
    s.textContent = CSS;
    (document.head || document.documentElement).appendChild(s);
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  // 各滑桿定義（範圍照桌面版）
  var SLIDERS = [
    { key: 'sweet', group: 'sec_voice', lbl: 'l_sweet', min: -2, max: 6, step: 0.5, dec: 1 },
    { key: 'mud', group: 'sec_voice', lbl: 'l_mud', min: -7, max: 0, step: 0.5, dec: 1 },
    { key: 'sib', group: 'sec_voice', lbl: 'l_sib', min: -5, max: 0, step: 0.5, dec: 1 },
    { key: 'air', group: 'sec_voice', lbl: 'l_air', min: -2, max: 4, step: 0.5, dec: 1 },
    { key: 'side', group: 'sec_side', lbl: 'l_side', min: -15, max: 0, step: 0.5, dec: 1 },
    { key: 'gain', group: 'sec_side', lbl: 'l_gain', min: -6, max: 6, step: 0.5, dec: 1 },
    { key: 'warm', group: 'sec_tube', lbl: 'l_warm', min: 0, max: 4, step: 0.5, dec: 1 },
    { key: 'tube_drive', group: 'sec_tube', lbl: 'l_drive', min: 0, max: 18, step: 3, dec: 0 }
  ];

  function mountSweetvox(mount) {
    if (!mount || mount.nodeType !== 1) return;
    if (mount.getAttribute('data-swx-mounted') === '1') return;   // 同一個 div 不要掛兩次
    ensureStyle();

    var lang = langOf(mount);
    var S = STRINGS[lang];
    var state = assign({}, DEFAULTS);
    var root = el('div', 'swx-root');
    mount.appendChild(root);

    // ---- 標題 ----
    var head = el('div', 'swx-head');
    head.appendChild(el('span', 'swx-title', S.title));
    if (S.title2) head.appendChild(el('span', 'swx-title2', S.title2));
    head.appendChild(el('span', 'swx-sub', S.sub));
    root.appendChild(head);

    root.appendChild(el('div', 'swx-note', S.note));

    var status = el('div', 'swx-status', '');
    var audio = el('audio', 'swx-audio');
    audio.controls = false;
    audio.preload = 'metadata';
    root.appendChild(audio);

    // ---- 選檔 ----
    var fileRow = el('div', 'swx-file');
    var fileLbl = el('label', 'swx-filebtn');
    var fin = document.createElement('input');
    fin.type = 'file';
    fin.className = 'swx-fileinput';
    fin.accept = 'audio/*,.mp3,.m4a,.m4a,.wav,.flac';
    fileLbl.appendChild(fin);
    fileLbl.appendChild(document.createTextNode(S.pick));
    var fname = el('span', 'swx-filename', S.nofile);
    fileRow.appendChild(fileLbl);
    fileRow.appendChild(fname);
    root.appendChild(fileRow);

    // ---- 播放／A-B ----
    var bar = el('div', 'swx-bar');
    var playBtn = el('button', 'swx-btn swx-play', S.play);
    playBtn.type = 'button';
    var abBtn = el('button', 'swx-btn swx-ab', '');
    abBtn.type = 'button';
    var abHint = el('span', 'swx-ab-hint', '');
    var preampLbl = el('span', 'swx-preamp', '');
    bar.appendChild(playBtn);
    bar.appendChild(abBtn);
    bar.appendChild(abHint);
    bar.appendChild(preampLbl);
    root.appendChild(bar);

    // ---- 預設 ----
    var psetRow = el('div', 'swx-presets');
    psetRow.appendChild(el('span', 'swx-sub', S.presets));
    var presetBtns = {};
    PRESETS.forEach(function (p) {
      var b = el('button', 'swx-btn swx-seg', p.name[lang] || p.id);
      b.type = 'button';
      b.setAttribute('aria-pressed', 'false');
      b.addEventListener('click', function () { applyPreset(p.id); });
      presetBtns[p.id] = b;
      psetRow.appendChild(b);
    });
    var resetBtn = el('button', 'swx-btn', S.reset);
    resetBtn.type = 'button';
    resetBtn.addEventListener('click', function () { resetAll(); });
    psetRow.appendChild(resetBtn);
    root.appendChild(psetRow);

    // ---- 滑桿 ----
    var grid = el('div', 'swx-grid');
    var sections = {};
    var rows = {};
    SLIDERS.forEach(function (sd) {
      if (!sections[sd.group]) {
        var sec = el('div', 'swx-sec');
        sec.appendChild(el('div', 'swx-sec-t', S[sd.group]));
        grid.appendChild(sec);
        sections[sd.group] = sec;
      }
      var row = el('label', 'swx-row');
      row.appendChild(el('span', 'swx-lbl', S[sd.lbl]));
      var r = document.createElement('input');
      r.type = 'range';
      r.className = 'swx-range';
      r.min = sd.min; r.max = sd.max; r.step = sd.step;
      r.value = state[sd.key];
      var val = el('span', 'swx-val', '');
      row.appendChild(r);
      row.appendChild(val);
      r.addEventListener('input', function () {
        state[sd.key] = roundTo(parseFloat(r.value), sd.step);
        markPreset(null);
        syncLive();
      });
      sections[sd.group].appendChild(row);
      rows[sd.key] = { input: r, val: val, def: sd };
    });
    root.appendChild(grid);

    // ---- 勾選 ----
    var checks = el('div', 'swx-checks');
    var cbCenter = checkbox(S.cb_centerbass, function (on) { state.centerbass = on; markPreset(null); syncLive(); });
    var cbTube = checkbox(S.cb_tube, function (on) { state.tube = on; syncLive(); });
    checks.appendChild(cbCenter.wrap);
    checks.appendChild(cbTube.wrap);
    root.appendChild(checks);
    var tubeHint = el('div', 'swx-hint', S.tube_hint);
    root.appendChild(tubeHint);
    root.appendChild(el('div', 'swx-hint', S.gain_hint));

    // ---- 下載 ----
    var foot = el('div', 'swx-foot');
    var dlBtn = el('button', 'swx-btn swx-dl', S.dl);
    dlBtn.type = 'button';
    var dlHint = el('span', 'swx-hint', S.dl_hint);
    foot.appendChild(dlBtn);
    foot.appendChild(dlHint);
    root.appendChild(foot);

    function checkbox(label, onchange) {
      var wrap = el('label', 'swx-check');
      var i = document.createElement('input');
      i.type = 'checkbox';
      wrap.appendChild(i);
      wrap.appendChild(document.createTextNode(label));
      i.addEventListener('change', function () { onchange(i.checked); });
      return { wrap: wrap, input: i };
    }

    function roundTo(x, step) {
      return Math.round(x / step) * step;
    }

    // --------- 即時試聽的圖 ---------
    var ctx = null, srcNode = null, g = null, dryG = null, wetG = null, outG = null, audioReady = false;

    function ensureAudio() {
      if (audioReady) return true;
      var AC = global.AudioContext || global.webkitAudioContext;
      if (!AC) { status.textContent = S.err_noaudio; return false; }
      try {
        ctx = new AC();
        srcNode = ctx.createMediaElementSource(audio);
        g = buildGraph(ctx, state);
        dryG = ctx.createGain(); wetG = ctx.createGain(); outG = ctx.createGain();
        dryG.gain.value = state.on ? 0 : 1;
        wetG.gain.value = state.on ? 1 : 0;
        srcNode.connect(g.input);
        g.output.connect(wetG);
        srcNode.connect(dryG);
        wetG.connect(outG);
        dryG.connect(outG);
        outG.connect(ctx.destination);
        audioReady = true;
        return true;
      } catch (e) {
        status.textContent = S.err_noaudio;
        return false;
      }
    }

    function syncLive() {
      if (!audioReady) { refreshLabels(); return; }
      applyState(g, state, true, ctx.currentTime);
      refreshLabels();
    }

    function applyAB(instant) {
      if (!audioReady) return;
      var now = ctx.currentTime;
      var on = !!state.on;
      if (instant) {
        dryG.gain.value = on ? 0 : 1;
        wetG.gain.value = on ? 1 : 0;
      } else {
        // 25 ms 交叉淡入淡出：不中斷播放、不爆音
        dryG.gain.setTargetAtTime(on ? 0 : 1, now, 0.008);
        wetG.gain.setTargetAtTime(on ? 1 : 0, now, 0.008);
      }
      abBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
      abBtn.textContent = on ? S.ab_on : S.ab_off;
      abHint.textContent = on ? S.ab_hint_on : S.ab_hint_off;
    }

    function markPreset(id) {
      PRESETS.forEach(function (p) {
        presetBtns[p.id].setAttribute('aria-pressed', p.id === id ? 'true' : 'false');
      });
    }

    function refreshLabels() {
      SLIDERS.forEach(function (sd) {
        var row = rows[sd.key];
        var v = num(state[sd.key], 0);
        row.val.textContent = (sd.dec === 0 ? (v > 0 ? '+' : (v < 0 ? '-' : '\u00b1')) + Math.abs(v).toFixed(0)
                                            : (v > 0 ? '+' : '') + v.toFixed(1)) + ' dB';
      });
      var p = configPreamp(state);
      preampLbl.textContent = S.preamp + p.toFixed(1) + ' dB';
    }

    function pullToUI() {
      SLIDERS.forEach(function (sd) {
        rows[sd.key].input.value = state[sd.key];
      });
      cbCenter.input.checked = !!state.centerbass;
      cbTube.input.checked = !!state.tube;
      refreshLabels();
    }

    function applyPreset(id) {
      var p = null;
      PRESETS.forEach(function (x) { if (x.id === id) p = x; });
      if (!p) return;
      assign(state, p.v);
      state.on = true;
      pullToUI();
      markPreset(id);
      syncLive();
      applyAB(false);
    }

    function resetAll() {
      assign(state, DEFAULTS);
      pullToUI();
      markPreset(null);
      syncLive();
      applyAB(false);
    }

    // --------- 事件 ---------
    fin.addEventListener('change', function () {
      var f = fin.files && fin.files[0];
      if (!f) return;
      if (audio.src && audio.src.indexOf('blob:') === 0) {
        try { URL.revokeObjectURL(audio.src); } catch (e) { /* 忽略 */ }
      }
      audio.src = URL.createObjectURL(f);
      fname.textContent = f.name;
      status.textContent = '';
      playBtn.textContent = S.play;
    });

    playBtn.addEventListener('click', function () {
      if (!audio.src) { status.textContent = S.nofile_short; return; }
      if (!ensureAudio()) return;
      if (ctx.state === 'suspended') ctx.resume();
      if (audio.paused) {
        audio.play().then(function () {
          playBtn.textContent = S.pause;
        }).catch(function () { status.textContent = S.err_load; });
      } else {
        audio.pause();
        playBtn.textContent = S.play;
      }
    });
    audio.addEventListener('play', function () { playBtn.textContent = S.pause; });
    audio.addEventListener('pause', function () { playBtn.textContent = S.play; });
    audio.addEventListener('ended', function () { playBtn.textContent = S.play; });
    audio.addEventListener('error', function () { status.textContent = S.err_load; });

    abBtn.addEventListener('click', function () {
      state.on = !state.on;
      if (audioReady) applyAB(false);
      else applyAB(true);
    });

    dlBtn.addEventListener('click', function () {
      var text = buildConfigText(state);
      var now = new Date();
      var name = 'sweetvox_' + pad2(now.getMonth() + 1) + pad2(now.getDate()) + '_' +
                 pad2(now.getHours()) + pad2(now.getMinutes()) + '.txt';
      var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = name;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      setTimeout(function () {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 1000);
    });

    // 初始化
    mount.setAttribute('data-swx-mounted', '1');
    pullToUI();
    markPreset(null);
    applyAB(true);

    // 給外部程式用的把手（驗收程式會用；一般頁面不需要）
    mount.__swx = {
      state: state,
      textFor: function () { return buildConfigText(state); },
      lang: lang
    };
    return mount.__swx;
  }

  /* =========================================================================
     9. 對外 + 自動掛載
     ========================================================================= */

  global.SweetVox = {
    version: VERSION,
    DEFAULTS: DEFAULTS,
    PRESETS: PRESETS,
    STRINGS: STRINGS,
    FS_REF: FS_REF,
    biquadCoef: biquadCoef,
    magDb: magDb,
    chainPeakDb: chainPeakDb,
    safePreamp: safePreamp,
    configPreamp: configPreamp,
    buildConfigText: buildConfigText,
    filterSpecs: filterSpecs,
    setBiquad: setBiquad,
    tubeCurve: tubeCurve,
    buildGraph: buildGraph,
    applyState: applyState,
    makeSignal: makeSignal,
    renderOffline: renderOffline
  };
  global.mountSweetvox = mountSweetvox;

  function autoMount() {
    var nodes = document.querySelectorAll('[data-lab-demo="sweetvox"]');
    for (var i = 0; i < nodes.length; i++) mountSweetvox(nodes[i]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoMount);
  } else {
    autoMount();
  }
})(typeof window !== 'undefined' ? window : this);

document.querySelectorAll('[data-lab-demo="sweetvox"]').forEach(mountSweetvox);
