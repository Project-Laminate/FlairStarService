#!/usr/bin/env bash
set -Eeo pipefail

# Create temporary directory
TEMP_DIR="/tmp/flair_star_work"
mkdir -p "$TEMP_DIR"

echo "-- Starting FLAIR STAR module..."
python3 /app/src/main.py \
    --input-dir "$MERCURE_IN_DIR" \
    --output-dir "$MERCURE_OUT_DIR" \
    --temp-dir "$TEMP_DIR"

# Clean up temp directory
rm -rf "$TEMP_DIR"

echo "-- Done."