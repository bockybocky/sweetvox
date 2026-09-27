# 看「Testing APO installation」對話框現在的狀態（是否在等人按按鈕）
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'DeviceTestDialog')))
if ($wins.Count -eq 0) { "DeviceTestDialog 已經不存在（測試結束）"; exit 0 }
foreach ($w in $wins) {
    "對話框: '$($w.Current.Name)'"
    $all = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($e in $all) {
        $ct = $e.Current.ControlType.ProgrammaticName -replace 'ControlType\.',''
        "  [$ct] name='$($e.Current.Name)' enabled=$($e.Current.IsEnabled)"
    }
}
