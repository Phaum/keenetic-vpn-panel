#!/opt/bin/sh

set -eu

VERSION="1.7.12"
TAG="v${VERSION}-release"
BASE_URL="https://github.com/AdguardTeam/AdGuardVPNCLI/releases/download/${TAG}"
INSTALL_DIR="${INSTALL_DIR:-/opt/adguardvpn_cli}"
LINK_PATH="${LINK_PATH:-/opt/bin/adguardvpn-cli}"
TMP_DIR="${TMPDIR:-/opt/tmp}/adguardvpn-cli-install.$$"

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT INT TERM

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ASSET_ARCH="x86_64"; SHA256="a706933c87ec88eec8578cce96d2b91c385e083cf738a806e69b3bcd877fb88c" ;;
  aarch64|arm64) ASSET_ARCH="aarch64"; SHA256="872fcd81ec41f952001c567abd2e61564773ccdcf5be246afd047f3d3eb4ee0b" ;;
  armv7|armv7l|armv8l) ASSET_ARCH="armv7"; SHA256="79acdf47fbb408159c813ac03a7fe0f0e1ef22ec2cc157f2e1b206f4893a8ba1" ;;
  mipsel|mipsle) ASSET_ARCH="mipsel"; SHA256="b31cea759728fe5fa8dd9c1487a2679424370a1be6804632df77896ee19e4efe" ;;
  mips)
    if printf 'I' | hexdump -o | awk 'NR == 1 { exit substr($2, 6, 1) == "1" ? 0 : 1 }'; then
      ASSET_ARCH="mipsel"; SHA256="b31cea759728fe5fa8dd9c1487a2679424370a1be6804632df77896ee19e4efe"
    else
      ASSET_ARCH="mips"; SHA256="afcd4b122614be71baf649b02b0142a74d18a5f2abb38372269840bc852ecf0a"
    fi
    ;;
  *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
esac

ARCHIVE="adguardvpn-cli-${VERSION}-linux-${ASSET_ARCH}.tar.gz"
URL="${BASE_URL}/${ARCHIVE}"
mkdir -p "$TMP_DIR"

if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$URL" -o "${TMP_DIR}/${ARCHIVE}"
elif command -v wget >/dev/null 2>&1; then
  wget -O "${TMP_DIR}/${ARCHIVE}" "$URL"
else
  echo "curl or wget is required for the one-time download" >&2
  exit 1
fi

if ! command -v sha256sum >/dev/null 2>&1; then
  echo "sha256sum is required to verify the official archive" >&2
  exit 1
fi
echo "${SHA256}  ${TMP_DIR}/${ARCHIVE}" | sha256sum -c -

tar -xzf "${TMP_DIR}/${ARCHIVE}" -C "$TMP_DIR"
BIN_PATH="$(find "$TMP_DIR" -type f -name adguardvpn-cli | head -n 1)"
if [ -z "$BIN_PATH" ] || [ ! -f "$BIN_PATH" ]; then
  echo "adguardvpn-cli was not found in the verified archive" >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR" "$(dirname "$LINK_PATH")"
cp "$BIN_PATH" "${INSTALL_DIR}/adguardvpn-cli"
chmod 0755 "${INSTALL_DIR}/adguardvpn-cli"
ln -sf "${INSTALL_DIR}/adguardvpn-cli" "$LINK_PATH"

echo "AdGuard VPN CLI ${VERSION} installed: ${LINK_PATH}"
