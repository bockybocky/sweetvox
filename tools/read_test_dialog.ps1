# 讀測試對話框的說明文字與每個裝置的 Pre-mix/Post-mix 狀態，然後按 OK 結束
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$w = $root.FindFirst([System.Windows.Automation.TreeScope]::Children,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'DeviceTestDialog')))
if (-not $w) { "測試對話框已關閉"; exit 0 }

foreach ($e in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Edit)))) {
    try {
        $v = $e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
        "Edit 內容: $v"
    } catch { "Edit 讀不到值: $($e.Current.Name)" }
}
"--- 樹上每一格的值 ---"
foreach ($it in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::TreeItem)))) {
    $val = ''
    try { $val = $it.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value } catch {}
    $name = $it.Current.Name
    if ($name -ne '' -or $val -ne '') { "  '$name' = '$val'" }
}
$ok = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, 'OK')))
if ($ok -and $ok.Current.IsEnabled) {
    $ok.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    ">> 已按測試對話框的 OK"
}
