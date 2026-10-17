#!/bin/sh
# Empaqueta extension/ en public/coto-sdr-extension.zip (lo descarga el panel desde Ajustes).
set -e
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
cp -r extension "$tmp/coto-sdr-extension"
rm -f public/coto-sdr-extension.zip
(cd "$tmp" && zip -q -X -r - coto-sdr-extension) > public/coto-sdr-extension.zip
rm -rf "$tmp"
echo "public/coto-sdr-extension.zip"
