. (Join-Path $PSScriptRoot "Common.ps1")

$root = Get-TonevyraRoot
Import-TonevyraEnv -Root $root -Require
Set-TonevyraDerivedEnv -Root $root

if (-not (Test-PlannerReady)) {
    throw "Planner Server is not ready. Run Start-PlannerServer.ps1 first."
}

$exe = Join-Path $root "Agent\TonevyraAI.exe"
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Agent executable is missing: $exe"
}

$process = Start-Process -FilePath $exe -ArgumentList @("tray") -WorkingDirectory $root -PassThru
Start-Sleep -Seconds 2
if ($process.HasExited) {
    throw "Tonevyra Agent exited during startup (exit=$($process.ExitCode))."
}

$pidPath = Join-Path $root "runtime\tonevyra_tray.pid"
Set-Content -LiteralPath $pidPath -Value $process.Id -Encoding ASCII
Write-Host "[OK] Tonevyra Agent started: PID $($process.Id)"
Write-Host "Input folder: $(Join-Path $root 'runtime\input')"
