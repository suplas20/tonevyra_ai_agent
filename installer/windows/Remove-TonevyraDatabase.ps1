<#
    EXPLICIT, DESTRUCTIVE Tonevyra database removal.

    The normal uninstaller preserves the database, photos, exports and settings.
    This script exists for the separate "remove my data" flow only. It stops and
    removes the Tonevyra-owned PostgreSQL service and its data directory. It never
    touches a user-managed PostgreSQL install (a service not named
    'TonevyraPostgreSQL'). Requires -Confirm to proceed.
#>
[CmdletBinding()]
param(
    [switch]$Confirm
)

$ErrorActionPreference = "Stop"
$PgService  = "TonevyraPostgreSQL"
$ConfigRoot = Join-Path $env:LOCALAPPDATA "TonevyraAI"

if (-not $Confirm) {
    Write-Host "이 작업은 Tonevyra 데이터베이스와 저장된 자격 증명을 영구 삭제합니다."
    Write-Host "실행하려면 -Confirm 스위치를 추가하십시오:"
    Write-Host "    powershell -ExecutionPolicy Bypass -File Remove-TonevyraDatabase.ps1 -Confirm"
    exit 2
}

$svc = Get-Service -Name $PgService -ErrorAction SilentlyContinue
if ($null -eq $svc) {
    Write-Host "Tonevyra 소유 PostgreSQL 서비스($PgService)가 없습니다. 사용자 관리 PostgreSQL은 건드리지 않습니다."
} else {
    $wmi = Get-CimInstance -ClassName Win32_Service -Filter "Name='$PgService'" -ErrorAction SilentlyContinue
    Write-Host "PostgreSQL 서비스를 중지/제거합니다: $PgService"
    Stop-Service -Name $PgService -Force -ErrorAction SilentlyContinue
    # sc.exe delete removes the service registration; the uninstaller of the
    # downloaded PostgreSQL package removes binaries/data where present.
    & "$env:SystemRoot\System32\sc.exe" delete $PgService | Out-Null
    if ($wmi -and $wmi.PathName) {
        Write-Host "서비스 바이너리 경로: $($wmi.PathName)"
    }
}

$secrets = Join-Path $ConfigRoot "secrets"
foreach ($p in @($secrets, (Join-Path $ConfigRoot "database.json"))) {
    if (Test-Path -LiteralPath $p) {
        Remove-Item -LiteralPath $p -Recurse -Force
        Write-Host "삭제: $p"
    }
}
Write-Host "Tonevyra 데이터베이스 제거 흐름이 완료되었습니다."
