#!/opt/bin/sh

export SSL_CERT_FILE=/opt/etc/ssl/certs/ca-certificates.crt
export HOME=/opt/home/admin
PATH=/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin

APP_DIR="/opt/share/keenetic-vpn-panel"
PYTHON_BIN="/opt/bin/python3"
LOG_FILE="/opt/var/log/keenetic-vpn-panel.log"

cd "$APP_DIR" || exit 1

exec "$PYTHON_BIN" vpn_panel_server.py >> "$LOG_FILE" 2>&1
