#!/opt/bin/sh

set -eu

if command -v curl >/dev/null 2>&1; then
  exec /bin/sh -c "$(curl -fsSL https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/main/install/install.sh)"
fi

if command -v wget >/dev/null 2>&1; then
  exec /bin/sh -c "$(wget -O- https://raw.githubusercontent.com/Phaum/keenetic-vpn-panel/main/install/install.sh)"
fi

echo "Neither curl nor wget found"
exit 1
