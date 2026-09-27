#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""播一個 wav（非同步、走預設裝置＝M-DAC），同時從 M-DAC loopback 側錄，存成 out.wav。
用法: python lb_round.py <要播的wav> <存檔wav> <錄幾秒>"""
import sys, time, wave, winsound
import pyaudiowpatch as pyaudio

play = sys.argv[1]
out = sys.argv[2]
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
skip = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0   # 等播放先穩定的秒數

p = pyaudio.PyAudio()
idx = None
for i in range(p.get_device_count()):
    d = p.get_device_info_by_index(i)
    if "Audiolab" in d["name"] and "Loopback" in d["name"]:
        idx, dev = i, d
        break
if idx is None:
    print("找不到 Audiolab M-DAC loopback"); p.terminate(); sys.exit(1)

rate = int(dev["defaultSampleRate"])
stream = p.open(format=pyaudio.paInt16, channels=2, rate=rate, input=True,
                input_device_index=idx, frames_per_buffer=1024)
winsound.PlaySound(play, winsound.SND_FILENAME | winsound.SND_ASYNC)
time.sleep(skip)
blocks = int(rate / 1024 * secs)
frames = [stream.read(1024, exception_on_overflow=False) for _ in range(blocks)]
stream.stop_stream(); stream.close(); p.terminate()
winsound.PlaySound(None, winsound.SND_PURGE)

wf = wave.open(out, "wb"); wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(rate)
wf.writeframes(b"".join(frames)); wf.close()
print(f"播 {play} → 錄 {out}（{secs}s @ {rate}Hz）")
