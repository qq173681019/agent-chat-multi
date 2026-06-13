# Agent Chat Multi - One-Click Start (Windows)
# Usage: .\start-all.ps1 or double-click start-all.bat
$ErrorActionPreference = "Continue"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

Write-Host ""
Write-Host "  Agent Chat Multi - Starting" -ForegroundColor Cyan
Write-Host "  ============================" -ForegroundColor Cyan
Write-Host ""

# -- 0. Check environment --
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "  [FAIL] Node.js not found. Install: https://nodejs.org" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# -- 1. Install deps --
if (-not (Test-Path "server\node_modules")) {
    Write-Host "  [1/6] Installing npm deps..." -ForegroundColor Yellow
    Push-Location server; npm install; Pop-Location
} else {
    Write-Host "  [1/6] Deps OK" -ForegroundColor Green
}

# -- 2. Read port --
$agentsJson = Get-Content "agents.json" -Raw | ConvertFrom-Json
$Port = if ($agentsJson.serverPort) { $agentsJson.serverPort } else { 3001 }
Write-Host "  [2/6] Port: $Port" -ForegroundColor Green

# -- 3. Kill old processes --
Write-Host "  [3/6] Cleaning old processes..." -ForegroundColor Yellow
$oldPids = netstat -ano 2>$null | Select-String ":$Port " | Select-String "LISTENING" | ForEach-Object {
    ($_ -split '\s+')[-1]
} | Sort-Object -Unique
foreach ($pid in $oldPids) {
    if ($pid -and $pid -ne "0") {
        Stop-Process -Id ([int]$pid) -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 1
Write-Host "  [OK] Port cleaned" -ForegroundColor Green

# -- 4. Start Node.js server --
Write-Host "  [4/6] Starting server..." -ForegroundColor Yellow
$serverProc = Start-Process -FilePath "node" -ArgumentList "multi-agent.js" -WorkingDirectory "$ProjectDir\server" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3

try {
    $r = Invoke-RestMethod -Uri "http://localhost:$Port/api/health" -TimeoutSec 3 -ErrorAction Stop
    $agentCount = $r.agents.Count
    Write-Host "  [OK] Server ready (PID $($serverProc.Id), $agentCount agents)" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Server not responding on port $Port" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# -- 5. Start Agent pollers --
Write-Host "  [5/6] Starting agent pollers..." -ForegroundColor Yellow
$env:CHAT_SERVER_URL = "http://localhost:$Port"
Get-ChildItem ".last_id_*" -ErrorAction SilentlyContinue | Remove-Item -Force

$agents = $agentsJson.agents | Where-Object { $_.enabled -ne $false }
$agentProcs = @()
foreach ($agent in $agents) {
    $proc = Start-Process -FilePath "python3" -ArgumentList "-u", "agent_poller.py", $agent.id -WorkingDirectory $ProjectDir -WindowStyle Hidden -PassThru
    $agentProcs += @{ id = $agent.id; name = $agent.name; pid = $proc.Id }
    Write-Host "    $($agent.avatar) $($agent.name) PID $($proc.Id)" -ForegroundColor DarkGray
    Start-Sleep -Milliseconds 500
}
Write-Host "  [OK] $($agents.Count) agents started" -ForegroundColor Green

# -- 6. Start Cloudflare Tunnel --
Write-Host "  [6/6] Starting tunnel..." -ForegroundColor Yellow
$cloudflared = $null
$candidates = @(
    "$ProjectDir\cloudflared.exe",
    "$ProjectDir\..\agent-chat\cloudflared.exe",
    "C:\Program Files\Cloudflare\cloudflared.exe"
)
foreach ($c in $candidates) {
    if (Test-Path $c) { $cloudflared = $c; break }
}
if (-not $cloudflared) {
    $cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
}

$publicUrl = ""
if ($cloudflared) {
    $tokenFile = "$env:USERPROFILE\.cloudflared\agent-chat-token"
    if (Test-Path $tokenFile) {
        $token = (Get-Content $tokenFile -Raw).Trim()
        Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "run", "--token", $token -WindowStyle Hidden
        $publicUrl = "https://multi.agent-chat.org"
        Write-Host "  [OK] Named tunnel -> $publicUrl" -ForegroundColor Green
    } else {
        $tunnelProc = Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "--url", "http://localhost:$Port" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$ProjectDir\tunnel-url.txt" -RedirectStandardError "$ProjectDir\tunnel-log.txt"
        Start-Sleep -Seconds 10
        $log = Get-Content "$ProjectDir\tunnel-log.txt" -Raw -ErrorAction SilentlyContinue
        if ($log -match '(https://[a-z0-9-]+\.trycloudflare\.com)') {
            $publicUrl = $Matches[0]
            Write-Host "  [OK] Quick tunnel -> $publicUrl" -ForegroundColor Green
        } else {
            $publicUrl = "(pending)"
            Write-Host "  [WARN] Tunnel starting, check tunnel-log.txt" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "  [WARN] cloudflared not found, local only" -ForegroundColor Yellow
}

# -- Summary --
Write-Host ""
Write-Host "  ============================" -ForegroundColor Cyan
Write-Host "  All systems go!" -ForegroundColor Green
Write-Host ""
Write-Host "  Local:  http://localhost:$Port"
if ($publicUrl -and $publicUrl -ne "(pending)") {
    Write-Host "  Public: $publicUrl"
}
Write-Host ""
Write-Host "  Server PID: $($serverProc.Id)"
foreach ($ap in $agentProcs) {
    Write-Host "  $($ap.name) PID: $($ap.pid)"
}
Write-Host ""
Write-Host "  Stop: run stop-all.bat or close this window" -ForegroundColor DarkGray
Write-Host "  ============================" -ForegroundColor Cyan
Write-Host ""

Start-Process "http://localhost:$Port"
Write-Host "  (Keep this window open. Press Enter to stop all)" -ForegroundColor DarkGray
Read-Host

Write-Host ""
Write-Host "  Stopping..." -ForegroundColor Yellow
Stop-Process -Id $serverProc.Id -Force -ErrorAction SilentlyContinue
foreach ($ap in $agentProcs) { Stop-Process -Id $ap.pid -Force -ErrorAction SilentlyContinue }
if ($tunnelProc) { Stop-Process -Id $tunnelProc.Id -Force -ErrorAction SilentlyContinue }
Write-Host "  Stopped." -ForegroundColor Green
