<#
    Tonevyra AI - Authenticode signing helper (Windows).

    Signs one or more files with a code-signing certificate. Certificate source
    resolution order:
      1. -Thumbprint  : an existing cert already in a certificate store.
      2. -CertPfx     : a PFX file (+ -CertPassword). Use this for a real OV/EV
                        certificate in CI/release.
      3. self-signed  : (default) create/reuse a self-signed CODE SIGNING cert in
                        CurrentUser\My, trust it on THIS machine, and export the
                        public .cer + .pfx to -ExportDir so it can be imported on
                        test machines.

    IMPORTANT: A self-signed certificate does NOT satisfy Windows Smart App
    Control (SAC), which only trusts Microsoft-cloud-known / reputable-CA-signed
    apps. Self-signing only removes SmartScreen "unknown publisher" AFTER the
    exported .cer is imported into Trusted Root + Trusted Publishers on the target
    machine. For release, supply a real OV/EV certificate via -CertPfx.

    Exit code 0 on success (all files carry a signer), non-zero otherwise.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string[]]$Files,
    [string]$Thumbprint = $env:TONEVYRA_SIGN_THUMBPRINT,
    [string]$CertPfx = $env:TONEVYRA_SIGN_PFX,
    [string]$CertPassword = $env:TONEVYRA_SIGN_PFX_PASSWORD,
    [string]$TimestampUrl = $(if ($env:TONEVYRA_SIGN_TIMESTAMP_URL) { $env:TONEVYRA_SIGN_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }),
    [string]$ExportDir = $(if ($env:TONEVYRA_SIGN_EXPORT_DIR) { $env:TONEVYRA_SIGN_EXPORT_DIR } else { "D:\Tonevyra_install\signing" }),
    [string]$SelfSignedPassword = "tonevyra-test"
)

$ErrorActionPreference = "Stop"
$SelfSignedSubject = "CN=Tonevyra AI (Self-Signed Test)"

function Resolve-Cert {
    if (-not [string]::IsNullOrWhiteSpace($Thumbprint)) {
        $clean = ($Thumbprint -replace '[^0-9A-Fa-f]', '')
        foreach ($store in @("Cert:\CurrentUser\My", "Cert:\LocalMachine\My")) {
            $c = Get-ChildItem $store -CodeSigningCert -ErrorAction SilentlyContinue |
                Where-Object { $_.Thumbprint -eq $clean } | Select-Object -First 1
            if ($c) { return $c }
        }
        throw "T033-SIGN code-signing cert with thumbprint $Thumbprint not found in a store."
    }
    if (-not [string]::IsNullOrWhiteSpace($CertPfx)) {
        if (-not (Test-Path -LiteralPath $CertPfx)) { throw "T033-SIGN PFX not found: $CertPfx" }
        $sec = if ([string]::IsNullOrEmpty($CertPassword)) { (New-Object System.Security.SecureString) } else { (ConvertTo-SecureString $CertPassword -AsPlainText -Force) }
        return (Get-PfxCertificate -FilePath $CertPfx -Password $sec)
    }

    # Self-signed fallback (test only).
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert -ErrorAction SilentlyContinue |
        Where-Object { $_.Subject -eq $SelfSignedSubject -and $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date) } |
        Sort-Object NotAfter -Descending | Select-Object -First 1
    if (-not $cert) {
        Write-Host "Creating self-signed code-signing certificate: $SelfSignedSubject"
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $SelfSignedSubject `
            -CertStoreLocation Cert:\CurrentUser\My -KeyUsage DigitalSignature `
            -KeyExportPolicy Exportable -HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears(5)
    }

    # Trust it on THIS machine so signing verifies Valid locally, and export the
    # public cert (+ pfx) so it can be imported on test machines.
    New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null
    $cerPath = Join-Path $ExportDir "TonevyraAI-TestCodeSign.cer"
    $pfxPath = Join-Path $ExportDir "TonevyraAI-TestCodeSign.pfx"
    Export-Certificate -Cert $cert -FilePath $cerPath -Force | Out-Null
    try {
        Export-PfxCertificate -Cert $cert -FilePath $pfxPath `
            -Password (ConvertTo-SecureString $SelfSignedPassword -AsPlainText -Force) -Force | Out-Null
    } catch { }
    foreach ($rootStore in @("Cert:\CurrentUser\Root", "Cert:\CurrentUser\TrustedPublisher")) {
        try {
            $store = Get-Item $rootStore
            $store.Open("ReadWrite")
            if (-not ($store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })) {
                $store.Add($cert)
            }
            $store.Close()
        } catch { }
    }
    Write-Host "Self-signed cert exported to: $cerPath"
    return $cert
}

$cert = Resolve-Cert
if (-not $cert.HasPrivateKey) { throw "T033-SIGN resolved certificate has no private key; cannot sign." }

$failed = @()
foreach ($file in $Files) {
    if (-not (Test-Path -LiteralPath $file)) { throw "T033-SIGN file to sign not found: $file" }
    $params = @{ FilePath = $file; Certificate = $cert; HashAlgorithm = "SHA256" }
    $sig = $null
    try {
        $sig = Set-AuthenticodeSignature @params -TimestampServer $TimestampUrl
    } catch {
        Write-Warning "Timestamping failed for $file ($($_.Exception.Message)); signing without a timestamp."
    }
    if (-not $sig -or $sig.Status -ne "Valid") {
        $sig = Set-AuthenticodeSignature @params
    }
    $verify = Get-AuthenticodeSignature -LiteralPath $file
    if ($null -eq $verify.SignerCertificate) {
        $failed += $file
        Write-Warning "No signer certificate embedded for $file (status: $($verify.Status))."
    } else {
        Write-Host ("Signed: " + $file + " [" + $verify.Status + "] by " + $verify.SignerCertificate.Subject)
    }
}

if ($failed.Count -gt 0) {
    Write-Error ("T033-SIGN failed to sign: " + ($failed -join ", "))
    exit 1
}
Write-Host "All files signed."
exit 0
