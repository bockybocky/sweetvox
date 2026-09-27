# v5：按 OK 送出裝置選擇，然後回報有沒有跳出「重啟／重開機」對話框
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Get-Win($cls) {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $root.FindFirst([System.Windows.Automation.TreeScope]::Children,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, $cls)))
}

$w = Get-Win 'DeviceSelector'
if (-not $w) { "找不到 Device Selector（可能已經關了）"; exit 0 }

$ok = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, 'OK')))
if (-not $ok) { "找不到 OK"; exit 1 }
"OK enabled=$($ok.Current.IsEnabled)，按下 OK"
$ok.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Seconds 3

"--- Device Selector 還在嗎 ---"
$w2 = Get-Win 'DeviceSelector'
if ($w2) { "還在" } else { "已關閉（送出成功）" }

"--- 有沒有跳出對話框 ---"
$root = [System.Windows.Automation.AutomationElement]::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Window)))
foreach ($x in $wins) {
    if ($x.Current.Name -ne '' -and $x.Current.ClassName -ne 'DeviceSelector') {
        "  視窗: '$($x.Current.Name)' class=$($x.Current.ClassName)"
    }
}
