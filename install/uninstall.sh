#!/opt/bin/sh

set -eu

APP_DIR="${APP_DIR:-/opt/share/keenetic-vpn-panel}"
INIT_SCRIPT_PATH="${INIT_SCRIPT_PATH:-/opt/etc/init.d/S99keenetic-vpn-panel}"

if [ -x "$INIT_SCRIPT_PATH" ]; then
  "$INIT_SCRIPT_PATH" stop || true
  rm -f "$INIT_SCRIPT_PATH"
fi

rm -rf "$APP_DIR"

echo "keenetic-vpn-panel removed"
