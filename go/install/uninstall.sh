#!/opt/bin/sh

set -eu
APP_ROOT="${APP_ROOT:-/opt/share/keenetic-vpn-panel}"
APP_DIR="${APP_DIR:-${APP_ROOT}/go}"
INIT_SCRIPT="${INIT_SCRIPT:-/opt/etc/init.d/S99keenetic-vpn-panel}"
KEEP_CONFIG="${KEEP_CONFIG:-1}"

if [ -x "$INIT_SCRIPT" ]; then "$INIT_SCRIPT" stop || true; rm -f "$INIT_SCRIPT"; fi
if [ "$KEEP_CONFIG" = "1" ] && [ -f "${APP_DIR}/config.json" ]; then
  mkdir -p "${APP_ROOT}/migration-backups"
  cp "${APP_DIR}/config.json" "${APP_ROOT}/migration-backups/config.uninstall.$(date +%Y%m%d-%H%M%S 2>/dev/null || echo now).json"
fi
rm -rf "$APP_DIR"
echo "Keenetic VPN Panel Go удалена. Резервные копии конфигурации сохранены в ${APP_ROOT}/migration-backups."
