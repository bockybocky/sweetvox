param(
    [ValidateSet('off','light','med','strong','fallback')]
    [string]$Preset = 'med'
)
# 切換女聲前移的版本：改 config.txt 的 Include 行，Equalizer APO 會即時重載，不用重開機
$cfg = 'C:\Program Files\EqualizerAPO\config\config.txt'
$map = @{
    'off'      = ''
    'light'    = 'vocal_focus_light.txt'
    'med'      = 'vocal_focus_med.txt'
    'strong'   = 'vocal_focus_strong.txt'
    'fallback' = 'fallback_stereo_eq.txt'
}
$file = $map[$Preset]
if ([string]::IsNullOrEmpty($file)) {
    # off = 全部註解掉（等於原聲）
    $content = "# 女聲前移：目前關閉（off）`r`n# Include: vocal_focus_med.txt`r`n"
} else {
    $content = "# 女聲前移（切換時間：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')）`r`n" +
               "# 版本：$Preset`r`n" +
               "# 要 A/B 比較原聲：把下一行前面加 #、存檔即生效（不用重開機）`r`n" +
               "Include: $file`r`n"
}
$full = Join-Path 'C:\Program Files\EqualizerAPO\config' $file
if (-not [string]::IsNullOrEmpty($file) -and -not (Test-Path $full)) {
    "錯誤：找不到 $full，沒有改動 config.txt"
    exit 1
}
[System.IO.File]::WriteAllText($cfg, $content, (New-Object System.Text.UTF8Encoding($false)))
Start-Sleep -Milliseconds 300
# 寫完回去讀那一行，確認真的寫進去了
"--- 切到 $Preset，config.txt 現在是 ---"
Get-Content $cfg | ForEach-Object { "  $_" }
$check = Get-Content $cfg | Where-Object { $_ -match '^Include:' }
if ([string]::IsNullOrEmpty($file)) {
    if ($check) { "警告：預期沒有 Include 行，但有：$check" ; exit 1 }
    "驗證：已關閉（無 Include 行）"
} else {
    if ($check -eq "Include: $file") { "驗證：Include 行正確 = $file" }
    else { "警告：Include 行對不上，讀到：$check"; exit 1 }
}
