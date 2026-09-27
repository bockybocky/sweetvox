"""自動試聽：把一批 Airwindows 外掛逐顆插進正中（女聲）鏈，量 THD 與偶次/奇次結構，
找出「真的給偶次諧波（暖）」而不只是「奇次（刺）」的飽和/真空管外掛。

用法: sep/.venv/Scripts/python.exe tools/audition_saturators.py [每顆測試的推力...]
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure_tube as mt
from sweep_tube_drive import inject_mid_drive

CANDIDATES = [
    # 名字看起來是真空管/飽和/磁帶/變壓器類的
    "SingleEndedTriode64.dll", "PurestWarm64.dll", "PurestWarm264.dll", "PurestWarm364.dll",
    "PurestDrive64.dll", "Air264.dll", "Spice64.dll", "SweetWarm64.dll",
    "Tube64.dll", "Tube264.dll", "TubeDesk64.dll", "Drive64.dll", "Density64.dll",
    "ToTape5.dll", "ToTape6.dll", "ToTape7.dll", "ToTape8.dll", "Tape64.dll", "Tape264.dll",
    "IronOxide5.dll", "IronOxide64.dll", "Mackity64.dll", "Mojo64.dll", "Pressure564.dll",
    "FireAmp64.dll", "BigAmp64.dll", "LeadAmp64.dll", "GrindAmp64.dll",
    "Spiral264.dll", "ChromeOxide64.dll", "PowerSag64.dll", "PowerSag264.dll",
    "Pop364.dll", "Pop264.dll", "Violent64.dll", "XRegion64.dll",
    "Hype64.dll", "Slew64.dll", "Slew264.dll", "Average64.dll", "Distance64.dll",
    "Weight64.dll", "ToneSlant64.dll", "Swell64.dll", "Compresaturator64.dll",
]


def main():
    drives = [float(x) for x in sys.argv[1:]] or [0.0, 12.0]
    mt.make_inputs()
    base = mt.load_base()
    rows = []
    for tube in CANDIDATES:
        path = os.path.join(mt.VSTDIR, tube)
        if not os.path.exists(path):
            print(f"  (跳過，檔案不存在) {tube}")
            continue
        for drive in drives:
            try:
                open(mt.CFG, "w", encoding="utf-8").write(inject_mid_drive(base, tube, drive))
                d, pk = mt.bench(os.path.join(mt.WORK, "in_phase.wav"),
                                 os.path.join(mt.WORK, "out_aud.wav"))
                r = mt.harm(d)
                if r is None:
                    continue
                h, h1 = r["h"], r["h1"]

                def hdb(k):
                    return 20 * np.log10(max(h[k], 1e-12) / h1)

                rows.append(dict(name=tube, drive=drive, thd=r["thd"], h2=hdb(2), h3=hdb(3),
                                 eo=r["even_odd_db"], rms=20 * np.log10(r["rms"]), pk=pk))
            except Exception as e:
                print(f"  (失敗) {tube} 推力{drive:+.0f}: {e}")
    open(mt.CFG, "w", encoding="utf-8").write(base)
    print("\n依「偶次減奇次」排序（越大＝越像真空管的暖；負值＝硬/刺）")
    print(f"{'外掛':22s}{'推力':>6s}{'THD%':>9s}{'h2 dBc':>9s}{'h3 dBc':>9s}{'偶-奇':>8s}{'RMS dB':>9s}{'峰值':>9s}")
    for r in sorted(rows, key=lambda r: -r["eo"]):
        print(f"{r['name']:22s}{r['drive']:+6.0f}{r['thd']:9.3f}{r['h2']:9.1f}{r['h3']:9.1f}"
              f"{r['eo']:+8.1f}{r['rms']:9.2f}{r['pk']:+9.2f}")
    print("\n（設定檔已還原）")


if __name__ == "__main__":
    main()
