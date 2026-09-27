"""播放 wav 到 Audiolab M-DAC（會經過 Equalizer APO 的女聲前移設定）。
用法: .venv/Scripts/python.exe play_wav.py <檔名.wav> [秒數]
"""
import sys, sounddevice as sd, soundfile as sf

path = sys.argv[1]
limit = float(sys.argv[2]) if len(sys.argv) > 2 else None

data, fs = sf.read(path, always_2d=True)
if limit:
    data = data[: int(limit * fs)]

dev = None
for i, d in enumerate(sd.query_devices()):
    if d["max_output_channels"] > 0 and "M-DAC" in d["name"]:
        dev = i
        break
name = sd.query_devices(dev)["name"] if dev is not None else "（系統預設）"
print(f"播放 {path}  {len(data)/fs:.1f} 秒 @ {fs} Hz")
print(f"輸出裝置: {name}")
sd.play(data, fs, device=dev, blocking=True)
print("播完")
