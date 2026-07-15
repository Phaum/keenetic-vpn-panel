#!/opt/bin/sh

set -eu

URL="${INSTALLER_URL:-https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/go-version/go/install/install.sh}"
CONNECT_TIMEOUT="${CONNECT_TIMEOUT:-20}"
TRANSFER_TIMEOUT="${TRANSFER_TIMEOUT:-180}"
DOWNLOAD_RETRIES="${DOWNLOAD_RETRIES:-2}"
CURL_IP_FAMILY="${CURL_IP_FAMILY--4}"
UPDATE_SCRIPT="${TMPDIR:-/opt/tmp}/keenetic-vpn-panel-update.$$"

cleanup() { rm -f "$UPDATE_SCRIPT"; }
trap cleanup EXIT INT TERM
mkdir -p "$(dirname "$UPDATE_SCRIPT")"

echo "[1/2] Загрузка установщика Go-версии: $URL"
if command -v curl >/dev/null 2>&1; then
  curl $CURL_IP_FAMILY --fail --location --show-error --silent \
    --connect-timeout "$CONNECT_TIMEOUT" --max-time "$TRANSFER_TIMEOUT" \
    --retry "$DOWNLOAD_RETRIES" --retry-delay 2 \
    --output "$UPDATE_SCRIPT" "$URL"
elif command -v wget >/dev/null 2>&1; then
  wget -T "$CONNECT_TIMEOUT" -t "$((DOWNLOAD_RETRIES + 1))" -O "$UPDATE_SCRIPT" "$URL"
else
  echo "Ошибка: для обновления требуется curl или wget." >&2
  exit 1
fi

[ -s "$UPDATE_SCRIPT" ] || { echo "Ошибка: загружен пустой установщик." >&2; exit 1; }
echo "[2/2] Запуск установщика. Текущая конфигурация будет сохранена."
/bin/sh "$UPDATE_SCRIPT"
