# Agent Chat Multi - 一键停止
# 用法: .\stop-all.ps1

$ErrorActionPreference = "SilentlyContinue"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  🛑 停止 Agent Chat Multi..." -ForegroundColor Yellow

# 读端口
$Port = 3001
if (Test-Path "$ProjectDir\agents.json") {
    $cfg = Get-Content "$ProjectDir\agents.json" -Raw | ConvertFrom-Json
    if ($cfg.serverPort) { $Port = $cfg.serverPort }
}

# 停 Node 服务
$nodePids = netstat -ano 2>$null | Select-String ":$Port " | Select-String "LISTENING" | ForEach-Object { ($_ -split '\s+')[-1] } | Sort-Object -Unique
foreach ($pid in $nodePids) { if ($pid -and $pid -ne "0") { Stop-Process -Id ([int]$pid) -Force } }

# 停 agent_poller 进程
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    $cmd -like "*agent_poller*"
} | Stop-Process -Force

# 停 cloudflared
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "  ✅ 已停止所有服务" -ForegroundColor Green
Write-Host ""
