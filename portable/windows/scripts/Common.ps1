Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-TonevyraRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Import-TonevyraEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [switch]$Require
    )

    $envPath = Join-Path $Root ".env"
    if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
        if ($Require) {
            throw ".env is missing. Run scripts\Initialize-Tonevyra.ps1 first."
        }
        return
    }

    foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -ne 2) {
            continue
        }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($name -match "^[A-Za-z_][A-Za-z0-9_]*$") {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Set-TonevyraDerivedEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $env:TONEVYRA_PROJECT_ROOT = $Root
    $env:TONEVYRA_QWEN3_MODEL_PATH = Join-Path $Root "models\qwen3-vl-4b-instruct"
    $env:TONEVYRA_QWEN3_MANIFEST_PATH = Join-Path $Root "models\qwen3-vl-4b-instruct\model_manifest.json"
    $env:TONEVYRA_MODEL_MANIFEST_PATH = $env:TONEVYRA_QWEN3_MANIFEST_PATH
    $env:TONEVYRA_PLANNER_SERVER_DATA_DIR = Join-Path $Root "runtime\planner_server"
    $env:HF_HUB_OFFLINE = "1"
    $env:TRANSFORMERS_OFFLINE = "1"
    $env:HF_HUB_DISABLE_TELEMETRY = "1"
    $env:HF_HUB_DISABLE_IMPLICIT_TOKEN = "1"
    $env:HF_HUB_DISABLE_UPDATE_CHECK = "1"
}

function Test-PlannerReady {
    $baseUrl = if ($env:TONEVYRA_PLANNER_API_BASE_URL) {
        $env:TONEVYRA_PLANNER_API_BASE_URL.TrimEnd("/")
    } else {
        "http://127.0.0.1:8000"
    }
    try {
        $response = Invoke-RestMethod -Uri "$baseUrl/health/ready" -Method Get -TimeoutSec 2
        return $response.ready -eq $true
    } catch {
        return $false
    }
}
