#!/opt/bin/sh

set -eu

REPO_OWNER="${REPO_OWNER:-Phaum}"
REPO_NAME="${REPO_NAME:-keenetic-vpn-panel}"
BRANCH="${BRANCH:-master}"
APP_DIR="${APP_DIR:-/opt/share/keenetic-vpn-panel}"
TMP_DIR="/opt/tmp/${REPO_NAME}-install.$$"
ARCHIVE_URL="https://codeload.github.com/${REPO_OWNER}/${REPO_NAME}/tar.gz/refs/heads/${BRANCH}"
INIT_SCRIPT_PATH="/opt/etc/init.d/S99keenetic-vpn-panel"

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT INT TERM

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

install_pkg_if_missing() {
  PKG="$1"
  if ! opkg list-installed 2>/dev/null | grep -q "^${PKG} "; then
    opkg install "$PKG"
  fi
}

download_file() {
  URL="$1"
  OUT="$2"

  if need_cmd curl; then
    curl -fsSL "$URL" -o "$OUT"
    return 0
  fi

  if need_cmd wget; then
    wget -O "$OUT" "$URL"
    return 0
  fi

  echo "Neither curl nor wget found"
  exit 1
}

if [ ! -d /opt ]; then
  echo "/opt not found. Entware must be installed first."
  exit 1
fi

if ! need_cmd opkg; then
  echo "opkg not found. Run this script inside Entware."
  exit 1
fi

mkdir -p "$TMP_DIR"

opkg update
install_pkg_if_missing ca-certificates
install_pkg_if_missing python3
if ! need_cmd curl && ! need_cmd wget; then
  install_pkg_if_missing wget-ssl
fi

ARCHIVE_PATH="${TMP_DIR}/project.tar.gz"
download_file "$ARCHIVE_URL" "$ARCHIVE_PATH"
tar -tzf "$ARCHIVE_PATH" >/dev/null 2>&1 || {
  echo "Downloaded archive is invalid"
  exit 1
}

ROOT_DIR="$(tar -tzf "$ARCHIVE_PATH" | head -n 1 | cut -d/ -f1)"
if [ -z "$ROOT_DIR" ]; then
  echo "Could not detect project root directory inside archive"
  exit 1
fi

BACKUP_CONFIG=""
if [ -f "${APP_DIR}/config.json" ]; then
  BACKUP_CONFIG="${TMP_DIR}/config.json.backup"
  cp "${APP_DIR}/config.json" "$BACKUP_CONFIG"
fi

tar -xzf "$ARCHIVE_PATH" -C "$TMP_DIR"

EXTRACTED_DIR="${TMP_DIR}/${ROOT_DIR}"
if [ ! -d "$EXTRACTED_DIR" ]; then
  echo "Extracted project directory not found"
  exit 1
fi

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
cp -R "${EXTRACTED_DIR}/." "$APP_DIR/"

if [ -n "$BACKUP_CONFIG" ] && [ -f "$BACKUP_CONFIG" ]; then
  cp "$BACKUP_CONFIG" "${APP_DIR}/config.json"
fi

mkdir -p "${APP_DIR}/deploy/entware"
mkdir -p "/opt/etc/init.d"

if [ ! -f "${APP_DIR}/config.json" ]; then
  echo "config.json not found after extracting the project"
  exit 1
fi

APP_DIR="$APP_DIR" /opt/bin/python3 - <<'PY'
import json
import os
import socket
from pathlib import Path

app_dir = Path(os.environ["APP_DIR"])
config_path = app_dir / "config.json"
config = json.loads(config_path.read_text(encoding="utf-8"))

def port_is_free(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()

config["panel"]["host"] = "0.0.0.0"

current_port = int(config["panel"].get("port", 18090))
candidate_ports = [18090, 18091, 18092, 18093, 8090]
if current_port == 8088 or not port_is_free("0.0.0.0", current_port):
    for port in candidate_ports:
        if port_is_free("0.0.0.0", port):
            current_port = port
            break

config["panel"]["port"] = current_port
config["autostart"]["enabled"] = True
config["autostart"]["app_dir"] = str(app_dir)
config["autostart"]["python_bin"] = "/opt/bin/python3"
config["autostart"]["log_file"] = "/opt/var/log/keenetic-vpn-panel.log"
config["autostart"]["pid_file"] = "/opt/var/run/keenetic-vpn-panel.pid"
config["autostart"]["start_script_path"] = str(app_dir / "deploy" / "entware" / "start_vpn_panel.sh")
config["autostart"]["init_script_path"] = "/opt/etc/init.d/S99keenetic-vpn-panel"

config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
PY

cat > "${APP_DIR}/deploy/entware/start_vpn_panel.sh" <<EOF
#!/opt/bin/sh

export SSL_CERT_FILE=/opt/etc/ssl/certs/ca-certificates.crt
export HOME=/root
PATH=/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin

APP_DIR="${APP_DIR}"
PYTHON_BIN="/opt/bin/python3"
LOG_FILE="/opt/var/log/keenetic-vpn-panel.log"

cd "\$APP_DIR" || exit 1

exec "\$PYTHON_BIN" vpn_panel_server.py >> "\$LOG_FILE" 2>&1
EOF

cat > "${APP_DIR}/deploy/entware/S99keenetic-vpn-panel" <<EOF
#!/opt/bin/sh

NAME="keenetic-vpn-panel"
APP_DIR="${APP_DIR}"
START_SCRIPT="${APP_DIR}/deploy/entware/start_vpn_panel.sh"
PID_FILE="/opt/var/run/keenetic-vpn-panel.pid"

start() {
  if [ -f "\$PID_FILE" ] && kill -0 "\$(cat "\$PID_FILE")" 2>/dev/null; then
    echo "\$NAME already running"
    return 0
  fi

  mkdir -p /opt/var/run
  "\$START_SCRIPT" &
  echo \$! > "\$PID_FILE"
  echo "\$NAME started"
}

stop() {
  if [ ! -f "\$PID_FILE" ]; then
    echo "\$NAME is not running"
    return 0
  fi

  PID="\$(cat "\$PID_FILE" 2>/dev/null)"
  if [ -n "\$PID" ] && kill -0 "\$PID" 2>/dev/null; then
    kill "\$PID"
  fi

  rm -f "\$PID_FILE"
  echo "\$NAME stopped"
}

status() {
  if [ -f "\$PID_FILE" ] && kill -0 "\$(cat "\$PID_FILE")" 2>/dev/null; then
    echo "\$NAME is running with PID \$(cat "\$PID_FILE")"
    return 0
  fi

  echo "\$NAME is not running"
  return 1
}

case "\$1" in
  start)
    start
    ;;
  stop)
    stop
    ;;
  restart)
    stop
    sleep 1
    start
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: \$0 {start|stop|restart|status}"
    exit 1
    ;;
esac
EOF

chmod +x "${APP_DIR}/deploy/entware/start_vpn_panel.sh"
chmod +x "${APP_DIR}/deploy/entware/S99keenetic-vpn-panel"

cp "${APP_DIR}/deploy/entware/S99keenetic-vpn-panel" "$INIT_SCRIPT_PATH"
chmod +x "$INIT_SCRIPT_PATH"

"$INIT_SCRIPT_PATH" restart || "$INIT_SCRIPT_PATH" start

PANEL_PORT="$(sed -n 's/.*"port":[[:space:]]*\([0-9][0-9]*\).*/\1/p' "${APP_DIR}/config.json" | head -n 1)"
if [ -z "$PANEL_PORT" ]; then
  PANEL_PORT="18090"
fi

echo ""
echo "Installation completed."
echo "Open the panel from your local network:"
echo "http://<router-lan-ip>:${PANEL_PORT}"
echo ""
echo "Service status:"
echo "${INIT_SCRIPT_PATH} status"
