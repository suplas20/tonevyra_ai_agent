<#
    Tonevyra AI - all-in-one provisioning helper (Windows).

    Invoked once by the Inno Setup installer AFTER the application payload,
    bundled model, Lightroom plugin and resources are already on disk. This
    script owns ONLY the prerequisite + database orchestration:

        - acquire + verify + unattended-install PostgreSQL (Tonevyra-owned)
        - create/verify tonevyra_app role + tonevyra_agent DB, store credentials
        - delegate schema/verify/smoke to the tested app CLI
          (installer-db bootstrap-schema / verify / db-smoke-test)
        - link the bundled Lightroom plugin when Lightroom Classic exists
        - enable current-user autostart (non-fatal)
        - app `init` + `doctor` gate (must pass)

    Messages/receipts are intentionally ASCII English (machine logs). The Korean
    user-facing text lives in the Inno wizard, which renders it correctly. This
    keeps the on-disk log/receipt files free of code-page mojibake.

    This script is idempotent and can be re-run standalone to complete or repair
    provisioning without reinstalling the payload:

        powershell -ExecutionPolicy Bypass -File Invoke-TonevyraProvision.ps1 `
            -InstallRoot "<install dir>" -ResultPath "$env:TEMP\r.txt"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$InstallRoot,
    [Parameter(Mandatory = $true)] [string]$ResultPath
)

$ErrorActionPreference = "Stop"

# --- constants ---------------------------------------------------------------
$AppExe        = Join-Path $InstallRoot "TonevyraAI.exe"
$ModelManifest = Join-Path $InstallRoot "models\qwen3-vl-4b-instruct\model_manifest.json"
$ConfigRoot    = Join-Path $env:LOCALAPPDATA "TonevyraAI"
$ReceiptRoot   = Join-Path $env:PROGRAMDATA "TonevyraAI\install-receipts"
$SessionId     = [Guid]::NewGuid().ToString("N")
$ReceiptPath   = Join-Path $ReceiptRoot ("install-" + $SessionId + ".json")
$Transcript    = Join-Path $ReceiptRoot ("install-" + $SessionId + ".log")

$PgService     = "TonevyraPostgreSQL"
$PgPort        = 55432
$PgHost        = "127.0.0.1"
$Database      = "tonevyra_agent"
$Role          = "tonevyra_app"
# Dedicated Tonevyra-owned prefix so we never collide with (or disturb) a
# user-managed PostgreSQL at the default location, and so leftover data from a
# previous failed attempt can be cleaned safely.
$PgPrefix      = Join-Path $env:ProgramFiles "TonevyraAI\PostgreSQL"
$PgDataDir     = Join-Path $PgPrefix "data"

$PinnedPgVersion = "18.4-2"
$PinnedPgUrl     = "https://get.enterprisedb.com/postgresql/postgresql-18.4-2-windows-x64.exe"
$PinnedPgSha256  = "0698d1a6083da490e5a57149257f5d9220d8c34109ed11b38aa592d320bf5385"
$AllowedPgHosts  = @("postgresql.org", "enterprisedb.com", "get.enterprisedb.com")

$DownloadTimeoutSec = 900
$InstallTimeoutSec  = 1800
$CommandTimeoutSec  = 300

$MetadataUrlOverride   = $env:TONEVYRA_T033_POSTGRES_METADATA_URL
$AdminPasswordOverride = $env:TONEVYRA_T033_POSTGRES_ADMIN_PASSWORD
$script:AdminPassword  = $AdminPasswordOverride

New-Item -ItemType Directory -Force -Path $ReceiptRoot | Out-Null
try { Start-Transcript -Path $Transcript -Append | Out-Null } catch { }

# --- helpers -----------------------------------------------------------------
function Write-Receipt([string]$Step, [string]$Result, [hashtable]$Data = @{}) {
    # Receipts never contain passwords or full connection URLs.
    $entry = [ordered]@{
        timestamp = (Get-Date).ToUniversalTime().ToString("o")
        step      = $Step
        result    = $Result
        data      = $Data
    }
    $existing = @()
    if (Test-Path -LiteralPath $ReceiptPath) {
        $existing = Get-Content -LiteralPath $ReceiptPath -Raw | ConvertFrom-Json
    }
    @($existing) + @($entry) | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReceiptPath -Encoding UTF8
}

function Write-Step([string]$Step, [string]$Message) {
    Write-Host ("[" + (Get-Date).ToUniversalTime().ToString("HH:mm:ss") + "] " + $Step + " - " + $Message)
    Write-Receipt $Step "running" @{ message = $Message }
}

function Invoke-Timed([string]$FilePath, [string[]]$Arguments, [int]$TimeoutSec, [string]$Code, [string]$What) {
    $p = Start-Process -FilePath $FilePath -ArgumentList $Arguments -PassThru -WorkingDirectory $InstallRoot
    if (-not $p.WaitForExit($TimeoutSec * 1000)) {
        try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch { }
        throw ($Code + " " + $What + " timed out after " + $TimeoutSec + "s")
    }
    if ($p.ExitCode -ne 0) {
        throw ($Code + " " + $What + " failed (exit " + $p.ExitCode + ")")
    }
}

function Protect-TempSecretFile([string]$Path) {
    try {
        $acl = Get-Acl -LiteralPath $Path
        $acl.SetAccessRuleProtection($true, $false)
        $identities = @(
            [System.Security.Principal.WindowsIdentity]::GetCurrent().User,
            (New-Object System.Security.Principal.SecurityIdentifier "S-1-5-32-544"),
            (New-Object System.Security.Principal.SecurityIdentifier "S-1-5-18")
        )
        foreach ($identity in $identities) {
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
                $identity,
                [System.Security.AccessControl.FileSystemRights]::FullControl,
                [System.Security.AccessControl.AccessControlType]::Allow
            )
            $acl.AddAccessRule($rule) | Out-Null
        }
        Set-Acl -LiteralPath $Path -AclObject $acl
    } catch {
        throw ("T033-PG-INSTALL-007 failed to protect PostgreSQL option file: " + $_.Exception.Message)
    }
}

function Remove-TempFile([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        try {
            Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
        } catch {
            Write-Warning ("Could not remove temporary installer file " + $Path + ": " + $_.Exception.Message)
        }
    }
}

function Assert-AllowedHost([string]$Url) {
    $uri = [Uri]$Url
    if ($uri.Scheme -ne "https") { throw ("T033-PG-DOWNLOAD-005 download URL must be HTTPS: " + $Url) }
    $ok = $false
    $hostName = $uri.Host.ToLowerInvariant()
    foreach ($h in $AllowedPgHosts) {
        if ($hostName -eq $h -or $hostName.EndsWith("." + $h)) { $ok = $true }
    }
    if (-not $ok) { throw ("T033-PG-DOWNLOAD-005 host not allowlisted: " + $uri.Host) }
}

function Get-PgServiceObject { Get-Service -Name $PgService -ErrorAction SilentlyContinue }

function Get-PsqlPath {
    $direct = Join-Path $PgPrefix "bin\psql.exe"
    if (Test-Path -LiteralPath $direct) { return $direct }
    $cmd = Get-Command "psql.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($base in @($PgPrefix, (Join-Path $env:ProgramFiles "PostgreSQL"))) {
        if (Test-Path -LiteralPath $base) {
            $found = Get-ChildItem -Path $base -Filter "psql.exe" -Recurse -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending | Select-Object -First 1
            if ($found) { return $found.FullName }
        }
    }
    return $null
}

function Test-PostgresAdminPassword([string]$Password) {
    if ([string]::IsNullOrWhiteSpace($Password)) { return $false }
    $psql = Get-PsqlPath
    if (-not $psql) { return $false }
    $oldHost = $env:PGHOST
    $oldPort = $env:PGPORT
    $oldUser = $env:PGUSER
    $oldPassword = $env:PGPASSWORD
    $oldTimeout = $env:PGCONNECT_TIMEOUT
    try {
        $env:PGHOST = $PgHost
        $env:PGPORT = "$PgPort"
        $env:PGUSER = "postgres"
        $env:PGPASSWORD = $Password
        $env:PGCONNECT_TIMEOUT = "15"
        $result = & $psql -w -tAc "select 1" -d "postgres" 2>$null
        return ($LASTEXITCODE -eq 0 -and "$result".Trim() -eq "1")
    } finally {
        if ($null -eq $oldHost) { Remove-Item Env:PGHOST -ErrorAction SilentlyContinue } else { $env:PGHOST = $oldHost }
        if ($null -eq $oldPort) { Remove-Item Env:PGPORT -ErrorAction SilentlyContinue } else { $env:PGPORT = $oldPort }
        if ($null -eq $oldUser) { Remove-Item Env:PGUSER -ErrorAction SilentlyContinue } else { $env:PGUSER = $oldUser }
        if ($null -eq $oldPassword) { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue } else { $env:PGPASSWORD = $oldPassword }
        if ($null -eq $oldTimeout) { Remove-Item Env:PGCONNECT_TIMEOUT -ErrorAction SilentlyContinue } else { $env:PGCONNECT_TIMEOUT = $oldTimeout }
    }
}

function Resolve-PostgreSQL {
    if ([string]::IsNullOrWhiteSpace($MetadataUrlOverride)) {
        Write-Receipt "POSTGRES_METADATA_RESOLVED" "pinned" @{ version = $PinnedPgVersion; host = ([Uri]$PinnedPgUrl).Host }
        return [pscustomobject]@{ version = $PinnedPgVersion; url = $PinnedPgUrl; sha256 = $PinnedPgSha256 }
    }
    Assert-AllowedHost $MetadataUrlOverride
    $tmp = Join-Path $env:TEMP ("tonevyra-pg-meta-" + [Guid]::NewGuid().ToString("N") + ".json")
    Invoke-WebRequest -Uri $MetadataUrlOverride -OutFile $tmp -UseBasicParsing -TimeoutSec 120
    $m = Get-Content -LiteralPath $tmp -Raw | ConvertFrom-Json
    Remove-Item -LiteralPath $tmp -Force
    if ($m.schema_version -ne "t033.postgresql.resolution.v1") { throw "T033-PG-METADATA-004 metadata schema mismatch" }
    if ($m.channel -ne "latest-stable" -or $m.release_status -ne "stable" -or $m.prerelease -ne $false) { throw "T033-PG-METADATA-004 prerelease/channel forbidden" }
    if ($m.metadata_signature_verified -ne $true) { throw "T033-PG-METADATA-004 metadata signature not verified" }
    if ($m.installer_signature_required -ne $true) { throw "T033-PG-INTEGRITY-006 installer signature required" }
    Assert-AllowedHost $m.url
    Write-Receipt "POSTGRES_METADATA_RESOLVED" "remote" @{ version = $m.version; host = ([Uri]$m.url).Host }
    return [pscustomobject]@{ version = $m.version; url = $m.url; sha256 = ($m.sha256).ToLowerInvariant() }
}

function Get-EdbInstallerLogTail {
    # The BitRock/EDB installer writes install-postgresql.log to %TEMP%.
    $candidates = @(
        (Join-Path $env:TEMP "install-postgresql.log"),
        (Join-Path $PgPrefix "install-postgresql.log")
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) {
            return (Get-Content -LiteralPath $c -Tail 25 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
        }
    }
    return ""
}

function Remove-TonevyraOwnedPostgres {
    # Removes ONLY the Tonevyra-owned PostgreSQL service and dedicated prefix.
    # Never touches a user-managed PostgreSQL (a service not named exactly
    # 'TonevyraPostgreSQL').
    $svc = Get-PgServiceObject
    if ($svc) {
        try { Stop-Service -Name $PgService -Force -ErrorAction SilentlyContinue } catch { }
        Start-Sleep -Seconds 2
        & "$env:SystemRoot\System32\sc.exe" delete $PgService | Out-Null
        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $deadline -and (Get-PgServiceObject)) { Start-Sleep -Seconds 1 }
    }
    # Free the port from any lingering postgres process bound to it.
    try {
        Get-NetTCPConnection -LocalPort $PgPort -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    } catch { }
    if (Test-Path -LiteralPath $PgPrefix) {
        Remove-Item -LiteralPath $PgPrefix -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Receipt "POSTGRES_CLEANUP" "removed-orphaned-service"
}

function Install-PostgreSQL {
    $existing = Get-PgServiceObject
    if ($existing) {
        $envPath = Join-Path $InstallRoot ".env"
        if ((Test-Path -LiteralPath $envPath) -or (-not [string]::IsNullOrWhiteSpace($script:AdminPassword))) {
            # Reusable: a saved deployment (.env) to verify, or an admin password
            # override to re-bootstrap with.
            Write-Step "POSTGRES_READY" "Existing Tonevyra PostgreSQL service detected; reusing it."
            Write-Receipt "POSTGRES_READY" "existing"
            return
        }
        # Orphaned Tonevyra-owned service from an incomplete prior attempt: no
        # saved credentials and no admin override. DB bootstrap never completed,
        # so there is no Tonevyra user data to preserve -> remove and reinstall.
        Write-Step "POSTGRES_CLEANUP" "Removing orphaned Tonevyra PostgreSQL service from an incomplete prior attempt."
        Remove-TonevyraOwnedPostgres
    }
    # Clean a Tonevyra-owned leftover prefix from a previous failed attempt. This
    # only touches our dedicated path, never a user-managed PostgreSQL.
    if (Test-Path -LiteralPath $PgPrefix) {
        Write-Step "POSTGRES_CLEANUP" "Removing Tonevyra-owned PostgreSQL leftover before reinstall."
        Remove-Item -LiteralPath $PgPrefix -Recurse -Force -ErrorAction SilentlyContinue
    }

    $res = Resolve-PostgreSQL
    $installer  = Join-Path $env:TEMP ("tonevyra-pg-" + [Guid]::NewGuid().ToString("N") + ".exe")
    $partial    = $installer + ".partial"
    $optionFile = Join-Path $env:TEMP ("tonevyra-pg-opt-" + [Guid]::NewGuid().ToString("N") + ".conf")
    $superPassword = [Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N")
    try {
        Write-Step "POSTGRES_DOWNLOADING" ("Downloading PostgreSQL " + $res.version + ".")
        Invoke-WebRequest -Uri $res.url -OutFile $partial -UseBasicParsing -TimeoutSec $DownloadTimeoutSec

        Write-Step "POSTGRES_HASH_VERIFYING" "Verifying installer SHA-256."
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $partial).Hash.ToLowerInvariant()
        if ($hash -ne $res.sha256) { throw "T033-PG-INTEGRITY-006 PostgreSQL SHA-256 mismatch" }
        Move-Item -LiteralPath $partial -Destination $installer -Force

        Write-Step "POSTGRES_SIGNATURE_VERIFYING" "Verifying installer Authenticode signature."
        $sig = Get-AuthenticodeSignature -FilePath $installer
        if ($sig.Status -ne "Valid") { throw "T033-PG-INTEGRITY-006 PostgreSQL Authenticode signature invalid" }

        # Remove the mark-of-the-web (Zone.Identifier) added to downloaded files.
        # Otherwise Windows shows a hidden "Open File - Security Warning" dialog
        # when the installer is launched, which silently blocks the unattended
        # flow until the user presses Enter/Run on a window they cannot see.
        Unblock-File -LiteralPath $installer -ErrorAction SilentlyContinue

        # Install into the Tonevyra-owned prefix. Only the super password is kept
        # out of the process command line (option file, ACL-locked). NOTE:
        # `unattendedmodeui` is NOT a valid option-file key for the EDB installer
        # (it is a command-line flag only); putting it in the file makes the
        # installer reject the whole --optionfile. It is passed on the CLI below.
        @(
            "mode=unattended",
            "prefix=$PgPrefix",
            "datadir=$PgDataDir",
            "servicename=$PgService",
            "serverport=$PgPort",
            "superpassword=$superPassword"
        ) | Set-Content -LiteralPath $optionFile -Encoding ASCII
        Protect-TempSecretFile $optionFile

        Write-Step "POSTGRES_INSTALLING" "Running PostgreSQL unattended installer (several minutes)."
        try {
            Invoke-Timed $installer @("--mode", "unattended", "--optionfile", $optionFile, "--unattendedmodeui", "none") $InstallTimeoutSec "T033-PG-INSTALL-007" "PostgreSQL unattended install"
        } catch {
            $edb = Get-EdbInstallerLogTail
            if ($edb) { throw ($_.Exception.Message + [Environment]::NewLine + "PostgreSQL installer log (tail):" + [Environment]::NewLine + $edb) }
            throw
        }

        Write-Step "POSTGRES_WAIT_READY" "Waiting for PostgreSQL service to start."
        $deadline = (Get-Date).AddMinutes(3)
        while ((Get-Date) -lt $deadline) {
            $svc = Get-PgServiceObject
            if ($svc -and $svc.Status -eq "Running") {
                Write-Step "POSTGRES_ADMIN_VERIFYING" "Verifying PostgreSQL postgres admin password."
                if (-not (Test-PostgresAdminPassword $superPassword)) {
                    throw "T033-PG-INSTALL-007 PostgreSQL installed, but postgres admin password verification failed. A previous partial TonevyraPostgreSQL installation may remain on this PC."
                }
                $script:AdminPassword = $superPassword
                Write-Receipt "POSTGRES_READY" "installed" @{ version = $res.version; port = $PgPort; prefix = $PgPrefix }
                return
            }
            Start-Sleep -Seconds 2
        }
        throw "T033-DB-READY-016 PostgreSQL service did not become ready"
    } finally {
        foreach ($f in @($partial, $installer, $optionFile)) {
            Remove-TempFile $f
        }
    }
}

function Save-Credential([string]$AppPassword) {
    $secretDir = Join-Path $ConfigRoot "secrets"
    New-Item -ItemType Directory -Force -Path $secretDir | Out-Null
    $secretPath = Join-Path $secretDir "postgres-password.dpapi"
    ConvertTo-SecureString -String $AppPassword -AsPlainText -Force |
        ConvertFrom-SecureString | Set-Content -LiteralPath $secretPath -Encoding ASCII
    @{
        database = @{
            host = $PgHost; port = $PgPort; name = $Database; user = $Role
            credential_file = $secretPath
        }
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $ConfigRoot "database.json") -Encoding UTF8
    Write-Receipt "DB_CREDENTIAL_STORING" "ok"
}

function Write-EnvFile([string]$Url) {
    # The running Agent reads TONEVYRA_DATABASE_URL from {InstallRoot}\.env
    # (pydantic-settings env_file). This is the functional runtime credential source.
    $envPath  = Join-Path $InstallRoot ".env"
    $modelDir = Join-Path $InstallRoot "models\qwen3-vl-4b-instruct"
    $manifest = Join-Path $modelDir "model_manifest.json"
    $documentsDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
    if ([string]::IsNullOrWhiteSpace($documentsDir)) {
        throw "T033-INPUT-DIR-001 Windows Documents folder could not be resolved"
    }
    $inputDir = Join-Path $documentsDir "TonevyraAI\input"
    New-Item -ItemType Directory -Force -Path $inputDir | Out-Null
    $env:TONEVYRA_INPUT_DIR = $inputDir

    [string[]]$lines = @(
        "TONEVYRA_DATABASE_URL=$Url",
        "TONEVYRA_INPUT_DIR=$inputDir",
        "TONEVYRA_MODEL_OFFLINE=true",
        "TONEVYRA_VISION_BACKEND=qwen3vl",
        "TONEVYRA_LIGHTROOM_BACKEND=lightroom",
        "TONEVYRA_QWEN3_MODEL_PATH=$modelDir",
        "TONEVYRA_QWEN3_MANIFEST_PATH=$manifest",
        "TONEVYRA_MODEL_MANIFEST_PATH=$manifest",
        "TONEVYRA_PLANNER_API_MODE=local_server",
        "TONEVYRA_PLANNER_API_BASE_URL=http://127.0.0.1:8000",
        "TONEVYRA_PLANNER_API_KEY=secret-key",
        "TONEVYRA_PLANNER_API_ALLOWED_HOST=127.0.0.1"
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllLines($envPath, $lines, $utf8NoBom)
    Write-Receipt "INPUT_DIRECTORY_PREPARING" "ok" @{ input_dir = $inputDir }
}

function Read-DatabaseUrl([string]$EnvPath) {
    $line = Get-Content -LiteralPath $EnvPath -ErrorAction Stop |
        Where-Object { $_ -match '^TONEVYRA_DATABASE_URL=' } |
        Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($line)) {
        throw "T033-DB-BOOTSTRAP-008 Existing .env has no TONEVYRA_DATABASE_URL"
    }
    return $line.Substring("TONEVYRA_DATABASE_URL=".Length)
}

function Initialize-Database {
    Write-Step "DB_BOOTSTRAPPING" "Preparing the Tonevyra database."
    $psql = Get-PsqlPath
    if (-not $psql) { throw "T033-DB-READY-016 psql.exe not found after PostgreSQL install" }

    if ([string]::IsNullOrWhiteSpace($script:AdminPassword)) {
        # Existing service, no admin password: verify already-saved Tonevyra creds.
        $envPath = Join-Path $InstallRoot ".env"
        if (Test-Path -LiteralPath $envPath) {
            Push-Location $InstallRoot
            try {
                $evidence = Join-Path $ReceiptRoot "database_bootstrap_evidence.json"
                Invoke-Timed $AppExe @("installer-db", "verify", "--credential-store-verified", "--output", $evidence) $CommandTimeoutSec "T033-DB-SCHEMA-020" "existing DB verify"
                $existingUrl = Read-DatabaseUrl $envPath
                Write-EnvFile $existingUrl
                $env:TONEVYRA_DATABASE_URL = $existingUrl
                Write-Receipt "DB_SCHEMA_VERIFYING" "existing-ok" @{ evidence = $evidence }
                return
            } finally { Pop-Location }
        }
        throw "T033-DB-BOOTSTRAP-008 Existing TonevyraPostgreSQL service found but admin password is unavailable and no saved Tonevyra credentials could be verified. Provide TONEVYRA_T033_POSTGRES_ADMIN_PASSWORD and re-run."
    }

    $appPassword = [Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N")
    $env:PGHOST = $PgHost
    $env:PGPORT = "$PgPort"
    $env:PGUSER = "postgres"
    $env:PGPASSWORD = $script:AdminPassword
    $env:PGCONNECT_TIMEOUT = "15"
    try {
        Write-Step "DB_ROLE_DATABASE" "Creating/verifying role and database."
        $roleExists = & $psql -w -tAc "select 1 from pg_roles where rolname = '$Role'"
        if ($LASTEXITCODE -ne 0) { throw "T033-DB-BOOTSTRAP-008 role probe failed" }
        if ("$roleExists".Trim() -eq "1") {
            & $psql -w -q -c "alter role $Role with login password '$appPassword'" *> $null
        } else {
            & $psql -w -q -c "create role $Role login password '$appPassword'" *> $null
        }
        if ($LASTEXITCODE -ne 0) { throw "T033-DB-BOOTSTRAP-008 role create/alter failed" }

        $dbExists = & $psql -w -tAc "select 1 from pg_database where datname = '$Database'"
        if ($LASTEXITCODE -ne 0) { throw "T033-DB-BOOTSTRAP-008 database probe failed" }
        if ("$dbExists".Trim() -ne "1") {
            & $psql -w -q -c "create database $Database owner $Role" *> $null
            if ($LASTEXITCODE -ne 0) { throw "T033-DB-BOOTSTRAP-008 database create failed" }
        }
    } finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }

    $url = "postgresql+psycopg://${Role}:$appPassword@${PgHost}:$PgPort/$Database"
    Save-Credential $appPassword
    Write-EnvFile $url
    $env:TONEVYRA_DATABASE_URL = $url

    Push-Location $InstallRoot
    try {
        Write-Step "DB_SCHEMA_BOOTSTRAPPING" "Applying Alembic schema (upgrade head)."
        Invoke-Timed $AppExe @("installer-db", "bootstrap-schema") $CommandTimeoutSec "T033-DB-MIGRATION-019" "schema bootstrap"

        $evidence = Join-Path $ReceiptRoot "database_bootstrap_evidence.json"
        Write-Step "DB_SCHEMA_VERIFYING" "Verifying required objects and privileges."
        try {
            Invoke-Timed $AppExe @("installer-db", "verify", "--credential-store-verified", "--output", $evidence) $CommandTimeoutSec "T033-DB-SCHEMA-020" "DB verify"
        } catch {
            # Surface exactly which completion gate(s) failed from the evidence file.
            $failed = ""
            if (Test-Path -LiteralPath $evidence) {
                try {
                    $ev = Get-Content -LiteralPath $evidence -Raw | ConvertFrom-Json
                    $gates = @("postgres_service_ready","role_exists","database_exists","runtime_role_non_superuser","localhost_only","alembic_head_matches","read_write_smoke_rolled_back","credential_store_verified")
                    $bad = @()
                    foreach ($g in $gates) { if ($ev.$g -ne $true) { $bad += $g } }
                    if ($bad.Count -gt 0) { $failed = "Failed gates: " + ($bad -join ", ") }
                } catch { }
            }
            if ($failed) { throw ($_.Exception.Message + [Environment]::NewLine + $failed + [Environment]::NewLine + "Evidence: " + $evidence) }
            throw
        }

        Write-Step "DB_SMOKE" "Running read/write smoke transaction."
        Invoke-Timed $AppExe @("db-smoke-test") $CommandTimeoutSec "T033-DB-SCHEMA-020" "DB smoke test"
        Write-Receipt "DB_SCHEMA_VERIFYING" "ok" @{ evidence = $evidence }
    } finally { Pop-Location }
}

function Install-LightroomPlugin {
    Write-Step "PLUGIN_INSTALLING" "Detecting Lightroom Classic."
    $installed = $false
    $running = $null -ne (Get-Process -Name "Lightroom" -ErrorAction SilentlyContinue)
    $paths = @(
        "$env:ProgramFiles\Adobe\Adobe Lightroom Classic\Lightroom.exe",
        "${env:ProgramFiles(x86)}\Adobe\Adobe Lightroom Classic\Lightroom.exe"
    )
    foreach ($p in $paths) { if ($p -and (Test-Path -LiteralPath $p)) { $installed = $true } }

    $modulesDir = Join-Path $env:APPDATA "Adobe\Lightroom\Modules"
    New-Item -ItemType Directory -Force -Path $modulesDir | Out-Null
    $dest = Join-Path $modulesDir "TonevyraAI.lrplugin"
    $src  = Join-Path $InstallRoot "lightroom\TonevyraAI.lrplugin"
    $bridgeRoot = Join-Path $InstallRoot "runtime\bridge"
    if ($bridgeRoot.Contains("]]")) {
        throw "T033-LIGHTROOM-CONFIG bridge path contains an unsupported Lua long-string terminator"
    }
    $configPath = Join-Path $src "BridgeConfig.lua"
    $configText = "return {" + [Environment]::NewLine +
        "  root = [[$bridgeRoot]]," + [Environment]::NewLine +
        "}" + [Environment]::NewLine
    [IO.File]::WriteAllText($configPath, $configText, (New-Object System.Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
    Copy-Item -LiteralPath $src -Destination $dest -Recurse -Force
    $status = if ($running) { "RESTART_REQUIRED" } elseif ($installed) { "INSTALLED" } else { "INSTALLED_LIGHTROOM_NOT_DETECTED" }
    Write-Receipt "PLUGIN_INSTALLING" $status @{
        modules_dir = $modulesDir
        bridge_root = $bridgeRoot
        lightroom_detected = $installed
        lightroom_running = $running
    }
    return $status
}

function Repair-LegacyModelTasks {
    $evidence = Join-Path $ReceiptRoot "legacy_model_task_repair.json"
    Write-Step "MODEL_TASK_REPAIR" "Requeueing tasks created by the legacy mock model configuration."
    Invoke-Timed $AppExe @("installer-requeue-legacy-model-tasks", "--output", $evidence) $CommandTimeoutSec "T033-MODEL-REPAIR" "legacy model task repair"
    Write-Receipt "MODEL_TASK_REPAIR" "ok" @{ evidence = $evidence }
}

function Enable-Autostart {
    Write-Step "STARTUP_REGISTERING" "Enabling current-user autostart."
    try {
        Invoke-Timed $AppExe @("startup", "enable") $CommandTimeoutSec "T033-STARTUP" "autostart enable"
        Write-Receipt "STARTUP_REGISTERING" "ok"
    } catch {
        # Autostart is optional; never fail the install on it.
        Write-Receipt "STARTUP_REGISTERING" "skipped" @{ reason = $_.Exception.Message }
    }
}

function Invoke-Doctor {
    Push-Location $InstallRoot
    try {
        Write-Step "RUNTIME_INIT" "Creating runtime directories."
        Invoke-Timed $AppExe @("init") $CommandTimeoutSec "T033-DOCTOR" "runtime init"
        Write-Step "POST_INSTALL_DOCTOR" "Running post-install doctor gate."
        Invoke-Timed $AppExe @("doctor") $CommandTimeoutSec "T033-DOCTOR" "post-install doctor"
        Write-Receipt "POST_INSTALL_DOCTOR" "ok"
    } finally { Pop-Location }
}

# --- main --------------------------------------------------------------------
try {
    if (Get-Process -Name "TonevyraAI" -ErrorAction SilentlyContinue) {
        throw "TonevyraAI.exe is running. Exit Tonevyra AI from the tray before installing."
    }
    if (-not (Test-Path -LiteralPath $AppExe)) { throw "T033-PAYLOAD-002 missing TonevyraAI.exe" }
    if (-not (Test-Path -LiteralPath $ModelManifest)) { throw "T033-PAYLOAD-002 missing bundled model manifest" }
    Write-Receipt "BUNDLED_RUNTIME_VERIFIED" "ok"

    Install-PostgreSQL
    Initialize-Database
    Repair-LegacyModelTasks
    $lightroom = Install-LightroomPlugin
    Enable-Autostart
    Invoke-Doctor

    Write-Receipt "COMPLETED" "ok" @{ lightroom = $lightroom; install_root = $InstallRoot }
    $result = if ($lightroom -eq "RESTART_REQUIRED") { "SUCCESS_RESTART_LIGHTROOM" } else { "SUCCESS" }
    Set-Content -LiteralPath $ResultPath -Value $result -Encoding UTF8
    Write-Host "Tonevyra AI provisioning completed."
    exit 0
} catch {
    $msg = $_.Exception.Message
    try { Write-Receipt "FAILED" "error" @{ error = $msg } } catch { }
    $detail = @(
        "Tonevyra AI database setup failed.",
        ("Error: " + $msg),
        "",
        ("App files are installed at: " + $InstallRoot),
        ("Transcript log: " + $Transcript),
        ("Receipt: " + $ReceiptPath),
        "",
        "You can retry provisioning without reinstalling (run as Administrator):",
        ("  powershell -ExecutionPolicy Bypass -File `"" + (Join-Path $InstallRoot "Invoke-TonevyraProvision.ps1") + "`" -InstallRoot `"" + $InstallRoot + "`" -ResultPath `"$env:TEMP\tonevyra-retry.txt`"")
    ) -join [Environment]::NewLine
    try { Set-Content -LiteralPath $ResultPath -Value $detail -Encoding UTF8 } catch { }
    Write-Error $msg
    exit 1
} finally {
    try { Stop-Transcript | Out-Null } catch { }
}
