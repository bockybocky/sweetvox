"""介面版面自檢：把調整台開起來（不顯示在螢幕上），檢查有沒有元件被視窗切掉。
用法: sep/.venv/Scripts/python.exe tools/check_layout.py   （hermes venv 的 python 也可）
"""
import importlib.util
import tkinter as tk

spec = importlib.util.spec_from_file_location(
    "g", r"E:\AI\workspace\vocal_focus\app\vocal_focus_gui.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

root = tk.Tk()
root.withdraw()                      # 不要搶螢幕焦點
app = g.App(root)
root.update_idletasks()
root.update()
W, H = root.winfo_width(), root.winfo_height()
print(f"視窗 {W}x{H}   內容需要高度 {root.winfo_reqheight()}")

bad = []


def walk(w, depth=0):
    for c in w.winfo_children():
        y = c.winfo_rooty() - root.winfo_rooty()
        x = c.winfo_rootx() - root.winfo_rootx()
        wd, h = c.winfo_width(), c.winfo_height()
        txt = ""
        try:
            txt = str(c.cget("text"))[:22]
        except Exception:
            pass
        if (h > 1 and y + h > H + 1) or (wd > 1 and x + wd > W + 1) or y > H:
            bad.append((c.winfo_class(), txt, x, y, wd, h))
        walk(c, depth + 1)


walk(root)

# 文字被切（元件實際大小 < 內容需要大小）＝字會被吃掉
tight = []
def walk2(w):
    for c in w.winfo_children():
        try:
            rw, rh = c.winfo_reqwidth(), c.winfo_reqheight()
            aw, ah = c.winfo_width(), c.winfo_height()
            txt = str(c.cget("text"))[:20]
        except Exception:
            walk2(c); continue
        if c.winfo_class() in ("Button", "Label", "Checkbutton") and aw > 1 and (aw + 2 < rw or ah + 2 < rh):
            tight.append((c.winfo_class(), txt, aw, rw, ah, rh))
        walk2(c)

walk2(root)
if tight:
    print(f"\n文字可能被切 {len(tight)} 個：")
    for cls, txt, aw, rw, ah, rh in tight:
        print(f"   {cls:<10s} {txt:<22s} 實寬 {aw:4d}/需 {rw:4d}   實高 {ah:3d}/需 {rh:3d}")
else:
    print("\n所有文字都放得下 ✓")

if bad:
    print(f"\n被切到的元件 {len(bad)} 個：")
    for cls, txt, x, y, wd, h in bad:
        print(f"   {cls:<10s} {txt:<24s} x={x:5d} y={y:5d} w={wd:4d} h={h:4d}  (底 {y+h} > {H})")
else:
    print("\n沒有元件被切掉 ✓")

# 檢查所有可互動元件都在視窗內且大小正常
n_btn = sum(1 for w in root.winfo_children() for c in w.winfo_children() if c.winfo_class() == "Button")
n_scale = len(getattr(app, "sliders", {})) + 1
print(f"\n按鈕 {n_btn} 顆、滑桿 {n_scale} 根、勾選框 {len([1 for f in root.winfo_children() for c in f.winfo_children() if c.winfo_class()=='Checkbutton'])} 個")
print(f"模式鈕：{list(getattr(app, 'preset_btns', {}).keys())}")
root.destroy()
