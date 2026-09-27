#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""套用甜嗓的模式鈕（跟介面 apply_preset() 走同一條路徑，不改任何 DSP 程式碼）。

用途：Charles 說「切到 <模式>」時用，不必手動按介面。
- 讀 app\\state.json（他當下的值）→ 套模式（布林旗標先回 DEFAULTS，再 update PRESETS[name]，on=True）
- 寫回 state.json ＋ 立刻寫 live 設定檔（C:\\Program Files\\EqualizerAPO\\config\\…）
- --launch 另外把調整台開起來（Hermes 本身是管理員，所以不需要 UAC）

用法：
    python set_preset.py 發燒 --dry-run        # 只看會變成什麼、會寫什麼，不動檔
    python set_preset.py 發燒                  # 套用（備份 state 與 live 檔）
    python set_preset.py 發燒 --launch         # 套用 ＋ 開調整台
"""
import argparse, datetime, hashlib, importlib.util, json, os, shutil, subprocess, sys, time

APP   = r"E:\AI\workspace\vocal_focus\app"
GUI   = os.path.join(APP, "vocal_focus_gui.py")
STATE = os.path.join(APP, "state.json")
APO   = r"C:\Program Files\EqualizerAPO\config"
PYW   = r"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe"
PY    = r"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
RUNPY = PYW if os.path.exists(PYW) else PY      # 這個 venv 沒有 pythonw.exe（實測），退回 python.exe


def load_mod():
    spec = importlib.util.spec_from_file_location("vgui", GUI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)          # 只是定義；不建視窗
    return m


def preset_state(mod, name, cur):
    """複製 App.apply_preset() 的語意（他當下的值 → 套模式）。"""
    v = dict(cur)
    for k, val in mod.DEFAULTS.items():          # 模式旗標先回預設，否則上一個模式的 piano/side_band 會殘留
        if isinstance(val, bool) and k != "on":
            v[k] = val
    v.update(mod.PRESETS[name])
    v["on"] = True
    return v


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def backup(paths, tag):
    out = []
    for p in paths:
        if os.path.exists(p):
            b = p + ".bak-" + tag
            if not os.path.exists(b):
                shutil.copy2(p, b)
            out.append((p, b, md5(p)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("preset")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--launch", action="store_true")
    a = ap.parse_args()

    mod = load_mod()
    if a.preset not in mod.PRESETS:
        print("沒有這個模式：", list(mod.PRESETS)); return 2

    cur = json.load(open(STATE, encoding="utf-8"))
    new = preset_state(mod, a.preset, cur)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    print("== 他現在這組 ==");  print(json.dumps(cur, ensure_ascii=False, sort_keys=True))
    print("== 套用「%s」後 ==" % a.preset); print(json.dumps(new, ensure_ascii=False, sort_keys=True))
    print("changed:", {k: (cur.get(k), new.get(k)) for k in set(cur) | set(new) if cur.get(k) != new.get(k)})
    print("build_config 首四行：")
    print("\n".join(mod.build_config(new).splitlines()[:4]))
    print("applied_preamp = %.2f dB（safe_preamp %.2f）" % (mod.applied_preamp(new), mod.safe_preamp(new)))
    print("開機模式判定 =", mod.App._match_preset(new))
    if a.dry_run:
        print("(dry-run，沒有寫任何檔)"); return 0

    print("== 備份 ==")
    for p, b, h in backup([STATE] + [os.path.join(APO, f) for f in
                                    ("sweetvox_custom.txt", "config.txt")],
                          "20260926-before-" + a.preset):
        print("  %s\n    → %s\n    md5(舊) %s" % (p, b, h))

    with open(STATE, "w", encoding="utf-8") as f:      # 先落地 state，之後介面開起來讀到的是這一組
        json.dump(new, f, ensure_ascii=False, indent=2)

    ok, msg = mod.write_files(new)                     # 立刻寫 live 設定檔（不用等介面）
    print("write_files:", ok, msg)

    # ---- 驗收 ----
    live = open(mod.CUSTOM, encoding="utf-8").read()
    want = mod.build_config(new)
    strip = lambda s: [l for l in s.splitlines() if not l.startswith("# 甜嗓 SweetVox")]
    d_live, d_want = strip(live), strip(want)
    diff = [(i, x, y) for i, (x, y) in enumerate(zip(d_live, d_want)) if x != y]
    print("A2 live 檔 vs build_config：行數 %d/%d、差異 %d 行" % (len(d_live), len(d_want), len(diff)))
    for i, x, y in diff[:5]:
        print("   line%d\n     live: %s\n     want: %s" % (i, x, y))
    cfg = open(mod.CONFIG_TXT, encoding="utf-8").read()
    active = [l.strip() for l in cfg.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    print("A3 config.txt 有效行:", active)
    st = json.load(open(STATE, encoding="utf-8"))
    print("A1 state 落地等於新值:", st == new)

    if a.launch:
        p = subprocess.Popen([PYW, GUI], cwd=APP, close_fds=True,
                             creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP
        print("已開調整台 pid", p.pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
