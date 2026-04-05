#!/opt/bin/sh

APP_DIR="/opt/share/keenetic-vpn-panel"
PYTHON_BIN="/opt/bin/python3"
LOG_FILE="/opt/var/log/keenetic-vpn-panel.log"

cd "$APP_DIR" || exit 1

exec "$PYTHON_BIN" vpn_panel_server.py >> "$LOG_FILE" 2>&1
