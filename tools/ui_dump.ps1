# 啟動 Equalizer APO DeviceSelector 並列出它的 UI 元件（用 UI Automation，逐項印名稱）
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Start-Process "C:\Program Files\EqualizerAPO\DeviceSelector.exe"
Start-Sleep -Seconds 4

$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Window)
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)

$found = $false
foreach ($w in $wins) {
    $n = $w.Current.Name
    if ($n -match 'Equalizer|Configurator|Device|APO') {
        $found = $true
        "WINDOW: '$n'  class=$($w.Current.ClassName)"
        $all = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                          [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($e in $all) {
            "  [{0}] name='{1}' id='{2}' enabled={3}" -f `
                $e.Current.ControlType.ProgrammaticName, $e.Current.Name, $e.Current.AutomationId, $e.Current.IsEnabled
        }
    }
}
if (-not $found) {
    "沒找到視窗，目前所有頂層視窗："
    foreach ($w in $wins) { "  '$($w.Current.Name)' class=$($w.Current.ClassName)" }
}
