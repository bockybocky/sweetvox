# 列出所有播放端點：名稱、GUID、以及 FxProperties 裡有沒有掛 EqualizerAPO
$root = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render'
$apo = @('{EACD2258-FCAC-4FF4-B36D-419E924A6D79}', '{EC1CC9CE-FAED-4822-828A-82A81A6F018F}')
$nameKey = '{a45c254e-df1c-4efd-8020-67d146a850e0},2'
$descKey = '{b3f8fa53-0004-438e-9003-51a46e139bfc},6'

Get-ChildItem -LiteralPath $root | ForEach-Object {
    $guid = $_.PSChildName
    $props = Get-ItemProperty -LiteralPath (Join-Path $_.PSPath 'Properties') -ErrorAction SilentlyContinue
    $fx = Get-ItemProperty -LiteralPath (Join-Path $_.PSPath 'FxProperties') -ErrorAction SilentlyContinue
    $name = ''
    if ($props) { $name = $props.$nameKey }
    $state = (Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue).DeviceState
    $hasApo = $false
    $detail = @()
    if ($fx) {
        foreach ($p in $fx.PSObject.Properties) {
            if ($p.Name -like 'PS*') { continue }
            if ($apo -contains $p.Value) { $hasApo = $true }
            if ($p.Name -like '{d04e05a6*') { $detail += "$($p.Name)=$($p.Value)" }
        }
    }
    $mark = if ($hasApo) { '<<< 有掛 Equalizer APO' } else { '' }
    "{0}  state={1}  {2}  {3}" -f $guid, $state, $name, $mark
    if ($detail.Count -gt 0) { "      " + ($detail -join '  ') }
}
