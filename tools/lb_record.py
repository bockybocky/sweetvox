#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""從指定裝置（預設找 Audiolab M-DAC 的 loopback）側錄 N 秒成 wav。"""
import sys, wave
import pyaudiowpatch as pyaudio

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
out = sys.argv[2] if len(sys.argv) > 2 else "loopback.wav"
pat = sys.argv[3] if len(sys.argv) > 3 else "Audiolab"

p = pyaudio.PyAudio()
idx = None
for i in range(p.get_device_count()):
    d = p.get_device_info_by_index(i)
    if pat in d["name"] and "Loopback" in d["name"]:
        idx = i
        dev = d
        break
if idx is None:
    print("找不到符合的 loopback 裝置：", pat)
    p.terminate()
    sys.exit(1)

rate = int(dev["defaultSampleRate"])
ch = min(2, int(dev["maxInputChannels"]))
print(f"錄音裝置 [{idx}] {dev['name']}  rate={rate} ch={ch} 秒數={secs}")
stream = p.open(format=pyaudio.paInt16, channels=ch, rate=rate, input=True,
                input_device_index=idx, frames_per_buffer=1024)
blocks = int(rate / 1024 * secs)
frames = [stream.read(1024, exception_on_overflow=False) for _ in range(blocks)]
stream.stop_stream(); stream.close(); p.terminate()

wf = wave.open(out, "wb")
wf.setnchannels(ch); wf.setsampwidth(2); wf.setframerate(rate)
wf.writeframes(b"".join(frames)); wf.close()
print("已寫入", out)
