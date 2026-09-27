// 驗證「甜嗓曲線產生器.html」：不開瀏覽器，用最小 DOM 替身把頁面 JS 真的跑一遍。
// 用法: node tools/verify_curve_page.js
const fs = require('fs');
const path = 'E:/AI/workspace/vocal_focus/phone/甜嗓曲線產生器.html';
const html = fs.readFileSync(path, 'utf8');
const script = html.split('<script>')[1].split('</script>')[0];

const store = {};
const ctxStub = new Proxy({}, { get: (t, k) => (k === 'font' || k === 'fillStyle' || k === 'strokeStyle' || k === 'lineWidth' ? '' : () => {}), set: () => true });
function el(id) {
  if (!store[id]) {
    store[id] = { id, value: '', textContent: '', innerHTML: '', checked: false, dataset: {},
                  classList: { add() {}, remove() {} }, addEventListener() {}, getContext: () => ctxStub };
  }
  return store[id];
}
const presets = ['daily', 'night', 'commute', 'earbud', 'flat'].map(p => { const o = el('p_' + p); o.dataset.p = p; return o; });
const warned = [];
global.document = {
  getElementById: el,
  querySelectorAll: (s) => presets,
  createElement: () => ({ style: {}, select() {}, remove() {} }),
  body: { appendChild() {} },
};
global.navigator = {};
global.console.warn = (...a) => warned.push(a.join(' '));

el('bass').value = '7'; el('mid').value = '3'; el('tre').value = '-4';
el('demud').checked = true; el('desib').checked = true;

eval(script);

console.log('=== 預設 日常（低音+7 中音+3 高音-4）===');
console.log(el('out10').textContent);
console.log('峰值標示：', el('pk').textContent);
console.log('=== 參數式 ===');
console.log(el('outParam').textContent);
console.log('=== Qudelix ===');
console.log(el('outQ').textContent);

// 換情境：深夜小聲
el('bass').value = '4'; el('mid').value = '4'; el('tre').value = '-6';
render();
console.log('=== 情境「深夜小聲」：低音+4 中音+4 高音-6 ===');
console.log(el('out10').textContent);

// 全部歸零：應該只剩 350 Hz 與 7.5 kHz 兩段（歸零情境會關掉）→ 期望全 0
el('bass').value = '0'; el('mid').value = '0'; el('tre').value = '0';
el('demud').checked = false; el('desib').checked = false;
render();
console.log('=== 全部歸零（應全為 +0.0）===');
console.log(el('out10').textContent);
if (warned.length) console.log('console.warn:', warned.join(' | '));
