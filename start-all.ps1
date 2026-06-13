# Agent Chat Multi - 一键启动脚本 (Windows PowerShell)
# 用法: 右键 → 使用 PowerShell 运行，或在终端执行 .\start-all.ps1
# 重启电脑后只需跑这个脚本，一切自动恢复

$ErrorActionPreference = "Continue"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

Write-Host ""
Write-Host "  🤖 Agent Chat Multi - 一键启动" -ForegroundColor Cyan
Write-Host "  ================================" -ForegroundColor Cyan
Write-Host ""

# ── 0. 环境检查 ──
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "  [FAIL] 请先安装 Node.js: https://nodejs.org" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}
if (-not (Get-Command python3 -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "  [FAIL] 请先安装 Python" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

# ── 1. 安装依赖 ──
if (-not (Test-Path "server\node_modules")) {
    Write-Host "  [1/6] 安装 npm 依赖..." -ForegroundColor Yellow
    Push-Location server; npm install; Pop-Location
    Write-Host "  [OK] 依赖安装完成" -ForegroundColor Green
} else {
    Write-Host "  [1/6] 依赖已就绪" -ForegroundColor Green
}

# ── 2. 读取端口 ──
$agentsJson = Get-Content "agents.json" -Raw | ConvertFrom-Json
$Port = if ($agentsJson.serverPort) { $agentsJson.serverPort } else { 3001 }
Write-Host "  [2/6] 端口: $Port" -ForegroundColor Green

# ── 3. 清理旧进程 ──
Write-Host "  [3/6] 清理旧进程..." -ForegroundColor Yellow
$oldPids = netstat -ano 2>$null | Select-String ":$Port " | Select-String "LISTENING" | ForEach-Object {
    ($_ -split '\s+')[-1]
} | Sort-Object -Unique
foreach ($pid in $oldPids) {
    if ($pid -and $pid -ne "0") {
        Stop-Process -Id ([int]$pid) -Force -ErrorAction SilentlyContinue
        Write-Host "    已终止 PID $pid" -ForegroundColor DarkGray
    }
}
Start-Sleep -Seconds 1
Write-Host "  [OK] 端口已清理" -ForegroundColor Green

# ── 4. 启动 Node.js 服务 ──
Write-Host "  [4/6] 启动聊天服务..." -ForegroundColor Yellow
$serverProc = Start-Process -FilePath "node" -ArgumentList "multi-agent.js" -WorkingDirectory "$ProjectDir\server" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3

$healthy = $false
try {
    $r = Invoke-RestMethod -Uri "http://localhost:$Port/api/health" -TimeoutSec 3 -ErrorAction Stop
    $healthy = $true
    $agentCount = $r.agents.Count
    Write-Host "  [OK] 服务启动成功 (PID $($serverProc.Id), $agentCount 个角色)" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] 服务启动失败，请检查 server/multi-agent.js" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

# ── 5. 启动 Agent 轮询进程 ──
Write-Host "  [5/6] 启动 Agent 轮询..." -ForegroundColor Yellow
$env:CHAT_SERVER_URL = "http://localhost:$Port"

# 清理旧的 last_id 文件
Get-ChildItem ".last_id_*" -ErrorAction SilentlyContinue | Remove-Item -Force

$agents = $agentsJson.agents | Where-Object { $_.enabled -ne $false }
$agentProcs = @()
foreach ($agent in $agents) {
    $proc = Start-Process -FilePath "python3" -ArgumentList "-u", "agent_poller.py", $agent.id -WorkingDirectory $ProjectDir -WindowStyle Hidden -PassThru
    $agentProcs += @{ id = $agent.id; name = $agent.name; pid = $proc.Id }
    Write-Host "    $($agent.avatar) $($agent.name) → PID $($proc.Id)" -ForegroundColor DarkGray
    Start-Sleep -Milliseconds 500
}
Write-Host "  [OK] $($agents.Count) 个 Agent 已启动" -ForegroundColor Green

# ── 6. 启动 Cloudflare Tunnel ──
Write-Host "  [6/6] 启动公网隧道..." -ForegroundColor Yellow

# 查找 cloudflared
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
    # 先尝试命名隧道 (multi.agent-chat.org)
    $tokenFile = "$env:USERPROFILE\.cloudflared\agent-chat-token"
    if (Test-Path $tokenFile) {
        $token = Get-Content $tokenFile -Raw | Trim
        Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "run", "--token", $token -WindowStyle Hidden
        $publicUrl = "https://multi.agent-chat.org"
        Write-Host "  [OK] 命名隧道启动 → $publicUrl" -ForegroundColor Green
    } else {
        # Quick Tunnel (临时地址)
        $tunnelProc = Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "--url", "http://localhost:$Port" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$ProjectDir\tunnel-url.txt" -RedirectStandardError "$ProjectDir\tunnel-log.txt"
        Start-Sleep -Seconds 8
        # 从日志提取 URL
        $log = Get-Content "$ProjectDir\tunnel-log.txt" -Raw -ErrorAction SilentlyContinue
        if ($log -match '(https://[a-z0-9-]+\.trycloudflare\.com)') {
            $publicUrl = $Matches[0]
            Write-Host "  [OK] Quick Tunnel → $publicUrl" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] 隧道启动中，请稍等..." -ForegroundColor Yellow
            $publicUrl = "(等待分配)"
        }
    }
} else {
    Write-Host "  [WARN] 未找到 cloudflared，仅本地可用" -ForegroundColor Yellow
    Write-Host "         下载: https://github.com/cloudflare/cloudflared/releases" -ForegroundColor DarkGray
}

# ── 总结 ──
Write-Host ""
Write-Host "  ================================" -ForegroundColor Cyan
Write-Host "  ✅ 全部启动完成！" -ForegroundColor Green
Write-Host ""
Write-Host "  🏠 本地: http://localhost:$Port"
if ($publicUrl -and $publicUrl -ne "(等待分配)") {
    Write-Host "  🌐 公网: $publicUrl"
} else {
    Write-Host "  🌐 公网: 查看隧道日志获取地址"
}
Write-Host ""
Write-Host "  📋 服务 PID: $($serverProc.Id)"
foreach ($ap in $agentProcs) {
    Write-Host "  📋 $($ap.name) PID: $($ap.pid)"
}
Write-Host ""
Write-Host "  ⏹ 停止: 运行 .\stop-all.ps1 或关闭此窗口" -ForegroundColor DarkGray
Write-Host "  ================================" -ForegroundColor Cyan
Write-Host ""

# 打开浏览器
Start-Process "http://localhost:$Port"

# 保持窗口打开
Write-Host "  (保持此窗口打开，关闭将停止所有服务)" -ForegroundColor DarkGray
Read-Host "按回车停止所有服务并退出"

# 清理
Write-Host "`n  正在停止..." -ForegroundColor Yellow
Stop-Process -Id $serverProc.Id -Force -ErrorAction SilentlyContinue
foreach ($ap in $agentProcs) { Stop-Process -Id $ap.pid -Force -ErrorAction SilentlyContinue }
if ($tunnelProc) { Stop-Process -Id $tunnelProc.Id -Force -ErrorAction SilentlyContinue }
Write-Host "  已停止" -ForegroundColor Green
