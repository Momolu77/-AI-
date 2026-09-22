$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = Join-Path $projectRoot '.venv/Scripts/python.exe'
$artifactsDirectory = Join-Path $projectRoot 'artifacts'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw '请先按 README 安装 Python 和 npm 依赖。' }

function Test-RecordedListener {
    param($Listener, $Records, $Processes)
    # Windows venv python.exe may launch a child interpreter that owns the socket.
    $ownerId = [int]$Listener.OwningProcess
    for ($depth = 0; $depth -lt 8 -and $ownerId -gt 0; $depth++) {
        $owner = $Processes | Where-Object { $_.ProcessId -eq $ownerId } | Select-Object -First 1
        if (-not $owner) { return $false }
        foreach ($record in $Records) {
            if ([int]$record.id -ne $ownerId) { continue }
            $expectedStart = [datetime]::Parse($record.started).ToUniversalTime()
            if ($owner.ExecutablePath -eq $record.executable -and [math]::Abs(($owner.CreationDate.ToUniversalTime() - $expectedStart).TotalSeconds) -le 1) {
                return $true
            }
        }
        $ownerId = [int]$owner.ParentProcessId
    }
    return $false
}

$occupied = Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue
if ($occupied) {
    $alreadyRunning = $false
    $pidFile = Join-Path $artifactsDirectory 'local-processes.json'
    if (@($occupied).Count -eq 2 -and (Test-Path -LiteralPath $pidFile)) {
        try {
            $records = Get-Content -LiteralPath $pidFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $processes = Get-CimInstance Win32_Process
            $verified = @($occupied | Where-Object {
                $_.LocalAddress -eq '127.0.0.1' -and (Test-RecordedListener -Listener $_ -Records $records -Processes $processes)
            })
            if ($verified.Count -eq 2) {
                $backendHealth = Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 3
                $frontendHealth = Invoke-WebRequest 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 3
                $alreadyRunning = $backendHealth.status -eq 'ok' -and $frontendHealth.StatusCode -eq 200
            }
        } catch { $alreadyRunning = $false }
    }
    if ($alreadyRunning) {
        Write-Host '工作台已在运行，前后端连接正常，无需再次启动。请打开下面的座位入口：'
        Push-Location $projectRoot
        try {
            & $pythonExecutable 'scripts/seed_local.py' '--env-file' '.env.local'
            if ($LASTEXITCODE -ne 0) { throw '读取座位入口失败，请查看上方错误。' }
        } finally { Pop-Location }
        exit 0
    }
    $portDetails = ($occupied | ForEach-Object { "$($_.LocalPort)（PID $($_.OwningProcess)）" }) -join '、'
    throw "端口已占用：$portDetails。未确认两个服务均为本项目且运行正常。若要重启本项目，请先运行 scripts/stop_local.ps1；其他服务需单独检查。"
}
New-Item -ItemType Directory -Force -Path $artifactsDirectory | Out-Null
Push-Location $projectRoot
try {
    & $pythonExecutable 'scripts/local_init.py' '--env-file' '.env.local'
    if ($LASTEXITCODE -ne 0) { throw '初始化失败。' }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backendProcess = Start-Process -FilePath $pythonExecutable -ArgumentList @('-m','uvicorn','app.main:app','--app-dir','backend','--env-file','.env.local','--host','127.0.0.1','--port','8000') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $artifactsDirectory "local-backend-$stamp.out.log") -RedirectStandardError (Join-Path $artifactsDirectory "local-backend-$stamp.err.log")
    $nodeExecutable = (Get-Command node -ErrorAction Stop).Source
    $frontendProcess = Start-Process -FilePath $nodeExecutable -ArgumentList @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5173','--strictPort') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $artifactsDirectory "local-frontend-$stamp.out.log") -RedirectStandardError (Join-Path $artifactsDirectory "local-frontend-$stamp.err.log")
    $records = @($backendProcess, $frontendProcess) | ForEach-Object { @{ id=$_.Id; started=$_.StartTime.ToUniversalTime().ToString('o'); executable=$_.Path } }
    ConvertTo-Json -InputObject @($records) | Set-Content -LiteralPath (Join-Path $artifactsDirectory 'local-processes.json') -Encoding UTF8
    $ready = $false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        try {
            $backendHealth = Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 1
            $frontendHealth = Invoke-WebRequest 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 1
            if ($backendHealth.status -eq 'ok' -and $frontendHealth.StatusCode -eq 200) { $ready=$true; break }
        } catch { Start-Sleep -Milliseconds 300 }
    }
    if (-not $ready) { throw '服务未就绪，请查看 artifacts/local-* 日志。' }
    & $pythonExecutable 'scripts/seed_local.py' '--env-file' '.env.local'
    Write-Host '两个服务已就绪，仅监听 127.0.0.1。使用 scripts/stop_local.ps1 停止。'
} finally { Pop-Location }
