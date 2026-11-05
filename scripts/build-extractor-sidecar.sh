#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_TRIPLE="${1:-$(rustc -vV | awk '/host:/ { print $2 }')}"

cd "$ROOT_DIR/backend"
python3 -m pip install -r requirements-build.txt
python3 -m PyInstaller --clean recreation-extractor.spec

mkdir -p "$ROOT_DIR/src-tauri/binaries"
cp "dist/recreation-extractor" "$ROOT_DIR/src-tauri/binaries/recreation-extractor-$TARGET_TRIPLE"
chmod +x "$ROOT_DIR/src-tauri/binaries/recreation-extractor-$TARGET_TRIPLE"

echo "Built src-tauri/binaries/recreation-extractor-$TARGET_TRIPLE"
