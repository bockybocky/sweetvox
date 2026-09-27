# 讀出「現在正在播什麼音樂」：優先用 Windows SMTC（Chrome/YouTube Music 會發佈媒體資訊），失敗才退回視窗標題
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $t) {
    $m = $asTaskGeneric.MakeGenericMethod($t)
    $task = $m.Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}

try {
    [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime] | Out-Null
    $mgrType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]
    $mgr = Await ($mgrType::RequestAsync()) $mgrType
    $sessions = $mgr.GetSessions()
    if ($sessions.Count -eq 0) { "SMTC: 沒有媒體工作階段（可能沒在播，或播放器不支援）" }
    foreach ($s in $sessions) {
        $propsType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties]
        $p = Await ($s.TryGetMediaPropertiesAsync()) $propsType
        $tl = $s.GetTimelineProperties()
        $status = $s.GetPlaybackInfo().PlaybackStatus
        "SMTC: [{0}] {1} - {2} ({3}) 位置 {4:N0}s / 全長 {5:N0}s" -f `
            $s.SourceAppUserModelId, $p.Title, $p.Artist, $status, $tl.Position.TotalSeconds, $tl.EndTime.TotalSeconds
    }
} catch {
    "SMTC 讀取失敗：$($_.Exception.Message)"
}

"--- Chrome 視窗標題（含分頁標題）---"
Get-Process chrome -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -ne '' } |
    ForEach-Object { "  $($_.MainWindowTitle)" }
