Add-Type -AssemblyName System.Windows.Forms, System.Drawing
# 宣告 DPI 感知，否則截圖會被系統放大重畫（拍出來的字會糊、視窗也會對不上位置）
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class Dpi {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@ -ErrorAction SilentlyContinue
[void][Dpi]::SetProcessDPIAware()
$sig = @'
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern IntPtr FindWindow(string c, string n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
'@
Add-Type -TypeDefinition $sig -ErrorAction SilentlyContinue

$h = [IntPtr]::Zero
foreach ($p in Get-Process pythonw -ErrorAction SilentlyContinue) {
  if ($p.MainWindowTitle -like "*SweetVox*" -or $p.MainWindowTitle -like "*甜嗓*") { $h = $p.MainWindowHandle }
}
if ($h -eq [IntPtr]::Zero) { Write-Output "找不到視窗"; exit 1 }
[void][W]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 600
$r = New-Object W+RECT
[void][W]::GetWindowRect($h, [ref]$r)
$w = $r.Right - $r.Left; $ht = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap $w, $ht
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$out = "E:\AI\workspace\vocal_focus\gui_sweetvox.png"
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output "$out  ($w x $ht)"
