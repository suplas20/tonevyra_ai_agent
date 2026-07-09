#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 3 ]]; then
  echo "usage: $0 <app-path> <pkg-path> <output-json>" >&2
  exit 2
fi
APP="$1"; PKG="$2"; OUT="$3"
mkdir -p "$(dirname "$OUT")"
arch="$(uname -m)"
app_ok=false; pkg_ok=false; gatekeeper_ok=false; staple_app=false; staple_pkg=false
codesign --verify --deep --strict --verbose=2 "$APP" >/dev/null 2>&1 && app_ok=true || true
pkgutil --check-signature "$PKG" >/dev/null 2>&1 && pkg_ok=true || true
spctl --assess --type execute --verbose=4 "$APP" >/dev/null 2>&1 && gatekeeper_ok=true || true
xcrun stapler validate "$APP" >/dev/null 2>&1 && staple_app=true || true
xcrun stapler validate "$PKG" >/dev/null 2>&1 && staple_pkg=true || true
cat > "$OUT" <<JSON
{
  "schema_version": "t033.macos.live.v1",
  "ticket": "T033",
  "platform": "macos",
  "architecture": "$arch",
  "developer_id_application_valid": $app_ok,
  "developer_id_installer_valid": $pkg_ok,
  "notarization_accepted": false,
  "staple_valid": $staple_app,
  "pkg_staple_valid": $staple_pkg,
  "gatekeeper_accepted": $gatekeeper_ok,
  "python_3119_bundled": false,
  "postgres_installer_downloaded": false,
  "postgres_installer_not_bundled": false,
  "database_ok": false,
  "agent_ok": false,
  "uninstall_data_preserved": false,
  "evidence_status": "COLLECTOR_TEMPLATE_REQUIRES_MANUAL_INSTALL_SEQUENCE"
}
JSON
echo "Wrote $OUT"
