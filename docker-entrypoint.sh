#!/usr/bin/env bash
set -Eeo pipefail

# Create temporary directory
TEMP_DIR="/tmp/flair_star_work"
mkdir -p "$TEMP_DIR"

echo "-- Starting FLAIR STAR module..."

# Export environment variables
export DATASET_PATH="${MERCURE_IN_DIR:-/input}"
export RESULTS_PATH="${MERCURE_OUT_DIR:-/output}"
export SWI_PATTERN="${SWI_PATTERN:-}"
export FLAIR_PATTERN="${FLAIR_PATTERN:-}"
export SWI_UID="${SWI_UID:-}"
export FLAIR_UID="${FLAIR_UID:-}"
export COPY_ALL="${COPY_ALL:-false}"

# Display COPY_ALL setting
if [ "${COPY_ALL,,}" = "true" ] || [ "${COPY_ALL,,}" = "yes" ] || [ "${COPY_ALL,,}" = "1" ]; then
    echo "-- COPY_ALL flag is set to TRUE. All input DICOM files will be copied to output."
else
    echo "-- COPY_ALL flag is set to FALSE. Only processed files will be in output."
fi

# Build command with basic parameters
CMD="python3 /app/src/main.py"

# Add directory parameters if they were provided as arguments
if [ ! -z "$MERCURE_IN_DIR" ]; then
    CMD="$CMD --input-dir \"$MERCURE_IN_DIR\""
fi

if [ ! -z "$MERCURE_OUT_DIR" ]; then
    CMD="$CMD --output-dir \"$MERCURE_OUT_DIR\""
fi

# Add temp directory
CMD="$CMD --temp-dir \"$TEMP_DIR\""

# Add UID options if they're provided as environment variables
if [ ! -z "$SWI_UID" ] && [ ! -z "$FLAIR_UID" ]; then
    echo "-- Using provided SeriesInstanceUIDs: SWI=\"$SWI_UID\", FLAIR=\"$FLAIR_UID\""
    CMD="$CMD --swi-uid \"$SWI_UID\" --flair-uid \"$FLAIR_UID\""
# Add pattern options if they're provided as environment variables
elif [ ! -z "$SWI_PATTERN" ] && [ ! -z "$FLAIR_PATTERN" ]; then
    echo "-- Using provided pattern matching: SWI=\"$SWI_PATTERN\", FLAIR=\"$FLAIR_PATTERN\""
    CMD="$CMD --swi-pattern \"$SWI_PATTERN\" --flair-pattern \"$FLAIR_PATTERN\""
fi

# Execute the command
eval $CMD

# Clean up temp directory
rm -rf "$TEMP_DIR"

echo "-- Done."