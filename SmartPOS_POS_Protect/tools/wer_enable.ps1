#requires -RunAsAdministrator
<#
.SYNOPSIS
  Enables Windows Error Reporting (WER) and configures local dumps suitable for POS diagnostics.
  - Ensures WER service is available
  - Enables global LocalDumps with retention/size
  - Leaves per-app overrides possible later (HKLM\...\LocalDumps\<exe>.exe)
#>

Write-Host "== SmartPOS POS Protect: enabling WER local dumps ==" -ForegroundColor Cyan

# Enable Windows Error Reporting globally
New-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting" -Name "Disabled" -Type DWord -Value 0

# Global LocalDumps
$ld = "HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps"
New-Item -Path $ld -Force | Out-Null
Set-ItemProperty -Path $ld -Name "DumpFolder" -Type ExpandString -Value "C:\ProgramData\Microsoft\Windows\WER\LocalDumps"
Set-ItemProperty -Path $ld -Name "DumpCount"  -Type DWord -Value 50
# 1 = MiniDump, 2 = FullDump. Start with Mini to reduce footprint
Set-ItemProperty -Path $ld -Name "DumpType"   -Type DWord -Value 1

# Ensure folders exist
New-Item -ItemType Directory -Path "C:\ProgramData\Microsoft\Windows\WER\LocalDumps" -Force | Out-Null

# Make sure WER service is running
Try {
  Set-Service -Name "WerSvc" -StartupType Manual
  Start-Service -Name "WerSvc" -ErrorAction SilentlyContinue
} Catch {}

Write-Host "WER enabled. Local dumps will be written to C:\ProgramData\Microsoft\Windows\WER\LocalDumps"
