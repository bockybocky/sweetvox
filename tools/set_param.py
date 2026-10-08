#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改單一參數（實驗用），走跟 set_preset.py 相同的路徑。

為什麼需要：房間量測顯示 63–200 Hz 隆起 +6～+14 dB，需要「削」低頻；
但介面的「溫暖」滑桿範圍是 0.0~4.0，**只能加不能削**（當初沒量過房間，不知道要削）。
這支用來在**改程式之前**先驗證「削下去是不是真的比較好」。

⚠ 設成滑桿範圍外的值時，介面若被操作會把值夾回去 —— 測試期間不要動那根滑桿。

用法：
    python set_param.py --set warm=-5.0
    python set_param.py --set warm=1.0 --set air=1.0
    python set_param.py --show
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import shutil

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
GUI = os.path.join(APP, "vocal_focus_gui.py")
STATE = os.path.join(APP, "state.json")
APO = r"C:\Program Files\EqualizerAPO\config"


def load_mod():
    spec = importlib.util.spec_from_file_location("vgui", GUI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", action="append", default=[], metavar="鍵=值")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    mod = load_mod()
    cur = json.load(open(STATE, encoding="utf-8"))
    if a.show or not a.set:
        print(json.dumps(cur, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    new = dict(cur)
    for kv in a.set:
        k, _, v = kv.partition("=")
        k = k.strip()
        # 新加的參數（例如 room63）還不在他的 state.json 裡，但在程式的 DEFAULTS 裡 → 也要能設
        if k not in cur and k not in mod.DEFAULTS:
            print(f"沒有這個參數：{k}（可用：{sorted(set(cur) | set(mod.DEFAULTS))}）")
            return 2
        old = cur[k] if k in cur else mod.DEFAULTS[k]
        new[k] = (v.strip().lower() == "true") if isinstance(old, bool) else type(old)(v)
        print(f"{k}: {old} → {new[k]}")

    print("build_config 的 MID 段：")
    for line in mod.build_config(new).splitlines():
        if line.startswith("Filter") or line.startswith("Preamp"):
            print("   " + line)
    if a.dry_run:
        print("(dry-run，沒有寫任何檔)")
        return 0

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for p in [STATE, os.path.join(APO, "sweetvox_custom.txt"), os.path.join(APO, "config.txt")]:
        if os.path.exists(p):
            b = f"{p}.bak-{ts}-before-param"
            shutil.copy2(p, b)
            print(f"備份 {os.path.basename(p)}  md5(舊) {md5(p)}")

    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(new, f, ensure_ascii=False, indent=2)
    ok, msg = mod.write_files(new)
    print("write_files:", ok, msg)

    live = open(mod.CUSTOM, encoding="utf-8").read()
    want = mod.build_config(new)
    strip = lambda s: [l for l in s.splitlines() if not l.startswith("# 甜嗓 SweetVox")]
    diff = [1 for x, y in zip(strip(live), strip(want)) if x != y]
    st = json.load(open(STATE, encoding="utf-8"))
    print(f"驗收：build_config 逐行差異 {len(diff)} 行（要 0）；state 落地正確 {st == new}")
    return 0 if (not diff and st == new) else 1


if __name__ == "__main__":
    raise SystemExit(main())
