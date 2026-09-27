# 叫出 Benchmark.exe 並列印它的介面元件
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Start-Process "C:\Program Files\EqualizerAPO\Benchmark.exe"
Start-Sleep -Seconds 4
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Window)
foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)) {
    $n = $w.Current.Name
    if ($n -match 'Benchmark|Equalizer') {
        "視窗: '$n' class=$($w.Current.ClassName)"
        $all = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                          [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($e in $all) {
            $ct = $e.Current.ControlType.ProgrammaticName -replace 'ControlType\.',''
            $val = ''
            try { $val = $e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value } catch {}
            "  [$ct] name='$($e.Current.Name)' id='$($e.Current.AutomationId)' val='$val' enabled=$($e.Current.IsEnabled)"
        }
    }
}
