#!/usr/bin/env bash
# Install croc into ~/.local/bin. Tries the official installer first,
# then a GitHub release download, then `go install` if Go is available.
set -euo pipefail

BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$BIN_DIR"

if command -v croc >/dev/null 2>&1; then
  echo "croc already installed: $(croc --version)"
  exit 0
fi

echo "Trying the official installer..."
if curl -fsSL https://getcroc.schollz.com | bash -s -- -p "$BIN_DIR" 2>/dev/null; then
  "$BIN_DIR/croc" --version && exit 0
fi

echo "Trying a GitHub release download..."
TAG=$(curl -fsSLI -o /dev/null -w '%{url_effective}' https://github.com/schollz/croc/releases/latest 2>/dev/null | sed 's|.*/tag/||') || TAG=""
if [ -n "$TAG" ] && [ "$TAG" != "https://github.com/schollz/croc/releases/latest" ]; then
  ARCH=$(uname -m); OS=$(uname -s)
  case "$OS-$ARCH" in
    Linux-x86_64)  ASSET="croc_${TAG}_Linux-64bit.tar.gz" ;;
    Linux-aarch64) ASSET="croc_${TAG}_Linux-ARM64.tar.gz" ;;
    Darwin-x86_64) ASSET="croc_${TAG}_macOS-64bit.tar.gz" ;;
    Darwin-arm64)  ASSET="croc_${TAG}_macOS-ARM64.tar.gz" ;;
    *) ASSET="" ;;
  esac
  if [ -n "$ASSET" ]; then
    TMP=$(mktemp -d)
    if curl -fsSL -o "$TMP/croc.tar.gz" "https://github.com/schollz/croc/releases/download/${TAG}/${ASSET}"; then
      tar -C "$TMP" -xzf "$TMP/croc.tar.gz" croc
      mv "$TMP/croc" "$BIN_DIR/croc" && chmod +x "$BIN_DIR/croc"
      rm -rf "$TMP"
      "$BIN_DIR/croc" --version && exit 0
    fi
    rm -rf "$TMP"
  fi
fi

if command -v go >/dev/null 2>&1; then
  echo "Building croc from source with Go..."
  GOBIN="$BIN_DIR" GOFLAGS=-mod=mod go install github.com/schollz/croc/v10@latest
  "$BIN_DIR/croc" --version && exit 0
fi

echo "Could not install croc automatically. See https://github.com/schollz/croc#install" >&2
exit 1
