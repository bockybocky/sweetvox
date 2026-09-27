# v3：印出每一列的實際座標（含無名子列），找出勾選框到底在哪個 x，再精準點它
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class M3 {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, int e);
  [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(int x, int y);
  public static void Click(int x, int y) {
    SetCursorPos(x, y); System.Threading.Thread.Sleep(200);
    mouse_event(0x0002,0,0,0,0); System.Threading.Thread.Sleep(80); mouse_event(0x0004,0,0,0,0);
  }
  public static long WinAt(int x, int y) { return (long)WindowFromPoint(x, y); }
}
"@

function Get-Win {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $root.FindFirst([System.Windows.Automation.TreeScope]::Children,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'DeviceSelector')))
}
function Dump($w, $tag) {
    "=== $tag ==="
    $items = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::TreeItem)))
    foreach ($it in $items) {
        $r = $it.Current.BoundingRectangle
        $ct = $it.Current.ControlType.ProgrammaticName -replace 'ControlType\.',''
        "  [{0}] '{1}' x={2} y={3} w={4} h={5}" -f $ct, $it.Current.Name, [int]$r.Left, [int]$r.Top, [int]$r.Width, [int]$r.Height
    }
    $ok = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty, 'OK')))
    if ($ok) { "  OK enabled=$($ok.Current.IsEnabled)" }
}

$w = Get-Win
if (-not $w) { "找不到視窗"; exit 1 }
"視窗矩形: $([int]$w.Current.BoundingRectangle.Left),$([int]$w.Current.BoundingRectangle.Top) w=$([int]$w.Current.BoundingRectangle.Width) h=$([int]$w.Current.BoundingRectangle.Height)"
Dump $w "目前"
"桌面在 (1780,1010) 的視窗 handle = $([M3]::WinAt(1780,1010))"
