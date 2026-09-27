"""掃「推力」對真空管失真的影響：推力 → 真空管 → 等量衰減（音量不變），看能不能逼出偶次諧波。
用法: sep/.venv/Scripts/python.exe tools/sweep_tube_drive.py
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure_tube as mt


def inject_mid_drive(cfg, tube, drive_db):
    """在正中（女聲）鏈末端插入：推力 → 真空管 → 等量衰減"""
    lines = cfg.splitlines()
    i = [k for k, l in enumerate(lines) if l.strip() == "Channel: R"][0]
    lines[i:i] = [f"Preamp: {drive_db:+.1f} dB",
                  f'VSTPlugin: Library "{os.path.join(mt.VSTDIR, tube)}"',
                  f"Preamp: {-drive_db:+.1f} dB"]
    return "\n".join(lines) + "\n"


def main():
    mt.make_inputs()
    base = mt.load_base()
    print("推力掃描（只掛在正中＝女聲那條鏈；真空管後等量衰減，音量不變）")
    print("真空管應該以偶次(h2/h4)為主；h3 偏大代表是硬式失真")
    print(f"{'真空管':16s}{'推力':>6s}{'THD%':>9s}{'h2 dBc':>9s}{'h3 dBc':>9s}{'偶-奇 dB':>10s}{'RMS dB':>9s}{'峰值 dBFS':>11s}")
    rows = []
    for tube in mt.TUBES:
        for drive in (0.0, 6.0, 12.0, 18.0):
            cfg = inject_mid_drive(base, tube, drive)
            open(mt.CFG, "w", encoding="utf-8").write(cfg)
            d, pk = mt.bench(os.path.join(mt.WORK, "in_phase.wav"),
                             os.path.join(mt.WORK, "out_sweep.wav"))
            r = mt.harm(d)
            h, h1 = r["h"], r["h1"]

            def hdb(k):
                return 20 * np.log10(max(h[k], 1e-12) / h1)

            rms = 20 * np.log10(r["rms"])
            print(f"{tube:16s}{drive:+6.0f}{r['thd']:9.3f}{hdb(2):9.1f}{hdb(3):9.1f}"
                  f"{r['even_odd_db']:+10.1f}{rms:9.2f}{pk:+11.2f}")
            rows.append((tube, drive, r["thd"], hdb(2), hdb(3), r["even_odd_db"], rms, pk))
    # 順便驗證延遲（推力 18 dB 時）
    cfg = inject_mid_drive(base, "Tube264.dll", 18.0)
    open(mt.CFG, "w", encoding="utf-8").write(cfg)
    d, _ = mt.bench(os.path.join(mt.WORK, "in_imp.wav"), os.path.join(mt.WORK, "out_imp.wav"))
    lat, _ = mt.latency(d)
    print(f"\n推力 +18 dB 時的延遲：{lat} 取樣")
    open(mt.CFG, "w", encoding="utf-8").write(base)
    print("已還原成原本的設定")


if __name__ == "__main__":
    main()
