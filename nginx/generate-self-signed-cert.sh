#!/usr/bin/env sh
# Generates a self-signed TLS cert for internal deployments with no domain
# name yet. Not committed to git (see nginx/certs/ in .gitignore) — every
# operator/environment generates their own key pair.
#
# Usage:
#   ./nginx/generate-self-signed-cert.sh [days] [extra-SAN-ip-or-dns ...]
#
# Example (server reachable at 10.0.5.12 as well as localhost):
#   ./nginx/generate-self-signed-cert.sh 825 IP:10.0.5.12
#
# Re-run any time to rotate/regenerate; this overwrites the existing files.

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CERT_DIR="$SCRIPT_DIR/certs"
DAYS="${1:-825}"   # 825 days = current max lifetime most browsers accept for a leaf cert
[ "$#" -ge 1 ] && shift   # only shift if a $1 was actually given

mkdir -p "$CERT_DIR"

# Base SANs: localhost + common loopback. Extra SANs (e.g. IP:10.0.5.12,
# DNS:ims.internal) can be passed as additional args and are appended.
SAN="DNS:localhost,IP:127.0.0.1"
for extra in "$@"; do
    SAN="$SAN,$extra"
done

echo "Generating self-signed cert (valid $DAYS days) with SAN: $SAN"

openssl req -x509 -nodes \
    -newkey rsa:2048 \
    -keyout "$CERT_DIR/privkey.pem" \
    -out "$CERT_DIR/fullchain.pem" \
    -days "$DAYS" \
    -subj "/CN=localhost" \
    -addext "subjectAltName=$SAN"

chmod 600 "$CERT_DIR/privkey.pem"
chmod 644 "$CERT_DIR/fullchain.pem"

echo "Done:"
echo "  $CERT_DIR/fullchain.pem"
echo "  $CERT_DIR/privkey.pem"
echo
echo "NOTE: browsers/clients will show an untrusted-certificate warning for"
echo "self-signed certs. Once a real domain + CA-issued cert (e.g. Let's"
echo "Encrypt) is available, swap these two files for the real ones — no"
echo "nginx.conf changes needed, paths stay the same."