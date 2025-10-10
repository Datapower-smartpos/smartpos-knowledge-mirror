Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$cfg = Get-Content "$PSScriptRoot\config.json" | ConvertFrom-Json
$apiKey = $cfg.api_key
$icon = New-Object System.Windows.Forms.NotifyIcon
$icon.Icon = [System.Drawing.SystemIcons]::Information
$icon.Visible = $true
$icon.Text = 'SmartPOS Tray'
$menu = New-Object System.Windows.Forms.ContextMenuStrip


function Call([string]$url, [bool]$auth=$false){
try{
$wc = New-Object System.Net.WebClient
if($auth){ $wc.Headers.Add('X-API-Key',$apiKey) }
return $wc.DownloadString($url)
} catch { return $_.Exception.Message }
}


$mi1 = $menu.Items.Add('Статус / Status')
$mi1.add_Click({ [System.Windows.Forms.MessageBox]::Show((Call 'http://127.0.0.1:11888/api/status')) })


$mi2 = $menu.Items.Add('Экспорт (WER,ETL,LOG,DB,EventLog)')
$mi2.add_Click({
$r = Call 'http://127.0.0.1:11888/api/export?mask=wer,etl,logs,db,eventlog' $true
[System.Windows.Forms.MessageBox]::Show($r, 'Export')
})


$miEVT = $menu.Items.Add('Экспорт EventLog (EVTX/CSV)')
$miEVT.add_Click({
try {
Start-Process powershell -Verb runAs -WindowStyle Hidden -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\\eventlog_export\\export_eventlog.ps1`""
} catch {
[System.Windows.Forms.MessageBox]::Show($_.Exception.Message,'EventLog export')
}
})


$mi3 = $menu.Items.Add('Включить WER/ETW')
$mi3.add_Click({
Start-Process powershell -Verb runAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\\enable_wer.ps1`""
Start-Process powershell -Verb runAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\\enable_etw.ps1`""
})


$mi4 = $menu.Items.Add('Откат изменений')
$mi4.add_Click({
Start-Process powershell -Verb runAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\\disable_wer.ps1`""
Start-Process powershell -Verb runAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\\disable_etw.ps1`""
})


$mi5 = $menu.Items.Add('Выход / Exit')
$mi5.add_Click({ $icon.Visible=$false; [System.Windows.Forms.Application]::Exit() })


$icon.ContextMenuStrip = $menu
[System.Windows.Forms.Application]::Run()