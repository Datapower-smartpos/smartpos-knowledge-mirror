# SmartPOS USB Agent — install_service.ps1 (v1.4.1)
# Устанавливает Windows-службу "SmartPOS_USB_Service" через sc.exe и запускает её.
# Без интерактивных запросов. Конфиг создаётся инсталлятором в %ProgramData%\SmartPOS\usb_agent\config.json

[CmdletBinding()]
param(
  [string]$ServiceName   = 'SmartPOS_USB_Service',
  [string]$PythonExe     = 'pythonw.exe',
  [string]$ScriptRelPath = 'src\python\smartpos_usb_service_v14.py',
  [switch]$ForceReinstall
)

$ErrorActionPreference = 'Stop'

function Info($m){ Write-Host "[INFO] $m" }
function Warn($m){ Write-Warning $m }
function Fail($m){ Write-Error $m }

try {
  $base  = Split-Path -Parent $PSScriptRoot
  $root  = Split-Path -Parent $base
  $script = Join-Path $root $ScriptRelPath
  if (-not (Test-Path $script)) { throw "Service script not found: $script" }

  $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
  if ($svc) {
    if ($ForceReinstall) {
      Info "Service exists, reinstall requested. Stopping..."
      try { Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1 } catch {}
      Info "Deleting service..."
      sc.exe delete $ServiceName | Out-Null
      Start-Sleep -Seconds 1
    } else {
      Info "Service already exists. Starting (if stopped)..."
      if ($svc.Status -ne 'Running') { Start-Service -Name $ServiceName -ErrorAction SilentlyContinue }
      exit 0
    }
  }

  $bin = "$PythonExe `"$script`""
  Info "Creating service $ServiceName with binPath=$bin"
  $create = sc.exe create $ServiceName binPath= "$bin" start= auto
  if ($LASTEXITCODE -ne 0) { throw "sc create failed: $($create | Out-String)" }

  sc.exe description $ServiceName "SmartPOS USB Agent Service" | Out-Null
  sc.exe failure $ServiceName reset= 86400 actions= restart/5000 | Out-Null

  Info "Starting service..."
  sc.exe start $ServiceName | Out-Null
  Start-Sleep -Seconds 1
  $svc2 = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
  if (-not $svc2 -or $svc2.Status -ne 'Running') { Warn "Service did not reach 'Running' state yet." }

  Write-Host "OK"
  exit 0
}
catch {
  Fail "Install failed: $($_.Exception.Message)"
  exit 1
}
