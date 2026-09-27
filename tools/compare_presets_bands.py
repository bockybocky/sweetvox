"""比較兩個 preset 對同一首歌的頻帶能量差異（用 Benchmark 離線跑完整條 APO 鏈）。
用途：證明「深夜」模式真的砍掉穿牆的低頻、抬起人聲清晰度，而不是靠感覺。
用法: sep/.venv/Scripts/python.exe tools/compare_presets_bands.py 中 深夜
"""
import os as _os; _ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 倉庫根目錄
import importlib.util, json, os, sys
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure_tube as mt

SONG = _os.path.join(_ROOT, r"sep\work\song_40s.wav")
BANDS = [(20, 40), (40, 60), (60, 85), (85, 120), (120, 250), (250, 500), (500, 1000),
         (1000, 2000), (2000, 4000), (4000, 8000), (8000, 16000)]


def load_gui():
    spec = importlib.util.spec_from_file_location(
        "g", _os.path.join(_ROOT, r"app\vocal_focus_gui.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    return g


def render(g, preset, out):
    st = dict(g.DEFAULTS)
    p = _os.path.join(_ROOT, r"app\state.json")
    if os.path.exists(p):
        st.update(json.load(open(p, encoding="utf-8")))
    if preset != "現在":
        st.update(g.PRESETS[preset])
    st["on"] = True
    open(g.CUSTOM, "w", encoding="utf-8").write(g.build_config(st))
    import re, subprocess
    r = subprocess.run([mt.BENCH, "--nopause", "-r", "44100", "-i", SONG, "-o", out],
                       capture_output=True, text=True)
    pk = re.search(r"Max output level: [\d.]+ \(([-\d.]+) dB\)", r.stdout)
    return float(pk.group(1)) if pk else float("nan"), ("clipped" in r.stdout)


def band_db(path):
    d, fs = sf.read(path, always_2d=True)
    x = d.mean(axis=1)
    n = min(len(x), int(fs * 10))
    X = np.abs(np.fft.rfft(x[:n] * np.hanning(n))) ** 2
    fr = np.fft.rfftfreq(n, 1 / fs)
    out = {}
    for lo, hi in BANDS:
        m = (fr >= lo) & (fr < hi)
        e = X[m].sum()
        out[(lo, hi)] = 10 * np.log10(max(e, 1e-20))
    # 中/側（女聲 vs 伴奏）
    L, R = d[:, 0], d[:, 1]
    mid = (L + R) / 2
    side = (L - R) / 2
    db = lambda v: 20 * np.log10(max(np.sqrt(np.mean(v ** 2)), 1e-12))
    return out, db(mid), db(side)


def main():
    g = load_gui()
    a = sys.argv[1] if len(sys.argv) > 1 else "中"
    b = sys.argv[2] if len(sys.argv) > 2 else "深夜"
    mt.make_inputs()
    pa, clipa = render(g, a, os.path.join(mt.WORK, "cmp_a.wav"))
    pb, clipb = render(g, b, os.path.join(mt.WORK, "cmp_b.wav"))
    ba, ma, sa = band_db(os.path.join(mt.WORK, "cmp_a.wav"))
    bb, mb, sb = band_db(os.path.join(mt.WORK, "cmp_b.wav"))
    print(f"\nA = {a}   峰值 {pa:+.2f} dBFS 削波={clipa}")
    print(f"B = {b}   峰值 {pb:+.2f} dBFS 削波={clipb}")
    print(f"\n{'頻帶 Hz':>14s}{'A dB':>10s}{'B dB':>10s}{'B-A':>9s}")
    for lo, hi in BANDS:
        print(f"{str(lo)+'-'+str(hi):>14s}{ba[(lo,hi)]:10.1f}{bb[(lo,hi)]:10.1f}{bb[(lo,hi)]-ba[(lo,hi)]:+9.1f}")
    print(f"\n女聲(正中) {ma:.1f} dB → {mb:.1f} dB  ({mb-ma:+.1f})")
    print(f"伴奏(兩側) {sa:.1f} dB → {sb:.1f} dB  ({sb-sa:+.1f})")
    print(f"女聲相對伴奏 {(ma-sa):+.1f} dB → {(mb-sb):+.1f} dB  （差 {((mb-sb)-(ma-sa)):+.1f} dB）")
    print("\n（低頻 <85 Hz 降越多＝越不容易吵到隔壁；1~4 kHz 升＝小聲時人聲越清楚）")


if __name__ == "__main__":
    main()
