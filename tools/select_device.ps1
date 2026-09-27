# 在 Equalizer APO Device Selector 裡把「喇叭 (Audiolab M-DAC)」的安裝勾選打開
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class M {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, int e);
  public static void Click(int x, int y) {
    SetCursorPos(x, y);
    System.Threading.Thread.Sleep(250);
    mouse_event(0x0002, 0, 0, 0, 0);   // left down
    System.Threading.Thread.Sleep(80);
    mouse_event(0x0004, 0, 0, 0, 0);   // left up
  }
}
"@

function Get-Win {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'DeviceSelector')
    $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
}

$w = Get-Win
if (-not $w) { "找不到 Device Selector 視窗"; exit 1 }
"視窗: $($w.Current.Name)"

$items = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::TreeItem)))

$target = $null
foreach ($it in $items) {
    if ($it.Current.Name -eq 'Audiolab M-DAC') { $target = $it }
}
if (-not $target) { "找不到 Audiolab M-DAC 那一列"; exit 1 }

$r = $target.Current.BoundingRectangle
"目標列: name='$($target.Current.Name)' rect=$([int]$r.Left),$([int]$r.Top) w=$([int]$r.Width) h=$([int]$r.Height)"
"支援的 pattern:"
foreach ($p in $target.GetSupportedPatterns()) { "   " + $p.ProgrammaticName }

# 先試 TogglePattern
$tp = $null
try { $tp = $target.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern) } catch {}
if ($tp) {
    "有 TogglePattern，目前狀態=$($tp.Current.ToggleState)"
    if ($tp.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::On) {
        $tp.Toggle(); Start-Sleep -Milliseconds 500; "切換後狀態=$($tp.Current.ToggleState)"
    }
} else {
    "沒有 TogglePattern -> 用滑鼠點勾選框（列的最左邊）"
    $x = [int]($r.Left + 12); $y = [int]($r.Top + $r.Height / 2)
    "點擊座標: $x,$y"
    [M]::Click($x, $y)
    Start-Sleep -Milliseconds 400
    # 再點一次同一列的裝置名稱，確保焦點在這一列
    [M]::Click([int]($r.Left + 60), $y)
    Start-Sleep -Milliseconds 300
}

# 回報那一列的狀態文字（勾選狀態會顯示成子項目或名稱）
Start-Sleep -Milliseconds 600
$items2 = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::TreeItem)))
"--- 目前樹上 M-DAC / 喇叭 相關列 ---"
$i = 0
foreach ($it in $items2) {
    if ($it.Current.Name -match 'M-DAC|喇叭|APO') { "  [$i] '$($it.Current.Name)'"; }
    $i++
}
$ok = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, 'OK')))
if ($ok) { "OK 按鈕 enabled=$($ok.Current.IsEnabled)" } else { "找不到 OK 按鈕" }
