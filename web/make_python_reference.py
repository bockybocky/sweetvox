#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
驗收程式 test_sweetvox.mjs 的「Python 參考值產生器」。

它直接 import 桌面版的 vocal_focus_gui.py（不改它、不執行它的介面），
用桌面版自己的 _biquad / _mag_db / _chain_peak_db / safe_preamp / build_config 算出：

  V1 四個預設 MID 鏈在 20 Hz ~ 20 kHz（1/12 八度）的頻率響應
  V2 四個預設的 safe_preamp（vst_air=False）
  V3 四個預設 + 預設狀態的 build_config() 全文

用法： python make_python_reference.py <輸出 json>
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DESKTOP_DIR = os.path.abspath(os.path.join(HERE, "..", "app"))
sys.path.insert(0, DESKTOP_DIR)

import vocal_focus_gui as gui   # noqa: E402  （桌面版，唯讀引用）

FS = 96000.0
PRESETS = list(gui.PRESETS.keys())


def mid_chain_spec(v):
    """桌面版 build_config() 寫進 MID 鏈（Channel: L）的六顆濾波器，
    以及 SIDE 鏈（Channel: R）的那顆，回傳 [(kind, f0, gain_db, q), ...]"""
    mid = [("HP", float(v.get("subcut", 35.0)), 0.0, 0.7),
           ("LS", 150.0, float(v["warm"]), 0.7),
           ("PK", 350.0, float(v["mud"]), 1.4),
           ("PK", 3000.0, float(v["sweet"]), 0.9),
           ("PK", 7500.0, float(v["sib"]), 2.0),
           ("HS", 10000.0, float(v["air"]), 0.707)]
    side = [("PK", 2000.0, -1.5, 0.8)]
    if v["centerbass"]:
        side.append(("HP", 100.0, 0.0, 0.7))
    return mid, side


def resp_db(filt, f, fs=FS):
    """跟桌面版 _mag_db 同一套（HP 用 RBJ 高通，其餘照 _biquad）"""
    kind, f0, g, q = filt
    if kind == "HP":
        A = 1.0
        w = 2 * math.pi * f0 / fs
        cw, sw = math.cos(w), math.sin(w)
        alpha = sw / (2 * q)
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
        c = (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)
    else:
        c = gui._biquad(kind, f0, g, q, fs)
    return gui._mag_db(c, f, fs)


def grid_1_12_octave():
    """20 Hz 起，每 1/12 八度一點，到 20 kHz 為止（含端點附近最後一點）"""
    freqs, f = [], 20.0
    while f <= 20000.0:
        freqs.append(f)
        f *= 2 ** (1.0 / 12.0)
    return freqs


def preset_state(name):
    """桌面版按了某個預設之後的完整狀態（DEFAULTS → 套 PRESETS[name]）"""
    v = dict(gui.DEFAULTS)
    v.update(gui.PRESETS[name])
    return v


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "python_reference.json")
    freqs = grid_1_12_octave()
    data = {
        "source": "vocal_focus_gui.py (桌面版，唯讀 import)",
        "desktop_md5": None,
        "fs": FS,
        "freqs": freqs,
        "presets": {},
        "configs": {}
    }

    for name in PRESETS:
        v = preset_state(name)
        mid, side = mid_chain_spec(v)
        mid_db = [sum(resp_db(x, f) for x in mid) for f in freqs]
        side_db = [sum(resp_db(x, f) for x in side) for f in freqs]
        # 分類用的：每一點只算「非架式」那幾顆（HP/PK）的總和，以及架式（LS/HS）的總和
        peak_filters = [x for x in mid if x[0] in ("HP", "PK")]
        shelf_filters = [x for x in mid if x[0] in ("LS", "HS")]
        peak_db = [sum(resp_db(x, f) for x in peak_filters) for f in freqs]
        shelf_db = [sum(resp_db(x, f) for x in shelf_filters) for f in freqs]
        data["presets"][name] = {
            "state": v,
            "mid_spec": mid,
            "side_spec": side,
            "mid_db": mid_db,
            "side_db": side_db,
            "peak_part_db": peak_db,
            "shelf_part_db": shelf_db,
            "safe_preamp": gui.safe_preamp(v),
            "config_preamp": _preamp_from_config(gui.build_config(v)),
            "config_text": gui.build_config(v)
        }

    # 另外一份：預設狀態（DEFAULTS）的設定檔，V3 會一起比
    v_def = dict(gui.DEFAULTS)
    data["configs"]["DEFAULTS"] = {
        "state": v_def,
        "safe_preamp": gui.safe_preamp(v_def),
        "config_preamp": _preamp_from_config(gui.build_config(v_def)),
        "config_text": gui.build_config(v_def)
    }

    md5 = _md5(os.path.join(DESKTOP_DIR, "vocal_focus_gui.py"))
    data["desktop_md5"] = md5
    if os.path.exists(os.path.join(DESKTOP_DIR, "state.json")):
        data["desktop_state_json"] = open(os.path.join(DESKTOP_DIR, "state.json"),
                                          encoding="utf-8").read()

    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("wrote " + out)
    print("desktop vocal_focus_gui.py md5 = " + md5)
    for name in PRESETS:
        p = data["presets"][name]
        print("  %-6s safe_preamp=%7.3f dB  config_preamp=%7.3f dB  mid(3k)=%+5.2f dB"
              % (name, p["safe_preamp"], p["config_preamp"],
                 _at(p["mid_db"], freqs, 3000.0)))


def _at(vals, freqs, f):
    return vals[min(range(len(freqs)), key=lambda i: abs(freqs[i] - f))]


def _preamp_from_config(text):
    for line in text.splitlines():
        m = re.match(r"^Preamp:\s*(-?[\d.]+)\s*dB$", line.strip())
        if m:
            return float(m.group(1))
    return None


def _md5(path):
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


if __name__ == "__main__":
    main()
