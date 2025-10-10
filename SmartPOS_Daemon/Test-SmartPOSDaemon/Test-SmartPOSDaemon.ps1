param(
    [string]$ProjectRoot = "C:\AI\SmartPOS\SmartPOS_Daemon",
    [ValidateSet("PR0018_soft","PR0022_probe","PR0006_width","All")]
    [string]$Case = "PR0018_soft",
    [int]$TimeoutSec = 8
)

# Read config
$cfgPath = Join-Path $ProjectRoot "config_smartpos.json"
if (!(Test-Path $cfgPath)) {
    Write-Error "Config not found: $cfgPath"
    exit 2
}
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
$daemon = $cfg.daemon_url
$printer = $cfg.printer_name

# Helpers
function Invoke-JsonPost($Url, $Body, $TimeoutSec=8) {
    $json = ($Body | ConvertTo-Json -Depth 6 -Compress)
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Post -ContentType "application/json" -Body $json -TimeoutSec $TimeoutSec
        return @{ ok=$true; code=$resp.StatusCode; text=$resp.Content }
    } catch {
        return @{ ok=$false; code=$_.Exception.Response.StatusCode.Value__; text=$_.Exception.Message }
    }
}

function Show-Response($Label, $RespText) {
    try {
        $obj = $RespText | ConvertFrom-Json
    } catch {
        Write-Host "[$Label] BAD JSON:" -ForegroundColor Yellow
        Write-Host $RespText
        return 1
    }
    $rc = $obj.result_code
    $acts = if ($obj.actions_done) { ($obj.actions_done -join "; ") } else { "" }
    $ev  = if ($obj.evidence) { ($obj.evidence | ConvertTo-Json -Compress) } else { "{}" }
    Write-Host "[$Label] result_code=$rc"
    if ($acts) { Write-Host "         actions= $acts" } else { Write-Host "         actions= (none)" }
    Write-Host "         evidence= $ev"
    if ($obj.human) {
        Write-Host "         cashier: $($obj.human.cashier)"
        Write-Host "         tech:    $($obj.human.tech)"
    }
    if ($rc -in @("ERROR","ACCESS_DENIED")) { return 1 } else { return 0 }
}

# 1) Health
Write-Host "== Probe /health on $daemon ==" -ForegroundColor Cyan
try {
    $h = Invoke-WebRequest -UseBasicParsing -Uri ($daemon.TrimEnd("/") + "/health") -TimeoutSec 3
    Write-Host "/health ->" $h.StatusCode
} catch {
    Write-Warning "Health endpoint failed: $($_.Exception.Message)"
}

# Base payload
$basePayload = [PSCustomObject]@{
    ticket_id = "SP-SELFTEST-0001"
    device    = [PSCustomObject]@{ type="receipt_printer"; name=$printer; conn="USB" }
    context   = [PSCustomObject]@{ beautify=$false; purge="soft"; raw_user="selftest" }
}

# Helper to clone PSCustomObject
function Copy-Object([psobject]$obj) {
    return ($obj | ConvertTo-Json -Depth 6 | ConvertFrom-Json)
}

$cases = @()

if ($Case -eq "All" -or $Case -eq "PR0018_soft") {
    $p = Copy-Object $basePayload
    $p | Add-Member -NotePropertyName problem_code -NotePropertyValue "PR0018" -Force
    $cases += @{ label="PR0018_soft"; payload=$p }
}
if ($Case -eq "All" -or $Case -eq "PR0022_probe") {
    $p = Copy-Object $basePayload
    $p | Add-Member -NotePropertyName problem_code -NotePropertyValue "PR0022" -Force
    $cases += @{ label="PR0022_probe"; payload=$p }
}
if ($Case -eq "All" -or $Case -eq "PR0006_width") {
    $p = Copy-Object $basePayload
    $p | Add-Member -NotePropertyName problem_code -NotePropertyValue "PR0006" -Force
    $cases += @{ label="PR0006_width"; payload=$p }
}

# 2) Run selected cases
$fail = 0
foreach ($c in $cases) {
    $url = $daemon.TrimEnd("/") + "/action/run"
    Write-Host "== POST $($c.label) -> $url ==" -ForegroundColor Cyan
    $res = Invoke-JsonPost -Url $url -Body $c.payload -TimeoutSec $TimeoutSec
    if (-not $res.ok) {
        Write-Warning "HTTP error: $($res.code) $($res.text)"
        $fail = 1
        continue
    }
    $rc = Show-Response -Label $c.label -RespText $res.text
    if ($rc -ne 0) { $fail = 1 }
}

if ($fail -ne 0) {
    Write-Host "== SELFTEST: FAIL ==" -ForegroundColor Red
    exit 1
} else {
    Write-Host "== SELFTEST: OK ==" -ForegroundColor Green
    exit 0
}
