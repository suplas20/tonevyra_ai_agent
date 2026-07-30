. (Join-Path $PSScriptRoot "Common.ps1")

$root = Get-TonevyraRoot
$pidPath = Join-Path $root "runtime\planner_server\planner.pid"
$exe = (Join-Path $root "PlannerServer\TonevyraPlannerServer.exe")
$processes = @(
    Get-Process -Name "TonevyraPlannerServer" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and ([IO.Path]::GetFullPath($_.Path) -eq [IO.Path]::GetFullPath($exe)) }
)

if ($processes.Count -gt 0) {
    $processIds = $processes.Id
    $processes | Stop-Process -Force
    Write-Host "[OK] Stopped Planner Server process tree: $($processIds -join ', ')"
} else {
    Write-Host "Planner Server process has already stopped."
}
Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
