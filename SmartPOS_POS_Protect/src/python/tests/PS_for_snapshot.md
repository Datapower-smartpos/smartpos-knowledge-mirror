Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# 0) Перейдём в корень репо на всякий случай
$repoRoot = (git rev-parse --show-toplevel).Trim()
Set-Location $repoRoot

# 1) Какие файлы включаем в снапшот
$files = @(
  "SmartPOS_POS_Protect/config/pos_protect_policies.json",
  "SmartPOS_POS_Protect/src/python/shared/pipeline.py",
  "SmartPOS_POS_Protect/src/python/collectors/wer_collect.py",
  "SmartPOS_POS_Protect/src/python/collectors/eventlog_collect.py",
  "SmartPOS_POS_Protect/src/python/analyzer/classifier.py",
  "SmartPOS_POS_Protect/src/python/cli/pos_protect_cli.py",
  "SmartPOS_POS_Protect/src/python/pos_protect_service.py"
) | Where-Object { Test-Path $_ }

# 2) Куда положим снапшот
$outDir = "SmartPOS_POS_Protect/.snapshot"
$out    = Join-Path $outDir "SNAPSHOT.md"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# 3) Соберём файл без бэктиков
"POS_Protect snapshot (branch: $(git rev-parse --abbrev-ref HEAD), commit: $(git rev-parse --short HEAD))" | Set-Content -Path $out -Encoding UTF8
"Generated: $(Get-Date -Format s)" | Add-Content -Path $out
Add-Content -Path $out -Value ""

foreach ($f in $files) {
  Add-Content -Path $out -Value "-----8<----- BEGIN FILE: $f"
  (Get-Content -Path $f -Raw) | Add-Content -Path $out
  Add-Content -Path $out -Value "-----8<----- END FILE: $f"
  Add-Content -Path $out -Value ""
}

# 4) Коммит и пуш
git add $out
git commit -m "chore(snapshot): POS_Protect key files [skip ci]" | Out-Null
git push
