param(
  [Parameter(Mandatory=$true)][string]$InstallerPath,
  [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$signature = Get-AuthenticodeSignature -FilePath $InstallerPath
$evidence = [ordered]@{
  schema_version = 't033.windows.live.v1'
  ticket = 'T033'
  platform = 'windows'
  architecture = if ([Environment]::Is64BitOperatingSystem) { 'x64' } else { 'unsupported' }
  installer_path = (Split-Path -Leaf $InstallerPath)
  installer_signature_valid = ($signature.Status -eq 'Valid')
  python_3119_bundled = $false
  postgres_installer_downloaded = $false
  postgres_installer_not_bundled = $false
  postgres_service_ok = $false
  database_ok = $false
  agent_ok = $false
  uninstall_data_preserved = $false
  evidence_status = 'COLLECTOR_TEMPLATE_REQUIRES_MANUAL_INSTALL_SEQUENCE'
}
$dir = Split-Path -Parent $OutputPath
if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$evidence | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $OutputPath
Write-Host "Wrote $OutputPath"
