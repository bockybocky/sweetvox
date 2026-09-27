#!/usr/bin/env node
/**
 * 甜嗓 SweetVox 網頁版 — 驗收程式（V1～V7）
 *
 * 用法：  node test_sweetvox.mjs            （會自己叫 Python 產生參考值、自己開無頭 Chrome）
 *
 * 不需要 npm 安裝任何東西：用的是 Node 內建的 WebSocket / fetch 直接跟 Chrome 的 DevTools Protocol 講話。
 *
 *   V1 四個預設 MID 鏈頻率響應（真的 BiquadFilterNode.getFrequencyResponse，fs=96 kHz）
 *      ⨯ Python 桌面版 _biquad/_mag_db
 *   V2 四個預設 Preamp ⨯ Python safe_preamp()（vst_air=False）
 *   V3 「下載設定檔」的文字 ⨯ Python build_config()（去掉時間戳那行）
 *   V4 「中」預設：純正中 3 kHz 正弦 vs 純兩側 3 kHz 正弦的增益差
 *   V5 四個預設 × 滿刻度粉紅雜訊 10 秒：峰值 ≤ -0.5 dBFS
 *   V6 全部濾波 0、tube 關、Preamp 0：輸出＝輸入（< 1e-6）
 *   V7 無頭 Chrome 開 demo.html：淺色／深色 × 寬 360／1200 截圖、無橫向捲軸、無主控台錯誤
 */
import { spawn, spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHOT_DIR = path.join(HERE, 'shots');
const RESULT_JSON = path.join(HERE, 'test_results.json');
const PY_REF = path.join(HERE, 'python_reference.json');
const CHROME_CANDIDATES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.CHROME_PATH || '',
].filter(Boolean);

const log = (...a) => console.log(...a);
const fmt = (x, d = 3) => (x === null || x === undefined || Number.isNaN(x) ? String(x) : Number(x).toFixed(d));

/* ============================ 1. Python 參考值 ============================ */

function buildPythonReference() {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = spawnSync(py, [path.join(HERE, 'make_python_reference.py'), PY_REF], {
    cwd: HERE, encoding: 'utf8',
  });
  if (r.status !== 0) throw new Error('make_python_reference.py 失敗：' + (r.stderr || r.stdout));
  log(r.stdout.trim());
  return JSON.parse(fs.readFileSync(PY_REF, 'utf8'));
}

/* ============================ 2. 無頭 Chrome + CDP ============================ */

class CDP {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.pending = new Map();
    this.listeners = [];
    this.ready = new Promise((res, rej) => {
      this.ws.addEventListener('open', () => res());
      this.ws.addEventListener('error', (e) => rej(new Error('CDP ws error: ' + (e.message || e.type))));
    });
    this.ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
      } else if (msg.method) {
        this.listeners.forEach((f) => f(msg));
      }
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  on(fn) { this.listeners.push(fn); }
}

async function freePort() {
  const net = await import('node:net');
  return new Promise((res) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const p = srv.address().port;
      srv.close(() => res(p));
    });
  });
}

async function startChrome() {
  const chrome = CHROME_CANDIDATES.find((p) => fs.existsSync(p));
  if (!chrome) throw new Error('找不到 Chrome，試過：' + CHROME_CANDIDATES.join(' | '));
  const port = await freePort();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'swx-chrome-'));
  const args = [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--mute-audio', '--allow-file-access-from-files',
    '--autoplay-policy=no-user-gesture-required', '--window-size=1200,900',
    `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, 'about:blank',
  ];
  const proc = spawn(chrome, args, { stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  proc.stderr.on('data', (d) => { stderr += d.toString(); });

  const base = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 30000;
  let info = null;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(base + '/json/version');
      if (r.ok) { info = await r.json(); break; }
    } catch { /* 還沒起來 */ }
    await new Promise((r) => setTimeout(r, 250));
  }
  if (!info) { proc.kill(); throw new Error('Chrome 沒起來：' + stderr.slice(-500)); }

  let targets = [];
  for (let i = 0; i < 40; i++) {
    targets = await (await fetch(base + '/json/list')).json();
    if (targets.some((t) => t.type === 'page')) break;
    await new Promise((r) => setTimeout(r, 250));
  }
  const page = targets.find((t) => t.type === 'page');
  if (!page) { proc.kill(); throw new Error('Chrome 沒有 page target'); }
  log(`Chrome ${info.Browser}  headless，遠端除錯埠 ${port}`);
  return { proc, cdp: new CDP(page.webSocketDebuggerUrl), profile, base };
}

/* ============================ 3. 頁面裡要跑的測試（大字串） ============================ */

function pageTestScript(freqs, presetsFromPy) {
  return `(async () => {
  const SV = window.SweetVox;
  const FREQS = ${JSON.stringify(freqs)};
  const PRESET_NAMES = ${JSON.stringify(presetsFromPy)};
  const n = FREQS.length;
  const freqs = Float32Array.from(FREQS);
  const octx = new OfflineAudioContext(2, 1024, 96000);
  const out = { version: SV.version, errors: [], v1: {}, v2: {}, v4: {}, v5: {}, v6: {}, thd: {}, v3: {} };

  function stateOf(presetName) {
    const s = Object.assign({}, SV.DEFAULTS);
    if (presetName === 'DEFAULTS') return s;
    const p = SV.PRESETS.find((x) => x.id === presetName);
    Object.assign(s, p.v);
    return s;
  }

  // ---- V1：MID 鏈的頻率響應（用真的 BiquadFilterNode 算） ----
  function respDb(specs) {
    const acc = new Float64Array(n);
    for (const s of specs) {
      const bq = octx.createBiquadFilter();
      SV.setBiquad(bq, s);          // 用 sweetvox.js 自己的設定（含高通 Q 換算），不是測試自己另外設
      const m = new Float32Array(n), ph = new Float32Array(n);
      bq.getFrequencyResponse(freqs, m, ph);
      for (let i = 0; i < n; i++) acc[i] += 20 * Math.log10(m[i]);
    }
    return Array.from(acc);
  }
  for (const name of PRESET_NAMES) {
    const st = stateOf(name);
    const sp = SV.filterSpecs(st);
    out.v1[name] = { mid_spec: sp.mid, side_spec: sp.side, mid_db: respDb(sp.mid), side_db: respDb(sp.side) };
    // V2
    out.v2[name] = { safe_preamp: SV.safePreamp(st), config_preamp: SV.configPreamp(st) };
    // V3
    out.v3[name] = SV.buildConfigText(st, new Date(2000, 0, 1, 12, 0, 0));
  }

  // ---- 直流／基頻量測 ----
  function fundamental(x, sr, f, from, to) {
    const a = from === undefined ? 0 : from, b = to === undefined ? x.length : to;
    let re = 0, im = 0;
    for (let i = a; i < b; i++) {
      const w = 2 * Math.PI * f * i / sr;
      re += x[i] * Math.cos(w); im += x[i] * Math.sin(w);
    }
    return 2 * Math.hypot(re, im) / (b - a);
  }
  function rms(x, from, to) {
    const a = from || 0, b = to === undefined ? x.length : to;
    let s = 0;
    for (let i = a; i < b; i++) s += x[i] * x[i];
    return Math.sqrt(s / (b - a));
  }
  function peakDb(x) {
    let p = 0;
    for (let i = 0; i < x.length; i++) { const a = Math.abs(x[i]); if (a > p) p = a; }
    return 20 * Math.log10(p);
  }
  function thdOf(x, sr, f, maxH) {
    const h1 = fundamental(x, sr, f);
    let s = 0;
    for (let h = 2; h <= (maxH || 20); h++) { const m = fundamental(x, sr, f * h); s += m * m; }
    return { thd: 100 * Math.sqrt(s) / h1, h1: h1 };
  }

  // ---- V4：「中」預設，純正中 vs 純兩側 3 kHz 正弦 ----
  const stMid = stateOf('中');
  const AMP = 0.25;
  for (const mode of ['mid', 'side']) {
    const r = await SV.renderOffline({ state: stMid, sampleRate: 96000, seconds: 1,
      signal: { type: 'sine', freq: 3000, amp: AMP, mode: mode } });
    const L = r.left;
    const skip = 4800;                       // 前面 50 ms 當暖機，不計
    const f0 = fundamental(L, 96000, 3000, skip, L.length);
    out.v4[mode] = { fund_db: 20 * Math.log10(f0 / AMP), rms_db: 20 * Math.log10(rms(L, skip, L.length) / (AMP / Math.SQRT2)),
                     preamp_db: r.preampDb };
  }
  out.v4.diff_db = out.v4.mid.fund_db - out.v4.side.fund_db;

  // ---- V5：四個預設 × 滿刻度粉紅雜訊 10 秒 ----
  for (const name of PRESET_NAMES) {
    const st = stateOf(name);
    const r = await SV.renderOffline({ state: st, sampleRate: 96000, seconds: 10,
      signal: { type: 'pink', amp: 1.0, seed: 20260923 } });
    out.v5[name] = { peak_left_db: peakDb(r.left), peak_right_db: peakDb(r.right), preamp_db: r.preampDb };
  }

  // ---- V6：全部濾波 0、tube 關、Preamp 0 → 輸出＝輸入 ----
  const zero = Object.assign({}, SV.DEFAULTS, {
    subcut: 0, warm: 0, mud: 0, sweet: 0, sib: 0, air: 0, side: 0, side_pk_db: 0,
    centerbass: false, tube: false, tube_drive: 0, gain: 0
  });
  {
    const sr = 96000, secs = 1, len = sr * secs;
    const r = await SV.renderOffline({ state: zero, sampleRate: sr, seconds: secs, preampDb: 0,
      signal: { type: 'pink', amp: 0.9, seed: 4242 } });
    const c2 = new OfflineAudioContext(2, len, sr);
    const buf = SV.makeSignal(c2, len, sr, { type: 'pink', amp: 0.9, seed: 4242 });
    const inL = buf.getChannelData(0), inR = buf.getChannelData(1);
    let maxL = 0, maxR = 0, atL = -1, atR = -1;
    for (let i = 0; i < len; i++) {
      const dl = Math.abs(r.left[i] - inL[i]); if (dl > maxL) { maxL = dl; atL = i; }
      const dr = Math.abs(r.right[i] - inR[i]); if (dr > maxR) { maxR = dr; atR = i; }
    }
    out.v6 = { max_err_left: maxL, at_left: atL, max_err_right: maxR, at_right: atR,
               preamp_db: r.preampDb };
  }

  // ---- 附加：真空管推力掃描（1 kHz、-12 dBFS、純 MID 鏈，Preamp 0）----
  {
    const amp = Math.pow(10, -12 / 20);
    const rows = [];
    for (const drive of [0, 3, 6, 9, 12, 18]) {
      const st = Object.assign({}, SV.DEFAULTS, { tube: true, tube_drive: drive, vst_air: false });
      const r = await SV.renderOffline({ state: st, sampleRate: 96000, seconds: 1, preampDb: 0,
        signal: { type: 'sine', freq: 1000, amp: amp, mode: 'mid' } });
      const t = thdOf(r.left, 96000, 1000, 20);
      // 偶次／奇次
      let odd = 0, even = 0;
      for (let h = 2; h <= 20; h++) {
        const m = fundamental(r.left, 96000, 1000 * h);
        if (h % 2 === 0) even += m * m; else odd += m * m;
      }
      rows.push({ drive_db: drive, thd_pct: t.thd, fund: t.h1,
                  even_minus_odd_db: 20 * Math.log10(Math.sqrt(even) / Math.sqrt(odd)),
                  peak_db: peakDb(r.left) });
    }
    out.thd_sweep = rows;
  }

  // ---- 附加：實際播放的取樣率（通常 48 kHz）跟驗算用的 96 kHz 差多少 ----
  {
    const octx48 = new OfflineAudioContext(2, 1024, 48000);
    const diffs = {};
    for (const name of PRESET_NAMES) {
      const st = stateOf(name);
      const sp = SV.filterSpecs(st);
      const acc = new Float64Array(n);
      for (const s of sp.mid) {
        const bq = octx48.createBiquadFilter();
        SV.setBiquad(bq, s);
        const m = new Float32Array(n), ph = new Float32Array(n);
        bq.getFrequencyResponse(freqs, m, ph);
        for (let i = 0; i < n; i++) acc[i] += 20 * Math.log10(m[i]);
      }
      let worst = 0, at = 0;
      for (let i = 0; i < n; i++) {
        const d = Math.abs(acc[i] - out.v1[name].mid_db[i]);
        if (d > worst) { worst = d; at = i; }
      }
      diffs[name] = { max_diff_db: worst, at_hz: FREQS[at] };
    }
    out.rate_diff = diffs;
  }

  // ---- 附加：真空管推力 6 dB 的 THD（-12 dBFS、1 kHz 正弦） ----
  {
    const amp = Math.pow(10, -12 / 20);
    const tubeOn = Object.assign({}, SV.DEFAULTS, { tube: true, tube_drive: 6, vst_air: false });
    const tubeOff = Object.assign({}, SV.DEFAULTS, { tube: false, tube_drive: 0, vst_air: false });
    const rOn = await SV.renderOffline({ state: tubeOn, sampleRate: 96000, seconds: 1, preampDb: 0,
      signal: { type: 'sine', freq: 1000, amp: amp, mode: 'mid' } });
    const rOff = await SV.renderOffline({ state: tubeOff, sampleRate: 96000, seconds: 1, preampDb: 0,
      signal: { type: 'sine', freq: 1000, amp: amp, mode: 'mid' } });
    const t1 = thdOf(rOn.left, 96000, 1000, 20);
    const t2 = thdOf(rOff.left, 96000, 1000, 20);
    out.thd = { tube_on_drive6_thd_pct: t1.thd, tube_on_fund: t1.h1,
                tube_off_thd_pct: t2.thd, tube_off_fund: t2.h1,
                peak_tube_on_db: peakDb(rOn.left) };
  }

  out.download_text = {};
  return out;
})()`;
}

/* ============================ 4. 主流程 ============================ */

function compareArrays(jsArr, pyArr) {
  let max = 0, at = 0;
  for (let i = 0; i < pyArr.length; i++) {
    const d = Math.abs(jsArr[i] - pyArr[i]);
    if (d > max) { max = d; at = i; }
  }
  return { max, at };
}

function stripTimestamp(text) {
  return text.split('\n').filter((l) => !/調整台寫入/.test(l)).join('\n');
}

async function main() {
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  const py = buildPythonReference();
  const presetNames = Object.keys(py.presets).concat(['DEFAULTS']);
  const results = { started: new Date().toISOString(), checks: {}, desktop_md5: py.desktop_md5 };
  results.artifacts = {
    'sweetvox.js': md5file(path.join(HERE, 'sweetvox.js')),
    'demo.html': md5file(path.join(HERE, 'demo.html')),
    'test_sweetvox.mjs': md5file(path.join(HERE, 'test_sweetvox.mjs')),
    'desktop app/vocal_focus_gui.py': py.desktop_md5,
  };
  log('這輪驗的檔案 md5：' + JSON.stringify(results.artifacts));

  const { proc, cdp, profile } = await startChrome();
  const consoleErrors = [];
  let pageResult = null;
  let uiStructure = null;
  try {
    await cdp.ready;
    cdp.on((msg) => {
      if (msg.method === 'Runtime.exceptionThrown') {
        consoleErrors.push('exception: ' + (msg.params.exceptionDetails.exception?.description ||
          msg.params.exceptionDetails.text));
      }
      if (msg.method === 'Runtime.consoleAPICalled' && (msg.params.type === 'error' || msg.params.type === 'warning')) {
        consoleErrors.push(msg.params.type + ': ' + msg.params.args.map((a) => a.value ?? a.description).join(' '));
      }
      if (msg.method === 'Log.entryAdded' && msg.params.entry.level === 'error') {
        consoleErrors.push('log: ' + msg.params.entry.text + ' @ ' + msg.params.entry.url);
      }
    });
    await cdp.send('Runtime.enable');
    await cdp.send('Page.enable');
    await cdp.send('Log.enable');

    const url = 'file:///' + path.join(HERE, 'demo.html').replace(/\\/g, '/');
    log('開檔：' + url);
    await cdp.send('Page.navigate', { url });
    await new Promise((r) => setTimeout(r, 1200));

    const evaluate = async (expression, awaitPromise = false) => {
      const r = await cdp.send('Runtime.evaluate', {
        expression, awaitPromise, returnByValue: true, timeout: 180000, userGesture: true,
      });
      if (r.exceptionDetails) {
        throw new Error('頁面裡丟出例外：' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
      }
      return r.result.value;
    };

    // --- 先確認 sweetvox.js 真的掛上去了 ---
    const mounted = await evaluate(`document.querySelectorAll('[data-lab-demo="sweetvox"]').length`);
    const hasApi = await evaluate(`typeof window.SweetVox === 'object' && typeof window.mountSweetvox === 'function'`);
    results.checks.mount = { mounts: mounted, api: hasApi };
    log(`頁面上掛了 ${mounted} 個，SweetVox API：${hasApi}`);

    // --- V1／V2／V4／V5／V6 在頁面裡跑 ---
    pageResult = await evaluate(pageTestScript(py.freqs, presetNames), true);
    results.page = { version: pageResult.version };

    // --- V3：真的按「下載設定檔」，把 Blob 攔下來讀文字 ---
    const downloadText = await evaluate(`(async () => {
      const captured = [];
      const orig = URL.createObjectURL;
      URL.createObjectURL = function (b) { captured.push(b); return orig.call(URL, b); };
      const btn = document.querySelector('.swx-dl');
      if (!btn) { URL.createObjectURL = orig; return { error: '找不到下載鈕' }; }
      btn.click();
      await new Promise((r) => setTimeout(r, 60));
      URL.createObjectURL = orig;
      if (!captured.length) return { error: '沒有建立 Blob' };
      return { text: await captured[0].text(), type: captured[0].type, size: captured[0].size };
    })()`, true);
    results.download = { type: downloadText.type, size: downloadText.size, error: downloadText.error };
    if (downloadText.text) pageResult.v3['__download__'] = downloadText.text;

    // --- V7：介面完整性 + 截圖（淺／深 × 360／1200） ---
    uiStructure = await evaluate(`(() => {
      const q = (s) => document.querySelectorAll(s).length;
      const note = document.querySelector('.swx-note');
      return {
        file_inputs: q('.swx-fileinput'), play: q('.swx-play'), ab: q('.swx-ab'),
        sliders: q('.swx-range'), slider_labels: Array.from(document.querySelectorAll('.swx-range'))
          .filter((r) => r.closest('label')).length,
        values_shown: q('.swx-val'), checks: q('.swx-check input[type=checkbox]'),
        presets: q('.swx-seg'), reset: q('.swx-btn'), dl: q('.swx-dl'),
        aria_pressed: document.querySelector('.swx-ab').getAttribute('aria-pressed'),
        note_text: note ? note.textContent : null,
        lang: document.querySelector('[data-lab-demo="sweetvox"]').dataset.lang,
        styles: document.querySelectorAll('#swx-style').length
      };
    })()`);
    results.ui = uiStructure;
    log('介面：滑桿 ' + uiStructure.sliders + '、預設 ' + uiStructure.presets + '、勾選 ' + uiStructure.checks +
        '、樣式表 ' + uiStructure.styles + ' 份');

    // 重複 mount 不重複插 style
    const styleDup = await evaluate(`(() => {
      const d = document.createElement('div');
      d.setAttribute('data-lab-demo', 'sweetvox');
      document.body.appendChild(d);
      window.mountSweetvox(d);
      const c = document.querySelectorAll('#swx-style').length;
      const inner = d.querySelectorAll('.swx-root').length;
      d.remove();
      return { styles_after: c, roots_in_new_mount: inner };
    })()`);
    results.checks.style_once = { styles_after: styleDup.styles_after, roots: styleDup.roots_in_new_mount };

    const shots = [];
    for (const scheme of ['light', 'dark']) {
      for (const width of [360, 1200]) {
        await cdp.send('Emulation.setDeviceMetricsOverride', {
          width, height: 900, deviceScaleFactor: 1, mobile: width <= 420,
        });
        await cdp.send('Emulation.setEmulatedMedia', {
          media: 'screen', features: [{ name: 'prefers-color-scheme', value: scheme }],
        });
        await new Promise((r) => setTimeout(r, 350));
        const layout = await evaluate(`(() => {
          const doc = document.documentElement;
          const wide = [];
          document.querySelectorAll('.swx-root, .swx-root *').forEach((e) => {
            const r = e.getBoundingClientRect();
            if (r.right > window.innerWidth + 0.5 || r.left < -0.5) {
              wide.push(e.className + ':' + Math.round(r.left) + '~' + Math.round(r.right));
            }
          });
          return {
            inner_width: window.innerWidth,
            doc_scroll_width: doc.scrollWidth,
            body_scroll_width: document.body.scrollWidth,
            root_scroll_width: document.querySelector('.swx-root').scrollWidth,
            root_client_width: document.querySelector('.swx-root').clientWidth,
            overflowing: wide.slice(0, 6),
            has_h_scroll: doc.scrollWidth > window.innerWidth || document.body.scrollWidth > window.innerWidth
          };
        })()`);
        const shot = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
        const file = path.join(SHOT_DIR, `demo_${scheme}_${width}.png`);
        fs.writeFileSync(file, Buffer.from(shot.data, 'base64'));
        const st = fs.statSync(file);
        shots.push({ scheme, width, file, bytes: st.size, ...layout });
        log(`  截圖 ${scheme} ${width}px → ${path.basename(file)}（${st.size} bytes，橫向捲軸：${layout.has_h_scroll}）`);
      }
    }
    results.shots = shots;
    await cdp.send('Emulation.clearDeviceMetricsOverride');

    // --- 附加：A/B 切換不中斷播放（真的載一段自己產生的測試音進去看播放位置有沒有倒退）---
    const abTest = await evaluate(`(async () => {
      const mount = document.querySelector('[data-lab-demo="sweetvox"]');
      const input = mount.querySelector('.swx-fileinput');
      const playBtn = mount.querySelector('.swx-play');
      const abBtn = mount.querySelector('.swx-ab');
      const audio = mount.querySelector('audio');
      const sr = 48000, secs = 6, len = sr * secs;
      const ab = new ArrayBuffer(44 + len * 2), dv = new DataView(ab);
      const ws = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
      ws(0, 'RIFF'); dv.setUint32(4, 36 + len * 2, true); ws(8, 'WAVE');
      ws(12, 'fmt '); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
      dv.setUint32(24, sr, true); dv.setUint32(28, sr * 2, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true);
      ws(36, 'data'); dv.setUint32(40, len * 2, true);
      for (let i = 0; i < len; i++) dv.setInt16(44 + i * 2, Math.round(12000 * Math.sin(2 * Math.PI * 440 * i / sr)), true);
      const dt = new DataTransfer();
      dt.items.add(new File([ab], 'swx-test-tone.wav', { type: 'audio/wav' }));
      input.files = dt.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      playBtn.click();
      await new Promise((r) => setTimeout(r, 1200));
      const ct1 = audio.currentTime, paused1 = audio.paused;
      const pressed1 = abBtn.getAttribute('aria-pressed');
      abBtn.click();
      await new Promise((r) => setTimeout(r, 600));
      const ct2 = audio.currentTime, paused2 = audio.paused, pressed2 = abBtn.getAttribute('aria-pressed');
      abBtn.click();
      await new Promise((r) => setTimeout(r, 600));
      const ct3 = audio.currentTime, paused3 = audio.paused, pressed3 = abBtn.getAttribute('aria-pressed');
      const out = {
        filename_shown: mount.querySelector('.swx-filename').textContent,
        played: !paused1, ct1: ct1, paused2: paused2, ct2: ct2, pressed2: pressed2,
        paused3: paused3, ct3: ct3, pressed3: pressed3,
        advanced: ct2 > ct1 && ct3 > ct2,
        never_paused: !paused1 && !paused2 && !paused3,
        ab_text_after: abBtn.textContent
      };
      audio.pause();
      return out;
    })()`, true);
    results.ab = abTest;
    log(`A/B：載入測試音後播放中=${abTest.played}、切換前後播放位置 ${abTest.ct1.toFixed(3)} → ${abTest.ct2.toFixed(3)} → ${abTest.ct3.toFixed(3)}，中途沒暫停=${abTest.never_paused}`);

    // --- 附加：按介面上的預設鈕，看 widget 狀態與下載文字是不是就是驗過的那一組 ---
    const presetCheck = await evaluate(`(() => {
      const mount = document.querySelector('[data-lab-demo="sweetvox"]');
      const sv = mount.__swx;
      const btns = Array.from(mount.querySelectorAll('.swx-seg'));
      const out = [];
      for (const p of window.SweetVox.PRESETS) {
        const b = btns.find((x) => x.textContent === p.name['zh-TW']);
        if (!b) { out.push({ id: p.id, found: false }); continue; }
        b.click();
        const st = sv.state;
        const diffKeys = Object.keys(p.v).filter((k) => st[k] !== p.v[k]);
        out.push({ id: p.id, found: true, matched: diffKeys.length === 0, diff_keys: diffKeys,
                   on: st.on, aria: b.getAttribute('aria-pressed'),
                   text: sv.textFor(),
                   slider_sweet: mount.querySelectorAll('.swx-range')[0].value,
                   shown_values: Array.from(mount.querySelectorAll('.swx-val')).map((e) => e.textContent) });
      }
      return out;
    })()`);
    results.preset_click = presetCheck;
  } finally {
    try { proc.kill(); } catch { }
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch { }
  }

  results.console_errors = consoleErrors;

  /* ---------------- 判定 ---------------- */
  const V = {};

  // V1
  let v1worstPeak = { diff: 0, name: null, f: null };
  let v1worstShelf = { diff: 0, name: null, f: null };
  let v1worstAll = { diff: 0, name: null, f: null };
  const v1rows = [];
  for (const name of Object.keys(py.presets)) {
    const js = pageResult.v1[name].mid_db, pyd = py.presets[name].mid_db;
    const shelfPart = py.presets[name].shelf_part_db;
    for (let i = 0; i < pyd.length; i++) {
      const d = Math.abs(js[i] - pyd[i]);
      const f = py.freqs[i];
      if (d > v1worstAll.diff) v1worstAll = { diff: d, name, f };
      if (Math.abs(shelfPart[i]) >= 0.10) {
        if (d > v1worstShelf.diff) v1worstShelf = { diff: d, name, f };
      } else if (d > v1worstPeak.diff) v1worstPeak = { diff: d, name, f };
    }
    const r = compareArrays(js, pyd);
    v1rows.push({ preset: name, max_diff_db: r.max, at_hz: py.freqs[r.at] });
  }
  V.V1 = {
    pass: v1worstPeak.diff <= 0.1 && v1worstShelf.diff <= 0.8,
    peak_segment_max_db: v1worstPeak, shelf_segment_max_db: v1worstShelf, overall_max_db: v1worstAll,
    per_preset: v1rows, points: py.freqs.length, sample_rate: 96000,
  };

  // V2
  const v2rows = [];
  let v2max = 0;
  for (const name of Object.keys(py.presets)) {
    const js = pageResult.v2[name].safe_preamp, pys = py.presets[name].safe_preamp;
    const d = Math.abs(js - pys);
    if (d > v2max) v2max = d;
    const cfgLine = pageResult.v3[name].split('\n').filter((l) => /^Preamp:/.test(l))[0];
    v2rows.push({ preset: name, js_safe_preamp_db: js, py_safe_preamp_db: pys, diff_db: d,
                  js_config_preamp_db: pageResult.v2[name].config_preamp,
                  py_config_preamp_db: py.presets[name].config_preamp, config_line: cfgLine });
  }
  V.V2 = { pass: v2max <= 0.05, max_diff_db: v2max, rows: v2rows };

  // V3
  const v3rows = [];
  let v3all = true;
  for (const name of Object.keys(py.presets)) {
    const jsText = stripTimestamp(pageResult.v3[name]);
    const pyText = stripTimestamp(py.presets[name].config_text);
    const same = jsText === pyText;
    let firstDiff = null;
    if (!same) {
      const a = jsText.split('\n'), b = pyText.split('\n');
      for (let i = 0; i < Math.max(a.length, b.length); i++) {
        if (a[i] !== b[i]) { firstDiff = { line: i + 1, js: a[i], py: b[i] }; break; }
      }
    }
    v3all = v3all && same;
    v3rows.push({ preset: name, identical: same, lines: pyText.split('\n').length, first_diff: firstDiff,
                  md5_js: md5(jsText), md5_py: md5(pyText) });
  }
  {
    const dl = pageResult.v3['__download__'];
    const jsText = stripTimestamp(dl || '');
    // 試用頁剛載入時是 DEFAULTS 狀態（跟桌面版一樣），所以下載鈕那份要跟 DEFAULTS 的設定檔比
    const pyText = stripTimestamp(py.configs['DEFAULTS'].config_text);
    const dlSame = jsText === pyText;
    v3rows.push({ preset: '下載鈕(Blob)', identical: dlSame, lines: jsText.split('\n').length });

    // 按介面上的預設鈕之後，widget 狀態與下載文字是不是就是驗過的那一組
    let presetStateOk = true;
    for (const r of (results.preset_click || [])) {
      if (!r.found) { presetStateOk = false; continue; }
      const t = stripTimestamp(r.text || '');
      const p = stripTimestamp(py.presets[r.id].config_text);
      const same = t === p;
      if (!same || !r.matched) presetStateOk = false;
      v3all = v3all && same;
      v3rows.push({ preset: 'UI 按「' + r.id + '」', identical: same, state_matched: r.matched,
                    lines: t.split('\n').length });
    }
    V.V3 = { pass: v3all && dlSame && presetStateOk, rows: v3rows, download_blob_bytes: results.download.size,
             download_blob_type: results.download.type };
  }

  // V4
  const v4 = pageResult.v4;
  V.V4 = {
    pass: v4.diff_db >= 3, preset: '中', freq_hz: 3000,
    mid_fund_db: v4.mid.fund_db, side_fund_db: v4.side.fund_db, diff_db: v4.diff_db,
    mid_rms_db: v4.mid.rms_db, side_rms_db: v4.side.rms_db, preamp_db: v4.mid.preamp_db,
  };

  // V5
  const v5rows = [];
  let v5worst = -999;
  for (const name of Object.keys(py.presets)) {
    const p = pageResult.v5[name];
    const worst = Math.max(p.peak_left_db, p.peak_right_db);
    if (worst > v5worst) v5worst = worst;
    v5rows.push({ preset: name, peak_left_db: p.peak_left_db, peak_right_db: p.peak_right_db, preamp_db: p.preamp_db });
  }
  V.V5 = { pass: v5worst <= -0.5, worst_peak_db: v5worst, rows: v5rows, noise: '滿刻度粉紅雜訊 10 秒、fs=96 kHz' };

  // V6
  const v6 = pageResult.v6;
  V.V6 = { pass: Math.max(v6.max_err_left, v6.max_err_right) < 1e-6, ...v6 };

  // V7
  const badShot = (results.shots || []).find((s) => s.has_h_scroll || s.bytes < 5000 || s.overflowing.length > 0);
  V.V7 = {
    pass: !badShot && consoleErrors.length === 0 &&
          uiStructure.sliders === 8 && uiStructure.presets === 4 && uiStructure.checks === 2 &&
          uiStructure.file_inputs === 1 && uiStructure.play === 1 && uiStructure.ab === 1 && uiStructure.dl === 1 &&
          uiStructure.styles === 1 && results.checks.style_once.styles_after === 1,
    shots: (results.shots || []).map((s) => ({ scheme: s.scheme, width: s.width, file: path.basename(s.file),
      bytes: s.bytes, has_h_scroll: s.has_h_scroll, doc_scroll_width: s.doc_scroll_width,
      root_scroll_width: s.root_scroll_width, root_client_width: s.root_client_width, overflowing: s.overflowing })),
    console_errors: consoleErrors,
    ui: uiStructure,
  };

  // 附加：真空管 THD
  V.THD = { ...pageResult.thd, spec: '1 kHz 正弦、-12 dBFS 入力、推力 6 dB；規格要求 1%～3%',
            pass: pageResult.thd.tube_on_drive6_thd_pct >= 1 && pageResult.thd.tube_on_drive6_thd_pct <= 3,
            sweep: pageResult.thd_sweep };

  // 附加：A/B 切換不中斷播放
  const ab = results.ab || {};
  V.AB = {
    pass: ab.never_paused === true && ab.advanced === true,
    undecidable: ab.played !== true,
    detail: ab,
  };

  // 附加：實際取樣率（48 kHz）與驗算基準（96 kHz）的差
  V.RATE = { rows: pageResult.rate_diff };

  results.checks = { ...results.checks, V1: V.V1, V2: V.V2, V3: V.V3, V4: V.V4, V5: V.V5, V6: V.V6, V7: V.V7,
                     THD: V.THD, AB: V.AB, RATE: V.RATE };
  results.finished = new Date().toISOString();
  fs.writeFileSync(RESULT_JSON, JSON.stringify(results, null, 2), 'utf8');

  /* ---------------- 印出來 ---------------- */
  console.log('\n================ 驗收結果 ================');
  const verdict = (b) => (b === true ? '通過' : b === false ? '失敗' : '無法判定');
  console.log(`V1 MID 鏈頻率響應      ${verdict(V.V1.pass)}  峰值段最大差 ${fmt(V.V1.peak_segment_max_db.diff)} dB`
    + `（${V.V1.peak_segment_max_db.name} @ ${fmt(V.V1.peak_segment_max_db.f, 1)} Hz）`
    + ` / 架式段最大差 ${fmt(V.V1.shelf_segment_max_db.diff)} dB（${V.V1.shelf_segment_max_db.name} @ ${fmt(V.V1.shelf_segment_max_db.f, 1)} Hz）`);
  console.log(`   全部點最大差 ${fmt(V.V1.overall_max_db.diff)} dB（${V.V1.overall_max_db.name} @ ${fmt(V.V1.overall_max_db.f, 1)} Hz），`
    + `共 ${V.V1.points} 點 × 4 預設`);
  console.log(`V2 Preamp              ${verdict(V.V2.pass)}  最大差 ${fmt(V.V2.max_diff_db, 4)} dB`);
  V.V2.rows.forEach((r) => console.log(`   ${r.preset}: JS ${fmt(r.js_safe_preamp_db)} / Python ${fmt(r.py_safe_preamp_db)} dB｜設定檔那行「${r.config_line}」`));
  console.log(`V3 設定檔逐行比對      ${verdict(V.V3.pass)}`);
  V.V3.rows.forEach((r) => console.log(`   ${r.preset}: ${r.identical ? '完全相同' : '不同 → ' + JSON.stringify(r.first_diff)}（${r.lines} 行）`));
  console.log(`V4 正中 vs 兩側 3 kHz  ${verdict(V.V4.pass)}  正中 ${fmt(V.V4.mid_fund_db, 2)} dB、兩側 ${fmt(V.V4.side_fund_db, 2)} dB，差 ${fmt(V.V4.diff_db, 2)} dB`);
  console.log(`V5 粉紅雜訊峰值        ${verdict(V.V5.pass)}  最差 ${fmt(V.V5.worst_peak_db, 2)} dBFS`);
  V.V5.rows.forEach((r) => console.log(`   ${r.preset}: L ${fmt(r.peak_left_db, 2)} / R ${fmt(r.peak_right_db, 2)} dBFS（Preamp ${fmt(r.preamp_db, 2)} dB）`));
  console.log(`V6 全 0 時輸出＝輸入   ${verdict(V.V6.pass)}  最大誤差 L ${V.V6.max_err_left.toExponential(3)} / R ${V.V6.max_err_right.toExponential(3)}`);
  console.log(`V7 無頭 Chrome 介面    ${verdict(V.V7.pass)}  截圖 ${V.V7.shots.length} 張、主控台錯誤 ${consoleErrors.length} 筆`);
  V.V7.shots.forEach((s) => console.log(`   ${s.scheme} ${s.width}px: ${s.file}（${s.bytes} bytes）捲軸寬 ${s.doc_scroll_width} / 視窗 ${s.width} 橫向捲軸=${s.has_h_scroll}`));
  if (consoleErrors.length) consoleErrors.forEach((e) => console.log('   ! ' + e));
  console.log(`THD（附加）            ${verdict(V.THD.pass)}  推力 6 dB、-12 dBFS：${fmt(V.THD.tube_on_drive6_thd_pct, 2)}%（推力關掉時 ${fmt(V.THD.tube_off_thd_pct, 4)}%）`);
  console.log('   推力掃描（網頁 WaveShaper vs 桌面版 PurestWarm 實測表）');
  V.THD.sweep.forEach((r) => console.log(`     推力 ${String(r.drive_db).padStart(2)} dB: THD ${fmt(r.thd_pct, 2)}%  偶-奇 ${fmt(r.even_minus_odd_db, 1)} dB`));
  console.log(`A/B 切換（附加）       ${V.AB.undecidable ? '無法判定（無頭沒有音訊裝置）' : verdict(V.AB.pass)}`
    + `  播放中 ${V.AB.detail.played}、位置 ${fmt(V.AB.detail.ct1, 3)} → ${fmt(V.AB.detail.ct2, 3)} → ${fmt(V.AB.detail.ct3, 3)}、中途沒暫停 ${V.AB.detail.never_paused}`);
  console.log('取樣率差（附加）：48 kHz 播放 vs 96 kHz 驗算基準（MID 鏈，最大差）');
  Object.keys(V.RATE.rows).forEach((k) => console.log(`   ${k}: ${fmt(V.RATE.rows[k].max_diff_db)} dB @ ${fmt(V.RATE.rows[k].at_hz, 0)} Hz`));

  const allPass = ['V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7'].every((k) => V[k].pass === true) &&
                  (V.AB.pass === true || V.AB.undecidable === true);
  console.log('==========================================');
  console.log('全部：' + (allPass ? '通過' : '有項目未通過') + '　結果檔：' + RESULT_JSON);
  process.exit(allPass ? 0 : 1);
}

function md5(s) {
  return crypto.createHash('md5').update(s, 'utf8').digest('hex');
}

function md5file(p) {
  try { return crypto.createHash('md5').update(fs.readFileSync(p)).digest('hex'); }
  catch (e) { return 'ERROR: ' + e.message; }
}

main().catch((e) => {
  console.error('驗收程式失敗：' + (e && e.stack || e));
  process.exit(2);
});
