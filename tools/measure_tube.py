"""量一條 Equalizer APO 鏈的客觀指標：THD、諧波結構（偶次/奇次）、延遲、峰值、音量。
做法：用 Benchmark.exe 離線跑「檔案進 → 檔案出」，完全不經過喇叭，不受正在播的音樂干擾。

用法: python measure_tube.py            # 量 無真空管 / 真空管-全鏈 / 真空管-只正中 三種
"""
import os as _os; _ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 倉庫根目錄
import importlib.util, json, os, re, subprocess, sys
import numpy as np
import soundfile as sf

BENCH = r"C:\Program Files\EqualizerAPO\Benchmark.exe"
CFG = r"C:\Program Files\EqualizerAPO\config\vocal_focus_custom.txt"
WORK = _os.path.join(_ROOT, r"test")
VSTDIR = _os.path.join(_ROOT, r"vst\airwindows\WinVST64s")
FS = 44100.0
TUBES = ["Tube264.dll", "Tube64.dll", "TubeDesk64.dll"]


def make_inputs():
    os.makedirs(WORK, exist_ok=True)
    t = np.arange(int(FS * 6.0)) / FS
    s = (0.25 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    for name, pair in (("in_phase", (s, s)), ("in_anti", (s, -s))):
        sf.write(os.path.join(WORK, f"{name}.wav"), np.stack(pair, axis=1), int(FS), subtype="FLOAT")
    imp = np.zeros(int(FS * 0.5), dtype=np.float32)
    imp[1000] = 0.25
    sf.write(os.path.join(WORK, "in_imp.wav"), np.stack([imp, imp], axis=1), int(FS), subtype="FLOAT")


def bench(inp, outp, peak=False):
    r = subprocess.run([BENCH, "--nopause", "-r", str(int(FS)), "-i", inp, "-o", outp],
                       capture_output=True, text=True)
    d, f = sf.read(outp, always_2d=True)
    pk = None
    m = re.search(r"Max output level: [\d.]+ \(([-\d.]+) dB\)", r.stdout)
    if m:
        pk = float(m.group(1))
    return d.astype(np.float64), pk


def harm(d):
    x = d[:, 0]
    seg = x[int(FS * 1.5): int(FS * 1.5) + 65536]
    w = np.hanning(len(seg))
    X = np.abs(np.fft.rfft(seg * w))
    fr = np.fft.rfftfreq(len(seg), 1 / FS)

    def at(f0):
        i = int(np.argmin(abs(fr - f0)))
        return float(X[max(0, i - 1):i + 2].max())

    h1 = at(1000.0)
    hs = {k: at(1000.0 * k) for k in range(2, 11)}
    if h1 <= 0:
        return None
    even = np.sqrt(sum(v ** 2 for k, v in hs.items() if k % 2 == 0))
    odd = np.sqrt(sum(v ** 2 for k, v in hs.items() if k % 2 == 1))
    thd = np.sqrt(sum(v ** 2 for v in hs.values())) / h1
    return dict(rms=float(np.sqrt(np.mean(x ** 2))), h=hs, h1=h1,
                thd=thd * 100, even_even_db=20 * np.log10(max(even, 1e-12) / h1),
                odd_db=20 * np.log10(max(odd, 1e-12) / h1),
                even_odd_db=20 * np.log10(max(even, 1e-12) / max(odd, 1e-12)))


def latency(d):
    x = d[:, 0]
    i = int(np.argmax(np.abs(x)))
    return i - 1000, float(np.max(np.abs(x)))


def load_base():
    spec = importlib.util.spec_from_file_location(
        "g", _os.path.join(_ROOT, r"app\vocal_focus_gui.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    st = dict(g.DEFAULTS)
    p = _os.path.join(_ROOT, r"app\state.json")
    if os.path.exists(p):
        st.update(json.load(open(p, encoding="utf-8")))
    st["on"] = True
    return g.build_config(st)


def inject(cfg, tube, where):
    """where='full' 放在拆中側之前（兩邊都過）；'mid' 放在正中鏈末端（只過女聲）"""
    line = f'VSTPlugin: Library "{os.path.join(VSTDIR, tube)}"'
    out = cfg.splitlines()
    if where == "full":
        idx = max(i for i, l in enumerate(out) if l.startswith(("Preamp", "VSTPlugin"))) + 1
        out.insert(idx, line)
    else:
        idx = [i for i, l in enumerate(out) if l.strip() == "Channel: R"][0]
        out.insert(idx, line)
    return "\n".join(out) + "\n"


def run_variant(label, cfg):
    open(CFG, "w", encoding="utf-8").write(cfg)
    res = {}
    for tag, inp in (("phase", "in_phase"), ("anti", "in_anti")):
        d, pk = bench(os.path.join(WORK, f"{inp}.wav"), os.path.join(WORK, f"out_{tag}.wav"))
        res[tag] = harm(d)
        res[tag]["peak_dbfs"] = pk
    d, _ = bench(os.path.join(WORK, "in_imp.wav"), os.path.join(WORK, "out_imp.wav"))
    res["lat"], res["imp_peak"] = latency(d)
    print(f"\n── {label} ──")
    for tag, nm in (("phase", "同相(正中=女聲)"), ("anti", "反相(純兩側=伴奏)")):
        r = res[tag]
        print(f"  {nm}: RMS {20*np.log10(r['rms']):7.2f} dB   THD {r['thd']:6.3f}%   "
              f"偶次 {r['even_even_db']:7.1f} dB  奇次 {r['odd_db']:7.1f} dB  "
              f"偶/奇 {r['even_odd_db']:+6.1f} dB  峰值 {r['peak_dbfs']:+.2f} dBFS")
    h = res["phase"]["h"]
    print("  諧波(dBc, 對 1kHz): " + "  ".join(f"h{k} {20*np.log10(max(h[k],1e-12)/res['phase']['h1']):6.1f}" for k in range(2, 8)))
    print(f"  延遲 {res['lat']} 取樣（0＝無延遲，不會造成梳狀濾波）")
    return res


if __name__ == "__main__":
    make_inputs()
    base = load_base()
    print(f"基礎設定：真空管未加、Air VST {'開' if 'Air64' in base else '關'}")
    run_variant("無真空管（基準）", base)
    for tube in TUBES:
        run_variant(f"{tube}｜全鏈（女聲＋伴奏都過）", inject(base, tube, "full"))
        run_variant(f"{tube}｜只正中（只有女聲那條過）", inject(base, tube, "mid"))
    open(CFG, "w", encoding="utf-8").write(base)
    print("\n已還原成原本的設定")
