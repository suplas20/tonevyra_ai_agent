. (Join-Path $PSScriptRoot "Common.ps1")

$root = Get-TonevyraRoot
$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

function Test-RequiredFile {
    param([string]$Label, [string]$Path)
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Write-Host "[OK] $Label`: $Path"
    } else {
        Write-Host "[FAIL] $Label`: $Path"
        $failures.Add($Label)
    }
}

Write-Host "Tonevyra AI target-PC prerequisite check"
Write-Host "========================================"

if (-not [Environment]::Is64BitOperatingSystem) {
    $failures.Add("64-bit Windows")
    Write-Host "[FAIL] 64-bit Windows is required."
} else {
    Write-Host "[OK] 64-bit Windows"
}

Test-RequiredFile "Agent executable" (Join-Path $root "Agent\TonevyraAI.exe")
Test-RequiredFile "Planner Server executable" (Join-Path $root "PlannerServer\TonevyraPlannerServer.exe")
Test-RequiredFile "Environment configuration" (Join-Path $root ".env")
Test-RequiredFile "Model index" (Join-Path $root "models\qwen3-vl-4b-instruct\model.safetensors.index.json")

$envPath = Join-Path $root ".env"
if (Test-Path -LiteralPath $envPath -PathType Leaf) {
    $envText = Get-Content -LiteralPath $envPath -Raw -Encoding UTF8
    if ($envText -match "CHANGE_ME_DATABASE_PASSWORD") {
        Write-Host "[FAIL] Replace CHANGE_ME_DATABASE_PASSWORD in .env."
        $failures.Add("PostgreSQL app password configuration")
    }
    if ($envText -match "CHANGE_ME_PLANNER_API_KEY") {
        Write-Host "[FAIL] Generate a Planner API key by running Initialize-Tonevyra.ps1."
        $failures.Add("Planner API key configuration")
    }
}

$weights = Get-ChildItem -LiteralPath (Join-Path $root "models\qwen3-vl-4b-instruct") `
    -Filter "*.safetensors" -File -ErrorAction SilentlyContinue
if (-not $weights) {
    Write-Host "[FAIL] Model safetensors weights are missing."
    $failures.Add("Qwen model weights")
} else {
    $weightBytes = ($weights | Measure-Object -Property Length -Sum).Sum
    Write-Host ("[OK] Model weights: {0:N2} GB" -f ($weightBytes / 1GB))
}

$nvidiaSmi = Get-Command "nvidia-smi.exe" -ErrorAction SilentlyContinue
if (-not $nvidiaSmi) {
    Write-Host "[FAIL] NVIDIA driver or nvidia-smi was not found."
    $failures.Add("NVIDIA driver")
} else {
    $gpuRows = & $nvidiaSmi.Source `
        --query-gpu=name,driver_version,memory.total `
        --format=csv,noheader 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $gpuRows) {
        Write-Host "[FAIL] NVIDIA GPU query failed."
        $failures.Add("NVIDIA GPU")
    } else {
        Write-Host "[OK] NVIDIA GPU: $($gpuRows -join '; ')"
        $driverText = (($gpuRows | Select-Object -First 1) -split ",")[1].Trim()
        try {
            if ([version]$driverText -lt [version]"580.88") {
                $warnings.Add("The CUDA 13.0 build recommends NVIDIA Windows driver 580.88 or later.")
            }
        } catch {
            $warnings.Add("Could not compare NVIDIA driver version: $driverText")
        }
    }
}

$postgresServices = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue
if (-not $postgresServices) {
    Write-Host "[FAIL] PostgreSQL Windows service was not found."
    $failures.Add("PostgreSQL service")
} elseif (-not ($postgresServices | Where-Object Status -eq "Running")) {
    Write-Host "[FAIL] PostgreSQL service is stopped."
    $failures.Add("PostgreSQL running")
} else {
    Write-Host "[OK] PostgreSQL service is running."
}

$lightroomCandidates = @(
    (Join-Path $env:ProgramFiles "Adobe\Adobe Lightroom Classic\Lightroom.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Adobe\Adobe Lightroom Classic\Lightroom.exe")
)
if ($lightroomCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }) {
    Write-Host "[OK] Lightroom Classic installation found."
} else {
    Write-Host "[FAIL] Lightroom Classic installation was not found."
    $failures.Add("Lightroom Classic")
}

$vcRuntime = Join-Path $env:WINDIR "System32\vcruntime140.dll"
if (Test-Path -LiteralPath $vcRuntime) {
    Write-Host "[OK] Microsoft Visual C++ x64 Runtime"
} else {
    $warnings.Add("Install Microsoft Visual C++ 2015-2022 x64 Redistributable.")
}

foreach ($warning in $warnings) {
    Write-Warning $warning
}

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "[BLOCKED] Missing items: $($failures -join ', ')"
    exit 1
}

Write-Host ""
Write-Host "[OK] Basic prerequisite check passed."
