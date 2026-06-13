# Agent Chat Multi - Stop All
$ErrorActionPreference = "SilentlyContinue"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  Stopping Agent Chat Multi..." -ForegroundColor Yellow

$Port = 3001
if (Test-Path "$ProjectDir\agents.json") {
    $cfg = Get-Content "$ProjectDir\agents.json" -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cfg.serverPort) { $Port = $cfg.serverPort }
}

# Stop Node server
$nodePids = netstat -ano 2>$null | Select-String ":$Port " | Select-String "LISTENING" | ForEach-Object { ($_ -split '\s+')[-1] } | Sort-Object -Unique
foreach ($pid in $nodePids) { if ($pid -and $pid -ne "0") { Stop-Process -Id ([int]$pid) -Force } }

# Stop agent_poller
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    $cmd -like "*agent_poller*"
} | Stop-Process -Force

# Stop cloudflared
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "  All stopped." -ForegroundColor Green
Write-Host ""
