# 開啟 Equalizer APO 的追蹤記錄，重啟音訊服務，然後把 log 印出來
# 目的：確認 EqualizerAPO.dll 到底有沒有掛到 Audiolab M-DAC 這條路徑上、有沒有讀到我們的設定檔
$key = 'HKLM:\SOFTWARE\EqualizerAPO'
Set-ItemProperty -Path $key -Name 'EnableTrace' -Value 1 -Type DWord
"EnableTrace = " + (Get-ItemProperty $key).EnableTrace

$log = 'C:\Windows\ServiceProfiles\LocalService\AppData\Local\Temp\EqualizerAPO.log'
if (Test-Path $log) {
    Rename-Item $log ("EqualizerAPO.log.before-trace-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
Restart-Service Audiosrv -Force
Start-Sleep -Seconds 4
"音訊服務已重啟：" + (Get-Service Audiosrv).Status
"--- log 內容 ---"
if (Test-Path $log) { Get-Content $log | Select-Object -Last 40 } else { "(log 還沒產生——代表 APO 完全沒被載入)" }
