#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只切「女聲前移 開 / 關」，其餘參數一個都不動。

為什麼需要這支：房間量測要比較「甜嗓開」與「原聲」兩條曲線，而兩次量測之間
**麥克風一毫米都不能動**。叫人走過去按介面上的【原聲 A/B】就毀了整個量測
（實測：耳麥移動造成的誤差 3.18 dB，比要量的訊號本身還大）。

走的路徑跟 set_preset.py 完全相同：讀 state → 改 on → build_config() → write_files()
→ 收尾逐行比對 live 檔。不手改 live 檔（專案鐵則 2）。

用法：
    python set_bypass.py --off          # 切到原聲（on=False）
    python set_bypass.py --on           # 切回女聲前移（on=True）
    python set_bypass.py --status       # 只看現在的狀態，不動任何東西
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
    spec.loader.exec_module(m)        # 只是定義，不建視窗
    return m


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--on", action="store_true")
    g.add_argument("--off", action="store_true")
    g.add_argument("--status", action="store_true")
    a = ap.parse_args()

    mod = load_mod()
    cur = json.load(open(STATE, encoding="utf-8"))
    cfg = open(mod.CONFIG_TXT, encoding="utf-8").read()
    active = [l.strip() for l in cfg.splitlines()
              if l.strip() and not l.lstrip().startswith("#")]

    if a.status:
        print(f"state.json on = {cur['on']}")
        print(f"config.txt 有效行 = {active}")
        print(f"一致: {bool(active) == bool(cur['on'])}")
        return 0

    want_on = bool(a.on)
    if cur["on"] == want_on:
        print(f"已經是 on={want_on}，不動任何東西")
        return 0

    new = dict(cur)
    new["on"] = want_on
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    # 備份（跟 set_preset 一樣，失敗要能退回）
    for p in [STATE, os.path.join(APO, "sweetvox_custom.txt"), os.path.join(APO, "config.txt")]:
        if os.path.exists(p):
            b = f"{p}.bak-{ts}-before-bypass"
            shutil.copy2(p, b)
            print(f"備份 {os.path.basename(p)} → {os.path.basename(b)}  md5(舊) {md5(p)}")

    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(new, f, ensure_ascii=False, indent=2)
    ok, msg = mod.write_files(new)
    print("write_files:", ok, msg)

    # 收尾驗收：build_config(state) 必須逐行等於 live 檔
    live = open(mod.CUSTOM, encoding="utf-8").read()
    want = mod.build_config(new)
    strip = lambda s: [l for l in s.splitlines() if not l.startswith("# 甜嗓 SweetVox")]
    d_live, d_want = strip(live), strip(want)
    diff = [(i, x, y) for i, (x, y) in enumerate(zip(d_live, d_want)) if x != y]
    cfg2 = open(mod.CONFIG_TXT, encoding="utf-8").read()
    active2 = [l.strip() for l in cfg2.splitlines()
               if l.strip() and not l.lstrip().startswith("#")]
    st = json.load(open(STATE, encoding="utf-8"))
    print(f"驗收：build_config 逐行差異 {len(diff)} 行（要 0）")
    print(f"      config.txt 有效行 {active2}")
    print(f"      state 落地正確 {st == new}，on = {st['on']}")
    print(f"      其餘參數未變 {all(st[k] == cur[k] for k in cur if k != 'on')}")
    return 0 if (len(diff) == 0 and st == new) else 1


if __name__ == "__main__":
    raise SystemExit(main())
