# -*- coding: utf-8 -*-
"""房間量測：指數掃頻（ESS）＋ 反摺積，量出「喇叭＋房間＋麥克風」的頻率響應。

為什麼用 ESS 而不是直接放噪音：掃頻的反摺積可以把非線性失真（諧波）推到脈衝響應
的「負時間」去，跟線性部分分開，所以即使喇叭有失真也不會污染曲線。

**未校正麥克風的用法**：絕對曲線不可信（webcam 麥克風通常 100~200 Hz 以下就滾降）。
正確用法是**量兩次相減**（甜嗓開/關），麥克風與喇叭的誤差會抵消，
剩下的應該等於甜嗓的設計曲線 —— 對得上才證明這把尺可信（先校正尺，再量東西）。

播放與錄音**一定要用兩個獨立的 Stream**，不可以用 sd.play/sd.rec
（那兩個共用同一個全域串流槽，後呼叫的會把前一個停掉 → 永遠錄到靜音；帳本 L194）。

用法：
  python room_sweep.py --tag sweetvox_on
  python room_sweep.py --tag bypass
  python room_sweep.py --compare sweetvox_on bypass
"""
import argparse
import json
import math
import os
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

SR = 48000          # webcam 麥克風的原生速率
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "room")


def make_sweep(f1=20.0, f2=20000.0, dur=15.0, sr=SR, amp=0.25):
    """指數掃頻 ＋ 它的反摺積濾波器"""
    n = int(dur * sr)
    t = np.arange(n) / sr
    k = math.log(f2 / f1)
    sweep = np.sin(2 * math.pi * f1 * dur / k * (np.exp(t * k / dur) - 1))
    # 頭尾淡入淡出，避免點擊
    fade = int(0.05 * sr)
    sweep[:fade] *= np.linspace(0, 1, fade)
    sweep[-fade:] *= np.linspace(1, 0, fade)
    # 反掃頻 ＋ 每八度 −6 dB 的補償 = 反摺積濾波器
    inv = sweep[::-1] * np.exp(-t * k / dur)
    inv /= np.abs(np.fft.rfft(inv) * np.fft.rfft(sweep)).max()
    return (amp * sweep).astype(np.float32), inv.astype(np.float64)


def record_sweep(sweep, out_dev, in_dev, tail=2.0, sr=SR):
    """兩個獨立 Stream：一邊放、一邊錄"""
    n_play = len(sweep)
    n_rec = n_play + int(tail * sr)
    captured, pos = [], [0]

    def icb(indata, frames, t_, status):
        captured.append(indata.copy())

    def ocb(outdata, frames, t_, status):
        p = pos[0]
        chunk = sweep[p:p + frames]
        if len(chunk) < frames:
            outdata[:, 0] = np.concatenate([chunk, np.zeros(frames - len(chunk), np.float32)])
            outdata[:, 1] = outdata[:, 0]
            pos[0] += len(chunk)
            return
        outdata[:, 0] = chunk
        outdata[:, 1] = chunk
        pos[0] += frames

    # 輸出端點可能是 96 kHz（M-DAC），掃頻是 48 kHz → 共享模式會直接拒絕，
    # 用 auto_convert 讓 Windows 轉。**不要用獨佔要求非原生速率**，那會把 M-DAC 打下 USB（帳本 L203）。
    auto = sd.WasapiSettings(auto_convert=True)
    istream = sd.InputStream(device=in_dev, samplerate=sr, channels=1, blocksize=0,
                             dtype="float32", callback=icb, extra_settings=auto)
    ostream = sd.OutputStream(device=out_dev, samplerate=sr, channels=2, blocksize=0,
                              dtype="float32", callback=ocb, extra_settings=auto)
    istream.start()
    time.sleep(0.5)
    ostream.start()
    time.sleep(n_rec / sr + 0.5)
    for s in (ostream, istream):
        s.stop()
        s.close()
    rec = np.concatenate(captured)[:, 0] if captured else np.zeros(1)
    return rec.astype(np.float64)


def freq_response(rec, inv, sr=SR):
    """反摺積取脈衝響應 → 取線性部分 → 頻率響應"""
    n = 1
    while n < len(rec) + len(inv):
        n *= 2
    ir = np.fft.irfft(np.fft.rfft(rec, n) * np.fft.rfft(inv, n), n)
    peak = int(np.argmax(np.abs(ir)))
    # 線性脈衝響應：峰值前 5 ms 到峰值後 400 ms（含房間殘響）
    a = max(0, peak - int(0.005 * sr))
    b = min(len(ir), peak + int(0.4 * sr))
    seg = ir[a:b] * np.hanning(b - a) ** 0.25
    spec = np.fft.rfft(seg, 1 << 16)
    freqs = np.fft.rfftfreq(1 << 16, 1 / sr)
    mag = 20 * np.log10(np.maximum(np.abs(spec), 1e-12))
    return freqs, mag, ir, peak


def smooth(freqs, mag, frac=6):
    """1/frac 八度平滑"""
    out = np.empty_like(mag)
    for i, f in enumerate(freqs):
        if f <= 0:
            out[i] = mag[i]
            continue
        lo, hi = f / 2 ** (1 / (2 * frac)), f * 2 ** (1 / (2 * frac))
        sel = (freqs >= lo) & (freqs <= hi)
        out[i] = mag[sel].mean() if sel.any() else mag[i]
    return out


def pick(part, kind):
    key = f"max_{kind}_channels"
    for d in sd.query_devices():
        if part.lower() in d["name"].lower() and d[key] >= 1 \
           and "wasapi" in sd.query_hostapis(d["hostapi"])["name"].lower():
            return d["index"], d["name"]
    raise SystemExit(f"找不到 {part} 的 {kind} 端點")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=None, help="這次量測的名稱（例如 sweetvox_on）")
    ap.add_argument("--compare", nargs=2, default=None, help="比較兩次量測：<A> <B>，輸出 A−B")
    ap.add_argument("--out-dev", default="M-DAC")
    ap.add_argument("--in-dev", default="麦克风")
    ap.add_argument("--dur", type=float, default=15.0)
    ap.add_argument("--amp", type=float, default=0.25)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    if args.compare:
        a = np.load(os.path.join(OUT, f"{args.compare[0]}.npz"))
        b = np.load(os.path.join(OUT, f"{args.compare[1]}.npz"))
        freqs = a["freqs"]
        diff = smooth(freqs, a["mag"] - b["mag"])
        band = (freqs >= 20) & (freqs <= 20000)
        print(f"=== {args.compare[0]} 減 {args.compare[1]} ===")
        print(f"{'Hz':>8} {'dB':>8}")
        for f in (35, 50, 80, 100, 150, 200, 350, 500, 1000, 2000, 3000, 5000, 7500, 10000, 15000):
            i = int(np.argmin(np.abs(freqs - f)))
            print(f"{f:>8} {diff[i]:>8.2f}")
        np.savez(os.path.join(OUT, "diff.npz"), freqs=freqs, diff=diff)
        return

    if not args.tag:
        raise SystemExit("要給 --tag")
    out_i, out_n = pick(args.out_dev, "output")
    in_i, in_n = pick(args.in_dev, "input")
    print(f"播 → [{out_i}] {out_n}")
    print(f"錄 ← [{in_i}] {in_n}")
    sweep, inv = make_sweep(dur=args.dur, amp=args.amp)
    print(f"掃頻 {args.dur:.0f} 秒（20 Hz → 20 kHz），開始...", flush=True)
    rec = record_sweep(sweep, out_i, in_i, sr=SR)
    rms = float(np.sqrt((rec ** 2).mean()))
    print(f"錄到 {len(rec)} 樣本，RMS {20 * math.log10(max(rms, 1e-12)):.1f} dBFS，"
          f"峰值 {20 * math.log10(max(float(np.abs(rec).max()), 1e-12)):.1f} dBFS")
    if rms < 1e-4:
        print("⚠ 幾乎沒錄到聲音 —— 麥克風靜音？音量太小？")
    freqs, mag, ir, peak = freq_response(rec, inv)
    sm = smooth(freqs, mag)
    np.savez(os.path.join(OUT, f"{args.tag}.npz"), freqs=freqs, mag=mag, smooth=sm)
    sf.write(os.path.join(OUT, f"{args.tag}_rec.wav"), rec.astype(np.float32), SR)
    band = (freqs >= 100) & (freqs <= 10000)
    ref = sm[band].mean()
    print(f"\n=== {args.tag} 的頻率響應（1/6 八度平滑，100 Hz–10 kHz 的平均當 0 dB）===")
    for f in (31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 800,
              1000, 1600, 2000, 3150, 5000, 8000, 12500):
        i = int(np.argmin(np.abs(freqs - f)))
        bar = "#" * max(0, int((sm[i] - ref + 15) / 1.5))
        print(f"{f:>7} Hz {sm[i] - ref:>+7.1f} dB  {bar}")


if __name__ == "__main__":
    main()
