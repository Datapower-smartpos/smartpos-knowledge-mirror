$ErrorActionPreference='Stop'
$ts = Get-Date -Format yyyyMMdd_HHmm
$dst = "SmartPOS_POS-Protect_${ts}"
New-Item -ItemType Directory $dst | Out-Null
Copy-Item -Path *.ps1,*.reg,*.py,config.json,installer.iss,watchdog.xml -Destination $dst
Copy-Item -Path profiles,eventlog_export,tests,docs -Destination $dst -Recurse
Compress-Archive -Path $dst -DestinationPath "$dst.zip" -Force
(Get-FileHash "$dst.zip" -Algorithm SHA256).Hash | Out-File "$dst.zip.sha256"
Write-Host "[OK] Release ready: $dst.zip"