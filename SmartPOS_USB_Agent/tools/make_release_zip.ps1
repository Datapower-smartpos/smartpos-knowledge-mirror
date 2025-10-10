<#!
SmartPOS USB Agent — сборка единого ZIP
Автор: Разработчик суперпрограмм
Запуск: powershell -ExecutionPolicy Bypass -File tools/make_release_zip.ps1
#>
param([string]$Version='1.4.1')
$ErrorActionPreference='Stop'
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root 'dist'
$new = Join-Path $dist ("SmartPOS_USB_Agent_v$Version.zip")
if(!(Test-Path $dist)){ New-Item -ItemType Directory -Path $dist | Out-Null }
if(Test-Path $new){ Remove-Item $new -Force }

$include = @(
  'src\python\smartpos_usb_service_v14.py',
  'src\python\usb_agent_core.py',
  'src\python\trace_wrappers_v2.py',
  'src\python\usb_devctl_cli.py',
  'installer\inno\SmartPOS_USB_Agent.iss',
  'installer\wix\SmartPOS_USB_Agent.wxs',
  'installer\scripts\install_service.ps1',
  'installer\scripts\uninstall_service.ps1',
  'tools\install_watchdog.ps1',
  'tools\uninstall_watchdog.ps1',
  'tools\ux\SmartPOS-USB-UX.ps1',
  'tests\*',
  'docs\README_FULL.md',
  'docs\ops\README_ops_short.md',
  'examples_pack\README_and_samples.txt'
)
$files = $include | ForEach-Object { Join-Path $root $_ }

# Сжимаем
$zipTmp = Join-Path $env:TEMP ("spusb_" + [guid]::NewGuid().ToString('N') + '.zip')
if(Test-Path $zipTmp){ Remove-Item $zipTmp -Force }
Compress-Archive -Path $files -DestinationPath $zipTmp -Force
Move-Item $zipTmp $new -Force
Write-Host "ZIP: $new"

# SHA256
$h = Get-FileHash -Path $new -Algorithm SHA256
$sha = $h.Hash.ToLower()
$shaFile = $new + '.sha256.txt'
"$sha  $(Split-Path -Leaf $new)" | Set-Content -Path $shaFile -Encoding ASCII
Write-Host "SHA256: $sha"

