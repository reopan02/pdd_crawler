$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $root "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$stdoutLog = Join-Path $logDir "web_stdout.log"
$stderrLog = Join-Path $logDir "web_stderr.log"
$pidFile = Join-Path $logDir "web.pid"
$pythonExe = if ($env:VIRTUAL_ENV) { Join-Path $env:VIRTUAL_ENV "Scripts\python.exe" } else { "python" }
$process = Start-Process -FilePath $pythonExe -ArgumentList "-m pdd_crawler.web.run" -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru
Set-Content -Path $pidFile -Value $process.Id -Encoding ascii
Write-Output "PID=$($process.Id)"
Write-Output "STDOUT=$stdoutLog"
Write-Output "STDERR=$stderrLog"
