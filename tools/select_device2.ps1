# v2：改用「選取該列 + 空白鍵」切換勾選（Qt 樹狀清單的標準行為），失敗才試 Invoke，再失敗才精準滑鼠點
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class M2 {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, int e);
  public static void Click(int x, int y) {
    SetCursorPos(x, y); System.Threading.Thread.Sleep(250);
    mouse_event(0x0002,0,0,0,0); System.Threading.Thread.Sleep(80); mouse_event(0x0004,0,0,0,0);
  }
}
"@

function Get-Win {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'DeviceSelector')
    $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
}
function Show-Status($w, $tag) {
    $items = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::TreeItem)))
    "--- $tag ---"
    for ($i=0; $i -lt $items.Count; $i++) {
        $n = $items[$i].Current.Name
        if ($n -match 'M-DAC|喇叭|^APO') { "  [$i] '$n'" }
    }
    $ok = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty, 'OK')))
    if ($ok) { "  OK enabled=$($ok.Current.IsEnabled)" }
}

$w = Get-Win
if (-not $w) { "找不到視窗"; exit 1 }
$hwnd = [IntPtr]$w.Current.NativeWindowHandle

$items = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::TreeItem)))
$target = $null
for ($i=0; $i -lt $items.Count; $i++) { if ($items[$i].Current.Name -eq 'Audiolab M-DAC') { $target = $items[$i] } }
if (-not $target) { "找不到 M-DAC 列"; exit 1 }
$r = $target.Current.BoundingRectangle
Show-Status $w "動作前"

# 1) 選取 + 空白鍵
try {
    $sel = $target.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
    $sel.Select(); Start-Sleep -Milliseconds 300
    [M2]::SetForegroundWindow($hwnd) | Out-Null
    Start-Sleep -Milliseconds 300
    [System.Windows.Forms.SendKeys]::SendWait(" ")
    Start-Sleep -Milliseconds 800
    ">> 試過 選取+空白鍵"
} catch { ">> 選取+空白鍵 失敗: $_" }
Show-Status $w "空白鍵後"

# 2) Invoke
try {
    $inv = $target.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $inv.Invoke(); Start-Sleep -Milliseconds 800
    ">> 試過 Invoke"
} catch { ">> Invoke 失敗: $_" }
Show-Status $w "Invoke後"

# 3) 精準滑鼠：沿這一列左緣試幾個 x
foreach ($dx in 6, 14, 22, 30) {
    $x = [int]($r.Left + $dx); $y = [int]($r.Top + $r.Height/2)
    [M2]::SetForegroundWindow($hwnd) | Out-Null
    [M2]::Click($x, $y)
    Start-Sleep -Milliseconds 500
    ">> 試點 $x,$y"
}
Show-Status $w "滑鼠之後"
