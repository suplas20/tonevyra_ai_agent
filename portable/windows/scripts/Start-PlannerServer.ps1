. (Join-Path $PSScriptRoot "Common.ps1")

$root = Get-TonevyraRoot
Import-TonevyraEnv -Root $root -Require
Set-TonevyraDerivedEnv -Root $root

if (Test-PlannerReady) {
    Write-Host "[OK] Planner Server is already ready."
    exit 0
}

$exe = Join-Path $root "PlannerServer\TonevyraPlannerServer.exe"
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Planner Server executable is missing: $exe"
}

$process = Start-Process -FilePath $exe -WorkingDirectory $root -PassThru
$pidPath = Join-Path $root "runtime\planner_server\planner.pid"
New-Item -ItemType Directory -Force -Path (Split-Path $pidPath) | Out-Null
Set-Content -LiteralPath $pidPath -Value $process.Id -Encoding ASCII

for ($attempt = 1; $attempt -le 40; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($process.HasExited) {
        throw "Planner Server exited during startup (exit=$($process.ExitCode))."
    }
    if (Test-PlannerReady) {
        Write-Host "[OK] Planner Server is ready: $env:TONEVYRA_PLANNER_API_BASE_URL"
        exit 0
    }
}

Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
throw "Planner Server readiness check timed out."
