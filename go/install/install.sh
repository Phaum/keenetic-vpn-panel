#!/opt/bin/sh

set -eu

REPO_OWNER="${REPO_OWNER:-Phaum}"
REPO_NAME="${REPO_NAME:-keenetic-vpn-panel}"
BRANCH="${BRANCH:-master}"
APP_ROOT="${APP_ROOT:-/opt/share/keenetic-vpn-panel}"
APP_DIR="${APP_DIR:-${APP_ROOT}/go}"
OLD_APP_DIR="${OLD_APP_DIR:-${APP_ROOT}/python}"
INIT_SCRIPT="${INIT_SCRIPT:-/opt/etc/init.d/S99keenetic-vpn-panel}"
LOG_FILE="${LOG_FILE:-/opt/var/log/keenetic-vpn-panel.log}"
PID_FILE="${PID_FILE:-/opt/var/run/keenetic-vpn-panel.pid}"
SHELL_BIN="${SHELL_BIN:-/opt/bin/sh}"
TMP_DIR="${TMPDIR:-/opt/tmp}/${REPO_NAME}-go-install.$$"
BACKUP_ROOT="${BACKUP_ROOT:-${APP_ROOT}/migration-backups}"
SOURCE_URL="${SOURCE_URL:-https://codeload.github.com/${REPO_OWNER}/${REPO_NAME}/tar.gz/refs/heads/${BRANCH}}"
RELEASE_BASE="${RELEASE_BASE:-https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/latest/download}"

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT INT TERM

need_cmd() { command -v "$1" >/dev/null 2>&1; }
install_pkg_if_available() {
  PKG="$1"
  opkg list-installed 2>/dev/null | grep -q "^${PKG} " && return 0
  opkg info "$PKG" >/dev/null 2>&1 && opkg install "$PKG" || true
}
download() {
  URL="$1"; DEST="$2"
  if need_cmd curl; then curl -fsSL "$URL" -o "$DEST"
  elif need_cmd wget; then wget -O "$DEST" "$URL"
  else echo "Ошибка: для загрузки требуется curl или wget." >&2; exit 1
  fi
}

if [ ! -d /opt ] || ! need_cmd opkg; then
  echo "Ошибка: Entware (/opt и opkg) не найден." >&2
  exit 1
fi
[ "$APP_DIR" != "$OLD_APP_DIR" ] || { echo "Ошибка: APP_DIR и OLD_APP_DIR не должны совпадать." >&2; exit 1; }

opkg update
install_pkg_if_available ca-certificates
if ! need_cmd curl && ! need_cmd wget; then install_pkg_if_available wget-ssl; fi
install_pkg_if_available ip-full
install_pkg_if_available ipset
install_pkg_if_available redsocks

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ASSET_ARCH="amd64" ;;
  aarch64|arm64) ASSET_ARCH="arm64" ;;
  armv7|armv7l|armv8l) ASSET_ARCH="armv7" ;;
  mipsel|mipsle) ASSET_ARCH="mipsle" ;;
  mips)
    if printf 'I' | hexdump -o 2>/dev/null | awk 'NR == 1 { exit substr($2, 6, 1) == "1" ? 0 : 1 }'; then ASSET_ARCH="mipsle"; else ASSET_ARCH="mips"; fi
    ;;
  *) echo "Ошибка: архитектура ${ARCH} не поддерживается." >&2; exit 1 ;;
esac

mkdir -p "$TMP_DIR" "$APP_ROOT" "$BACKUP_ROOT" "$(dirname "$INIT_SCRIPT")" "$(dirname "$LOG_FILE")" "$(dirname "$PID_FILE")"

SOURCE_ARCHIVE="${TMP_DIR}/source.tar.gz"
download "$SOURCE_URL" "$SOURCE_ARCHIVE"
tar -tzf "$SOURCE_ARCHIVE" >/dev/null 2>&1 || { echo "Ошибка: архив проекта повреждён." >&2; exit 1; }
SOURCE_ROOT="$(tar -tzf "$SOURCE_ARCHIVE" | head -n 1 | cut -d/ -f1)"
tar -xzf "$SOURCE_ARCHIVE" -C "$TMP_DIR"
EXTRACTED="${TMP_DIR}/${SOURCE_ROOT}"
[ -d "${EXTRACTED}/go" ] || { echo "Ошибка: каталог go отсутствует в архиве." >&2; exit 1; }

BINARY_ASSET="keenetic-vpn-panel-linux-${ASSET_ARCH}"
BINARY="${TMP_DIR}/${BINARY_ASSET}"
if [ -n "${LOCAL_BINARY:-}" ]; then
  cp "$LOCAL_BINARY" "$BINARY"
else
  download "${RELEASE_BASE}/${BINARY_ASSET}" "$BINARY"
  download "${RELEASE_BASE}/${BINARY_ASSET}.sha256" "${BINARY}.sha256"
  need_cmd sha256sum || { echo "Ошибка: требуется sha256sum." >&2; exit 1; }
  EXPECTED="$(awk 'NR == 1 {print $1}' "${BINARY}.sha256")"
  echo "${EXPECTED}  ${BINARY}" | sha256sum -c -
fi
chmod 0755 "$BINARY"

STAMP="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo now)"
ROLLBACK="${TMP_DIR}/rollback"
mkdir -p "$ROLLBACK"
[ ! -d "$APP_DIR" ] || cp -R "$APP_DIR" "${ROLLBACK}/go"
[ ! -f "$INIT_SCRIPT" ] || cp "$INIT_SCRIPT" "${ROLLBACK}/init-script"
[ ! -d "${APP_ROOT}/web" ] || cp -R "${APP_ROOT}/web" "${ROLLBACK}/web"
[ ! -d "${APP_ROOT}/assets" ] || cp -R "${APP_ROOT}/assets" "${ROLLBACK}/assets"

CONFIG_SOURCE=""
INSTALL_KIND="fresh"
if [ -f "${APP_DIR}/config.json" ]; then
  CONFIG_SOURCE="${TMP_DIR}/config.current.json"
  cp "${APP_DIR}/config.json" "$CONFIG_SOURCE"
  INSTALL_KIND="go-update"
elif [ -f "${OLD_APP_DIR}/config.json" ]; then
  CONFIG_SOURCE="${TMP_DIR}/config.python.json"
  cp "${OLD_APP_DIR}/config.json" "$CONFIG_SOURCE"
  INSTALL_KIND="python-migration"
elif [ -f "${APP_ROOT}/vpn_panel_server.py" ] && [ -f "${APP_ROOT}/config.json" ]; then
  CONFIG_SOURCE="${TMP_DIR}/config.legacy-root.json"
  cp "${APP_ROOT}/config.json" "$CONFIG_SOURCE"
  INSTALL_KIND="legacy-root-migration"
fi

if [ -x "$INIT_SCRIPT" ]; then "$INIT_SCRIPT" stop || true; fi

rollback() {
  echo "Установка не завершена, выполняется откат." >&2
  [ ! -x "$INIT_SCRIPT" ] || "$INIT_SCRIPT" stop || true
  rm -rf "$APP_DIR"
  if [ -d "${ROLLBACK}/go" ]; then mv "${ROLLBACK}/go" "$APP_DIR"; fi
  if [ -f "${ROLLBACK}/init-script" ]; then cp "${ROLLBACK}/init-script" "$INIT_SCRIPT"; chmod 0755 "$INIT_SCRIPT"; "$INIT_SCRIPT" start || true
  else rm -f "$INIT_SCRIPT"
  fi
  rm -rf "${APP_ROOT}/web" "${APP_ROOT}/assets"
  [ ! -d "${ROLLBACK}/web" ] || mv "${ROLLBACK}/web" "${APP_ROOT}/web"
  [ ! -d "${ROLLBACK}/assets" ] || mv "${ROLLBACK}/assets" "${APP_ROOT}/assets"
  exit 1
}

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR" "${APP_DIR}/deploy/entware"
cp -R "${EXTRACTED}/go/." "$APP_DIR/" || rollback
cp "$BINARY" "${APP_DIR}/keenetic-vpn-panel" || rollback
chmod 0755 "${APP_DIR}/keenetic-vpn-panel"
rm -rf "${APP_ROOT}/web" "${APP_ROOT}/assets"
cp -R "${EXTRACTED}/web" "${APP_ROOT}/web" || rollback
cp -R "${EXTRACTED}/assets" "${APP_ROOT}/assets" || rollback

if [ -n "$CONFIG_SOURCE" ]; then
  mkdir -p "$BACKUP_ROOT"
  cp "$CONFIG_SOURCE" "${BACKUP_ROOT}/config.${INSTALL_KIND}.${STAMP}.json"
  (cd "$APP_DIR" && ./keenetic-vpn-panel migrate-config "$CONFIG_SOURCE" >/dev/null) || rollback
fi

cat > "${APP_DIR}/deploy/entware/start_vpn_panel.sh" <<EOF
#!${SHELL_BIN}
export SSL_CERT_FILE=/opt/etc/ssl/certs/ca-certificates.crt
export HOME=/opt/home/admin
PATH=/opt/bin:/opt/sbin:/usr/sbin:/usr/bin:/sbin:/bin
cd ${APP_DIR} || exit 1
exec ${APP_DIR}/keenetic-vpn-panel >> ${LOG_FILE} 2>&1
EOF

cat > "$INIT_SCRIPT" <<EOF
#!${SHELL_BIN}
PID_FILE=${PID_FILE}
APP=${APP_DIR}/deploy/entware/start_vpn_panel.sh
start() { [ -f "\$PID_FILE" ] && kill -0 "\$(cat "\$PID_FILE")" 2>/dev/null && return 0; mkdir -p "\$(dirname "\$PID_FILE")"; "\$APP" & echo \$! > "\$PID_FILE"; }
stop() { [ -f "\$PID_FILE" ] || return 0; PID="\$(cat "\$PID_FILE")"; kill "\$PID" 2>/dev/null || true; N=0; while kill -0 "\$PID" 2>/dev/null && [ "\$N" -lt 10 ]; do sleep 1; N=\$((N+1)); done; rm -f "\$PID_FILE"; }
case "\${1:-}" in start) start;; stop) stop;; restart) stop; start;; status) [ -f "\$PID_FILE" ] && kill -0 "\$(cat "\$PID_FILE")" 2>/dev/null;; *) echo "Usage: \$0 {start|stop|restart|status}"; exit 1;; esac
EOF
chmod 0755 "${APP_DIR}/deploy/entware/start_vpn_panel.sh" "$INIT_SCRIPT"

"$INIT_SCRIPT" start || rollback
sleep 2
"$INIT_SCRIPT" status || rollback

PANEL_PORT="$(sed -n 's/.*"port"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "${APP_DIR}/config.json" | head -n 1)"
PANEL_PORT="${PANEL_PORT:-8088}"
HEALTH_URL="http://127.0.0.1:${PANEL_PORT}/api/state"
HEALTH_OK=0
N=0
while [ "$N" -lt 10 ]; do
  if need_cmd curl && curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then HEALTH_OK=1; break; fi
  if ! need_cmd curl && need_cmd wget && wget -q -O /dev/null "$HEALTH_URL"; then HEALTH_OK=1; break; fi
  N=$((N+1)); sleep 1
done
[ "$HEALTH_OK" -eq 1 ] || rollback

if [ "$INSTALL_KIND" = "python-migration" ]; then rm -rf "$OLD_APP_DIR"; fi
if [ "$INSTALL_KIND" = "legacy-root-migration" ]; then
  rm -rf "${APP_ROOT}/vpn_panel_server.py" "${APP_ROOT}/templates" "${APP_ROOT}/tools" "${APP_ROOT}/install" "${APP_ROOT}/deploy"
  rm -f "${APP_ROOT}/config.json" "${APP_ROOT}/sctipt_test_location.txt"
fi

echo "Keenetic VPN Panel Go установлена: ${APP_DIR}"
echo "Тип установки: ${INSTALL_KIND}"
echo "Панель: http://ROUTER_IP:${PANEL_PORT}"
if [ -n "$CONFIG_SOURCE" ]; then echo "Резервная копия конфигурации: ${BACKUP_ROOT}/config.${INSTALL_KIND}.${STAMP}.json"; fi
