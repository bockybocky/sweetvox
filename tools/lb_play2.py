#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
乾淨可重複的播放＋側錄管線（v2）
  * 測試訊號：固定種子的立體聲白噪音（左右獨立、每次完全相同 → 可重複比對）
  * 播放：直接寫入 M-DAC（挑跟 loopback 同取樣率的裝置，全程不重取樣）
  * 側錄：M-DAC 的 WASAPI loopback
用法: python lb_play2.py <out.wav> [秒數] [seed]
"""
import sys, wave, random, struct
import pyaudiowpatch as pyaudio

RATE_HINT = "Audiolab"

def find_loopback(pa):
    for i in range(pa.get_device_count()):
        d = pa.get_device_info_by_index(i)
        if RATE_HINT in d["name"] and "Loopback" in d["name"] and d["maxInputChannels"] >= 2:
            return i, d
    return None, None

def find_output(pa, rate):
    best = None
    for i in range(pa.get_device_count()):
        d = pa.get_device_info_by_index(i)
        if RATE_HINT not in d["name"] or "Loopback" in d["name"] or d["maxOutputChannels"] < 2:
            continue
        if int(d["defaultSampleRate"]) != rate:
            continue
        api = pa.get_host_api_info_by_index(d["hostApi"])["name"]
        if "WASAPI" in api:
            return i, d
        best = best or (i, d)
    return best if best else (None, None)

def gen_noise(secs, rate, seed=12345):
    """左右獨立的白噪音，固定種子 → 每次一模一樣"""
    r1, r2 = random.Random(seed), random.Random(seed + 1)
    n = int(rate * secs)
    buf = bytearray()
    amp = 0.22 * 32767
    for _ in range(n):
        buf += struct.pack("<hh", int(r1.uniform(-1, 1) * amp), int(r2.uniform(-1, 1) * amp))
    return bytes(buf)

def main():
    out = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 12345

    p = pyaudio.PyAudio()
    ii, idd = find_loopback(p)
    if ii is None:
        print("找不到 M-DAC loopback"); p.terminate(); sys.exit(1)
    irate = int(idd["defaultSampleRate"])
    oi, od = find_output(p, irate)
    if oi is None:
        print(f"找不到與 loopback 同率（{irate}）的 M-DAC 輸出裝置"); p.terminate(); sys.exit(1)
    api = p.get_host_api_info_by_index(od["hostApi"])["name"]
    print(f"播 -> [{oi}] {od['name']} ({api}) {irate}Hz ；錄 <- [{ii}] {idd['name']} {irate}Hz")

    play = gen_noise(secs + 3.0, irate, seed)
    ostr = p.open(format=pyaudio.paInt16, channels=2, rate=irate, output=True,
                  output_device_index=oi, frames_per_buffer=1024)
    istr = p.open(format=pyaudio.paInt16, channels=2, rate=irate, input=True,
                  input_device_index=ii, frames_per_buffer=1024)

    fb = 4 * 1024  # 每塊 1024 frames = 4096 bytes
    pos = 0
    # 先餵 0.5 秒讓輸出串流穩定跑起來（這段不錄）
    for _ in range(int(irate / 1024 * 0.5)):
        ostr.write(play[pos:pos + fb]); pos += fb
    frames = []
    for _ in range(int(irate / 1024 * secs)):
        ostr.write(play[pos:pos + fb]); pos += fb
        frames.append(istr.read(1024, exception_on_overflow=False))
    ostr.stop_stream(); ostr.close(); istr.stop_stream(); istr.close(); p.terminate()

    w = wave.open(out, "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(irate)
    w.writeframes(b"".join(frames)); w.close()
    print("已寫入", out)

if __name__ == "__main__":
    main()
