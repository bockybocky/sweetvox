#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""乾淨的播放＋側錄管線：直接寫入 M-DAC（WASAPI shared），同時從 M-DAC loopback 側錄。
用法: python lb_play.py <wav> <out.wav> [秒數]
（取代 winsound：winsound 看起來會把立體聲弄成近似單聲道，會讓量測失真）
"""
import sys, wave, time
import pyaudiowpatch as pyaudio

def find(pa, key, want_loopback):
    for i in range(pa.get_device_count()):
        d = pa.get_device_info_by_index(i)
        nm = d["name"]
        if key not in nm:
            continue
        if want_loopback and "Loopback" in nm and d["maxInputChannels"] >= 2:
            return i, d
        if (not want_loopback) and "Loopback" not in nm and d["maxOutputChannels"] >= 2:
            return i, d
    return None, None

def main():
    src, out = sys.argv[1], sys.argv[2]
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
    w = wave.open(src)
    ch, sw, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
    data = w.readframes(w.getnframes()); w.close()
    assert sw == 2 and ch == 2, "只支援 16-bit 立體聲 wav"

    p = pyaudio.PyAudio()
    ii, idd = find(p, "Audiolab", True)
    irate = int(idd["defaultSampleRate"])
    # 挑一台跟 loopback 同取樣率的輸出裝置，這樣完全不用重取樣（避免量測漂移）
    oi = od = None
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if ("Audiolab" in d["name"] and "Loopback" not in d["name"]
                and d["maxOutputChannels"] >= 2
                and int(d["defaultSampleRate"]) == irate):
            oi, od = i, d
            if "WASAPI" in p.get_host_api_info_by_index(d["hostApi"])["name"]:
                break
    if oi is None:
        oi, od = find(p, "Audiolab", False)
    orate = int(od["defaultSampleRate"])
    print(f"播 -> [{oi}] {od['name']} {orate}Hz ；錄 <- [{ii}] {idd['name']} {irate}Hz")
    ostr = p.open(format=pyaudio.paInt16, channels=2, rate=orate, output=True,
                  output_device_index=oi, frames_per_buffer=1024)
    istr = p.open(format=pyaudio.paInt16, channels=2, rate=irate, input=True,
                  input_device_index=ii, frames_per_buffer=1024)

    # 先等輸出串流啟動，再開始收
    def resample(raw, fr, to):
        """最陽春的線性內插（只為了測試訊號，不做品質評比）"""
        import struct
        n = len(raw) // 4
        s = struct.unpack("<%dh" % (2 * n), raw)
        need = int(n * to / fr)
        out = bytearray()
        for i in range(need):
            pos = i * fr / to
            i0 = int(pos); frac = pos - i0
            i1 = min(i0 + 1, n - 1)
            l = int(s[2 * i0] * (1 - frac) + s[2 * i1] * frac)
            r = int(s[2 * i0 + 1] * (1 - frac) + s[2 * i1 + 1] * frac)
            out += struct.pack("<hh", l, r)
        return bytes(out)

    play = resample(data, rate, orate) if orate != rate else data
    pos, step = 0, 2048
    frames = []
    need = int(irate / 1024 * secs)
    # 先丟一段出去讓 WASAPI 開始跑
    for _ in range(6):
        chunk = play[pos:pos + step * 2]; pos += step * 2
        if not chunk: pos = 0; chunk = play[pos:pos + step * 2]; pos += step * 2
        ostr.write(chunk)
    for _ in range(need):
        chunk = play[pos:pos + step * 2]; pos += step * 2
        if not chunk:
            pos = 0; chunk = play[pos:pos + step * 2]; pos += step * 2
        ostr.write(chunk)
        frames.append(istr.read(1024, exception_on_overflow=False))
    ostr.stop_stream(); ostr.close()
    istr.stop_stream(); istr.close(); p.terminate()

    wf = wave.open(out, "wb"); wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(irate)
    wf.writeframes(b"".join(frames)); wf.close()
    print("已寫入", out)

if __name__ == "__main__":
    main()
