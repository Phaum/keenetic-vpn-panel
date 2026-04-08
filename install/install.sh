#!/opt/bin/sh

set -eu

REPO_OWNER="${REPO_OWNER:-Phaum}"
REPO_NAME="${REPO_NAME:-keenetic-vpn-panel}"
BRANCH="${BRANCH:-master}"
APP_DIR="${APP_DIR:-/opt/share/keenetic-vpn-panel}"
TMP_DIR="/opt/tmp/${REPO_NAME}-install.$$"
ARCHIVE_URL="https://codeload.github.com/${REPO_OWNER}/${REPO_NAME}/tar.gz/refs/heads/${BRANCH}"
INIT_SCRIPT_PATH="/opt/etc/init.d/S99keenetic-vpn-panel"
ADGUARDVPN_INSTALLER_URL="https://raw.githubusercontent.com/AdguardTeam/AdGuardVPNCLI/master/scripts/release/install.sh"
ADGUARDVPN_HOME="${ADGUARDVPN_HOME:-/opt/home/admin}"
ADGUARDVPN_BIN="/opt/adguardvpn_cli/adguardvpn-cli"
ADGUARDVPN_LINK="/opt/bin/adguardvpn-cli"

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

install_first_available_pkg() {
  for PKG in "$@"; do
    if opkg info "$PKG" >/dev/null 2>&1; then
      install_pkg_if_missing "$PKG"
      return 0
    fi
  done
  return 1
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

detect_lan_ip() {
  if need_cmd ip; then
    CANDIDATE="$(ip -4 -o addr show up 2>/dev/null \
      | awk '
          /inet / {
            split($4, pair, "/")
            ip = pair[1]
            if (ip ~ /^127\./) next
            if (ip ~ /^192\.168\./) { print ip; exit }
            if (best == "" && ip ~ /^10\./) best = ip
            if (fallback == "" && ip ~ /^172\.(1[6-9]|2[0-9]|3[0-1])\./) fallback = ip
          }
          END {
            if (best != "") print best
            else if (fallback != "") print fallback
          }
        ' | head -n 1)"
    if [ -n "$CANDIDATE" ]; then
      echo "$CANDIDATE"
      return 0
    fi
  fi

  echo "192.168.1.1"
}

install_adguardvpn_cli() {
  mkdir -p "$ADGUARDVPN_HOME"

  if [ -x "$ADGUARDVPN_BIN" ]; then
    ln -sf "$ADGUARDVPN_BIN" "$ADGUARDVPN_LINK"
    return 0
  fi

  INSTALLER_PATH="${TMP_DIR}/adguardvpn-install.sh"
  download_file "$ADGUARDVPN_INSTALLER_URL" "$INSTALLER_PATH"
  chmod +x "$INSTALLER_PATH"

  HOME="$ADGUARDVPN_HOME" sh "$INSTALLER_PATH" -a n

  if [ ! -x "$ADGUARDVPN_BIN" ]; then
    echo "adguardvpn-cli installation finished, but $ADGUARDVPN_BIN was not found"
    exit 1
  fi

  ln -sf "$ADGUARDVPN_BIN" "$ADGUARDVPN_LINK"
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
install_pkg_if_missing curl
install_pkg_if_missing sudo
install_pkg_if_missing python3
install_pkg_if_missing ipset
install_pkg_if_missing redsocks
install_first_available_pkg ip-full ip || true
if ! need_cmd curl && ! need_cmd wget; then
  install_pkg_if_missing wget-ssl
fi
install_adguardvpn_cli

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
DEFAULT_CONFIG_PATH="${TMP_DIR}/config.default.json"
cp "${APP_DIR}/config.json" "$DEFAULT_CONFIG_PATH"

CONFIG_RESTORE_STATUS="fresh"
if [ -n "$BACKUP_CONFIG" ] && [ -f "$BACKUP_CONFIG" ]; then
  if BACKUP_CONFIG="$BACKUP_CONFIG" /opt/bin/python3 - <<'PY'
import json
import os
from pathlib import Path

backup_path = Path(os.environ["BACKUP_CONFIG"])
text = backup_path.read_text(encoding="utf-8")
decoder = json.JSONDecoder()

try:
    json.loads(text)
except json.JSONDecodeError as exc:
    try:
        payload, end = decoder.raw_decode(text.lstrip())
    except json.JSONDecodeError:
        raise SystemExit(1) from exc
    if not isinstance(payload, dict):
        raise SystemExit(1)
PY
  then
    cp "$BACKUP_CONFIG" "${APP_DIR}/config.json"
    CONFIG_RESTORE_STATUS="backup-valid"
  else
    BROKEN_CONFIG_COPY="${APP_DIR}/config.invalid.backup"
    cp "$BACKUP_CONFIG" "$BROKEN_CONFIG_COPY"
    echo "Warning: existing config.json is malformed, trying to recover valid data"
    echo "Broken backup saved to ${BROKEN_CONFIG_COPY}"
    CONFIG_RESTORE_STATUS="invalid-backup"
  fi
fi

mkdir -p "${APP_DIR}/deploy/entware"
mkdir -p "/opt/etc/init.d"

if [ ! -f "${APP_DIR}/config.json" ] || [ ! -f "$DEFAULT_CONFIG_PATH" ]; then
  echo "config.json not found after extracting the project"
  exit 1
fi

APP_DIR="$APP_DIR" DEFAULT_CONFIG_PATH="$DEFAULT_CONFIG_PATH" CONFIG_RESTORE_STATUS="$CONFIG_RESTORE_STATUS" /opt/bin/python3 - <<'PY'
import json
import os
import shutil
import socket
from pathlib import Path

app_dir = Path(os.environ["APP_DIR"])
config_path = app_dir / "config.json"
default_config_path = Path(os.environ["DEFAULT_CONFIG_PATH"])
restore_status = os.environ["CONFIG_RESTORE_STATUS"]
config_text = config_path.read_text(encoding="utf-8")
decoder = json.JSONDecoder()

def merge_defaults(base, override):
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = merge_defaults(merged.get(key), value)
        return merged
    return override if override is not None else base

def load_first_object(text):
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload, _ = decoder.raw_decode(text.lstrip())
    if not isinstance(payload, dict):
        raise SystemExit("config.json root must be an object")
    return payload

default_config = load_first_object(default_config_path.read_text(encoding="utf-8"))
current_config = load_first_object(config_text)
config = merge_defaults(default_config, current_config)

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

def choose_port(host: str, current: int, preserve_current: bool) -> int:
    if preserve_current and current > 0 and current != 8088:
        return current

    preferred = [current, 18090, 18091, 18092, 18093, 8090]
    seen: set[int] = set()
    for port in preferred:
        if port in seen or port <= 0:
            continue
        seen.add(port)
        if port != 8088 and port_is_free(host, port):
            return port

    for port in range(18100, 18121):
        if port in seen:
            continue
        if port_is_free(host, port):
            return port

    raise SystemExit("Could not find a free TCP port for the panel")

def detect_dnsmasq_conf_path() -> str:
    candidate_config_files = [
        Path("/opt/etc/dnsmasq.conf"),
        Path("/etc/dnsmasq.conf"),
    ]
    candidate_dirs = [
        Path("/opt/etc/dnsmasq.d"),
        Path("/opt/etc/dnsmasq.conf.d"),
        Path("/etc/dnsmasq.d"),
    ]

    for config_file in candidate_config_files:
        if not config_file.exists():
            continue
        try:
            for line in config_file.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("conf-dir="):
                    directory = stripped.split("=", 1)[1].split(",", 1)[0].strip()
                    if directory:
                        path = Path(directory)
                        path.mkdir(parents=True, exist_ok=True)
                        return str(path / "keenetic-vpn-panel-ipset.conf")
        except OSError:
            continue

    for directory in candidate_dirs:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            return str(directory / "keenetic-vpn-panel-ipset.conf")
        except OSError:
            continue
    return str(app_dir / "generated" / "dnsmasq-ipset-kvpn.conf")

def detect_dnsmasq_restart_command() -> str:
    candidates = [
        "/opt/etc/init.d/S56dnsmasq restart",
        "/opt/etc/init.d/S50dnsmasq restart",
        "/etc/init.d/dnsmasq restart",
        "service dnsmasq restart",
    ]
    for candidate in candidates:
        executable = candidate.split(" ", 1)[0]
        if os.path.isabs(executable) and Path(executable).exists():
            return candidate
        if not os.path.isabs(executable) and shutil.which(executable):
            return candidate
    return ""

panel = config.setdefault("panel", {})
current_host = str(panel.get("host", "")).strip()
if current_host in {"", "127.0.0.1", "localhost"}:
    panel["host"] = "0.0.0.0"

current_port = int(panel.get("port", 18090))
panel["port"] = choose_port("0.0.0.0", current_port, restore_status != "fresh")

autostart = config.setdefault("autostart", {})
autostart["enabled"] = bool(autostart.get("enabled", True))
autostart["app_dir"] = str(app_dir)
autostart["python_bin"] = "/opt/bin/python3"
autostart["log_file"] = "/opt/var/log/keenetic-vpn-panel.log"
autostart["pid_file"] = "/opt/var/run/keenetic-vpn-panel.pid"
autostart["start_script_path"] = str(app_dir / "deploy" / "entware" / "start_vpn_panel.sh")
autostart["init_script_path"] = "/opt/etc/init.d/S99keenetic-vpn-panel"

transparent_proxy = config.setdefault("transparent_proxy", {})
current_mode = str(transparent_proxy.get("mode", "")).strip().lower()
if current_mode in {"", "router-only"}:
    transparent_proxy["mode"] = "tun-policy"
transparent_proxy["dnsmasq_ipset_config_path"] = detect_dnsmasq_conf_path()
transparent_proxy["dnsmasq_restart_command"] = transparent_proxy.get("dnsmasq_restart_command") or detect_dnsmasq_restart_command()
transparent_proxy["ip_path"] = transparent_proxy.get("ip_path") or "/opt/sbin/ip"
transparent_proxy["ipset_path"] = transparent_proxy.get("ipset_path") or "/opt/sbin/ipset"
transparent_proxy["iptables_path"] = transparent_proxy.get("iptables_path") or "/opt/sbin/iptables"
transparent_proxy["dns_hijack_enabled"] = bool(transparent_proxy.get("dns_hijack_enabled", True))
transparent_proxy["tun_interface"] = str(transparent_proxy.get("tun_interface", "auto") or "auto")

config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
PY

HOME="$ADGUARDVPN_HOME" adguardvpn-cli config set-mode TUN >/dev/null 2>&1 || true
HOME="$ADGUARDVPN_HOME" adguardvpn-cli config set-tun-routing-mode NONE >/dev/null 2>&1 || true

cat > "${APP_DIR}/deploy/entware/start_vpn_panel.sh" <<EOF
#!/opt/bin/sh

export SSL_CERT_FILE=/opt/etc/ssl/certs/ca-certificates.crt
export HOME=/opt/home/admin
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
LOG_FILE="/opt/var/log/keenetic-vpn-panel.log"

start() {
  if [ -f "\$PID_FILE" ] && kill -0 "\$(cat "\$PID_FILE")" 2>/dev/null; then
    echo "\$NAME already running"
    return 0
  fi

  mkdir -p /opt/var/run
  "\$START_SCRIPT" &
  PID=\$!
  echo "\$PID" > "\$PID_FILE"
  sleep 2
  if [ -n "\$PID" ] && kill -0 "\$PID" 2>/dev/null; then
    echo "\$NAME started"
    return 0
  fi

  echo "\$NAME failed to start"
  rm -f "\$PID_FILE"
  if [ -f "\$LOG_FILE" ]; then
    tail -n 40 "\$LOG_FILE"
  fi
  return 1
}

stop_wait() {
  PID="\$1"
  COUNT=0
  while [ "\$COUNT" -lt 10 ]; do
    if [ -z "\$PID" ] || ! kill -0 "\$PID" 2>/dev/null; then
      return 0
    fi
    sleep 1
    COUNT=\$((COUNT + 1))
  done
  return 1
}

stop() {
  if [ ! -f "\$PID_FILE" ]; then
    echo "\$NAME is not running"
    return 0
  fi

  PID="\$(cat "\$PID_FILE" 2>/dev/null)"
  if [ -n "\$PID" ] && kill -0 "\$PID" 2>/dev/null; then
    kill "\$PID"
    if ! stop_wait "\$PID"; then
      echo "\$NAME did not stop in time"
      return 1
    fi
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
sleep 2
if ! "$INIT_SCRIPT_PATH" status; then
  echo "Service failed to stay running. Recent log:"
  tail -n 60 "/opt/var/log/keenetic-vpn-panel.log" 2>/dev/null || true
  exit 1
fi

PANEL_PORT="$(sed -n 's/.*"port":[[:space:]]*\([0-9][0-9]*\).*/\1/p' "${APP_DIR}/config.json" | head -n 1)"
if [ -z "$PANEL_PORT" ]; then
  PANEL_PORT="18090"
fi
PANEL_HOST="$(detect_lan_ip)"

echo ""
echo "Installation completed."
if [ "$CONFIG_RESTORE_STATUS" = "backup-valid" ]; then
  echo "Config note: previous config restored and merged with the new version."
fi
if [ "$CONFIG_RESTORE_STATUS" = "invalid-backup" ]; then
  echo "Config note: malformed previous config was recovered as much as possible; review ${APP_DIR}/config.invalid.backup if needed."
fi
echo "Open the panel from your local network:"
echo "http://${PANEL_HOST}:${PANEL_PORT}"
echo ""
echo "Service status:"
echo "${INIT_SCRIPT_PATH} status"
