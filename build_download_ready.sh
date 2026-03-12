#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/download-ready"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

# Copy runnable MVP files as plain source (no diff markers)
cp "$ROOT_DIR/README.md" "$OUT_DIR/README.md"
cp "$ROOT_DIR/package.json" "$OUT_DIR/package.json"
cp -R "$ROOT_DIR/app" "$OUT_DIR/app"
cp -R "$ROOT_DIR/tests" "$OUT_DIR/tests"
cp -R "$ROOT_DIR/docs" "$OUT_DIR/docs"
cp -R "$ROOT_DIR/miniapp" "$OUT_DIR/miniapp"

# Clean python cache if present
find "$OUT_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} + || true

# Build zip for one-click download
(
  cd "$ROOT_DIR"
  rm -f tourist-card-mvp-download-ready.zip
  zip -rq tourist-card-mvp-download-ready.zip download-ready
)

echo "Built: $OUT_DIR"
echo "Built: $ROOT_DIR/tourist-card-mvp-download-ready.zip"

# Build a miniapp-only zip to import directly in WeChat DevTools
(
  cd "$ROOT_DIR/miniapp"
  rm -f "$ROOT_DIR/miniapp-import-ready.zip"
  zip -rq "$ROOT_DIR/miniapp-import-ready.zip" .
)

echo "Built: $ROOT_DIR/miniapp-import-ready.zip"
