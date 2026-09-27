# v4：勾選框在「Connector」欄（x≈1490），不是 Device 欄。沿該欄點擊直到 OK 亮起
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class M4 {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, int e);
  public static void Click(int x, int y) {
    SetCursorPos(x, y); System.Threading.Thread.Sleep(180);
    mouse_event(0x0002,0,0,0,0); System.Threading.Thread.Sleep(70); mouse_event(0x0004,0,0,0,0);
  }
}
"@

function Get-Win {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $root.FindFirst([System.Windows.Automation.TreeScope]::Children,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'DeviceSelector')))
}
function Status($w) {
    $it = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::TreeItem)))
    $out = @()
    foreach ($i in $it) { if ($i.Current.Name -match '^APO') { $out += $i.Current.Name } }
    $ok = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty, 'OK')))
    ($out -join ' | ') + "   >>> OK enabled=" + $ok.Current.IsEnabled
}

$w = Get-Win
if (-not $w) { "找不到視窗"; exit 1 }
$hwnd = [IntPtr]$w.Current.NativeWindowHandle
[M4]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 400
"起點: $(Status $w)"

$y = 1010   # Audiolab M-DAC 那一列的中心 y
foreach ($x in 1490, 1498, 1506, 1482, 1474, 1466) {
    [M4]::Click($x, $y)
    Start-Sleep -Milliseconds 500
    $s = Status $w
    "點 ($x,$y) -> $s"
    if ($s -match 'enabled=True') { ">>> 已經勾選成功，停止嘗試"; break }
}
