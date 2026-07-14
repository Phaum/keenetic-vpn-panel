#!/opt/bin/sh

set -eu
URL="${INSTALLER_URL:-https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/go-version/go/install/install.sh}"
if command -v curl >/dev/null 2>&1; then exec /bin/sh -c "$(curl -fsSL "$URL")"; fi
if command -v wget >/dev/null 2>&1; then exec /bin/sh -c "$(wget -O- "$URL")"; fi
echo "Ошибка: для обновления требуется curl или wget." >&2
exit 1
