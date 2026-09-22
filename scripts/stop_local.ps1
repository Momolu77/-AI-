$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot 'artifacts/local-processes.json'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host '没有本启动脚本记录的进程。'; exit 0 }
$records = Get-Content -LiteralPath $pidFile -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($record in $records) {
    $localProcess = Get-Process -Id $record.id -ErrorAction SilentlyContinue
    if (-not $localProcess) { continue }
    $expectedStart = [datetime]::Parse($record.started).ToUniversalTime()
    if ($localProcess.Path -ne $record.executable -or [math]::Abs(($localProcess.StartTime.ToUniversalTime() - $expectedStart).TotalSeconds) -gt 1) { throw "进程 $($record.id) 已变化，未停止。" }
    Stop-Process -Id $localProcess.Id
}
Remove-Item -LiteralPath $pidFile
Write-Host '已停止本脚本启动的本地服务。未修改数据。'
