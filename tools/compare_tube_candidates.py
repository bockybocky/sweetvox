"""把多顆飽和/真空管外掛放在同一套量測下對比：THD、偶次/奇次結構、峰值、延遲。
用法: sep/.venv/Scripts/python.exe tools/compare_tube_candidates.py
      sep/.venv/Scripts/python.exe tools/compare_tube_candidates.py "C:/路徑/某.dll"
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure_tube as mt

DEFAULT_CANDS = [
    ("PurestWarm（現用）", os.path.join(mt.VSTDIR, "PurestWarm64.dll")),
    ("Voxengo Tube Amp", r"C:\Program Files\Common Files\VST2\Voxengo\Tube Amp.dll"),
    ("Airwindows Tube264", os.path.join(mt.VSTDIR, "Tube264.dll")),
]


def inject(cfg, dll_path, drive_db):
    """在正中（女聲）鏈末端插入：推力 → 外掛 → 等量衰減"""
    lines = cfg.splitlines()
    i = [k for k, l in enumerate(lines) if l.strip() == "Channel: R"][0]
    lines[i:i] = [f"Preamp: {drive_db:+.1f} dB",
                  f'VSTPlugin: Library "{dll_path}"',
                  f"Preamp: {-drive_db:+.1f} dB"]
    return "\n".join(lines) + "\n"


def main():
    cands = DEFAULT_CANDS
    if len(sys.argv) > 1:
        cands = [(os.path.basename(a), a) for a in sys.argv[1:]]
    mt.make_inputs()
    base = mt.load_base()
    print(f"{'外掛':22s}{'推力':>6s}{'THD%':>9s}{'h2 dBc':>9s}{'h3 dBc':>9s}{'偶-奇 dB':>10s}{'峰值':>9s}")
    best = {}
    for name, path in cands:
        if not os.path.exists(path):
            print(f"  (找不到檔案) {name} -> {path}")
            continue
        for drive in (0.0, 6.0, 12.0, 18.0):
            try:
                open(mt.CFG, "w", encoding="utf-8").write(inject(base, path, drive))
                d, pk = mt.bench(os.path.join(mt.WORK, "in_phase.wav"),
                                 os.path.join(mt.WORK, "out_cmp.wav"))
                r = mt.harm(d)
                if r is None:
                    continue
                h, h1 = r["h"], r["h1"]
                hdb = lambda k: 20 * np.log10(max(h[k], 1e-12) / h1)
                print(f"{name:22s}{drive:+6.0f}{r['thd']:9.3f}{hdb(2):9.1f}{hdb(3):9.1f}"
                      f"{r['even_odd_db']:+10.1f}{pk:+9.2f}")
                # 記錄「THD 在 0.5~4% 之間、且偶次最高」的最佳檔
                if 0.4 <= r["thd"] <= 5.0:
                    if name not in best or r["even_odd_db"] > best[name][1]:
                        best[name] = (drive, r["even_odd_db"], r["thd"])
            except Exception as e:
                print(f"  (失敗) {name} 推力{drive:+.0f}: {e}")
    print("\n每顆在「可用失真量（THD 0.4~5%）」下最偏偶次的檔位：")
    for name, (drive, eo, thd) in sorted(best.items(), key=lambda kv: -kv[1][1]):
        print(f"  {name:22s} 推力 {drive:+.0f} dB  THD {thd:.2f}%  偶-奇 {eo:+.1f} dB")
    open(mt.CFG, "w", encoding="utf-8").write(base)
    print("\n（設定檔已還原）")


if __name__ == "__main__":
    main()
