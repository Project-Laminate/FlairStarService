#!/usr/bin/env bash
set -Eeo pipefail

# Create temporary directory
TEMP_DIR="/tmp/flair_star_work"
mkdir -p "$TEMP_DIR"

echo "-- Starting FLAIR STAR module..."

# Build command with basic parameters
CMD="python3 /app/src/main.py \
    --input-dir \"$MERCURE_IN_DIR\" \
    --output-dir \"$MERCURE_OUT_DIR\" \
    --temp-dir \"$TEMP_DIR\""

# Add pattern options if they're provided as environment variables
if [ ! -z "$SWI_PATTERN" ] && [ ! -z "$FLAIR_PATTERN" ]; then
    echo "-- Using provided pattern matching: SWI=\"$SWI_PATTERN\", FLAIR=\"$FLAIR_PATTERN\""
    CMD="$CMD --swi-pattern \"$SWI_PATTERN\" --flair-pattern \"$FLAIR_PATTERN\""
fi

# Execute the command
eval $CMD

# Clean up temp directory
rm -rf "$TEMP_DIR"

echo "-- Done."