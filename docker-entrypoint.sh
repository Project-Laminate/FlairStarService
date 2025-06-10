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
export TASK_JSON="${TASK_JSON:-}"

# Display COPY_ALL setting
if [ "${COPY_ALL,,}" = "true" ] || [ "${COPY_ALL,,}" = "yes" ] || [ "${COPY_ALL,,}" = "1" ]; then
    echo "-- COPY_ALL flag is set to TRUE. All input DICOM files will be copied to output."
else
    echo "-- COPY_ALL flag is set to FALSE. Only processed files will be in output."
fi

# Display configuration sources
echo "-- Configuration sources available:"
[ ! -z "$TASK_JSON" ] && echo "   ✓ TASK_JSON (${#TASK_JSON} chars)"
[ ! -z "$SWI_UID" ] && [ ! -z "$FLAIR_UID" ] && echo "   ✓ SeriesInstanceUIDs"
[ ! -z "$SWI_PATTERN" ] && [ ! -z "$FLAIR_PATTERN" ] && echo "   ✓ Pattern matching"
echo "   ✓ COPY_ALL environment variable override"

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

# Configuration priority order:
# 1. TASK_JSON (complete JSON configuration)
# 2. UID-based matching
# 3. Pattern-based matching
# 4. Fall back to task.json file or environment variables in main.py

if [ ! -z "$TASK_JSON" ]; then
    echo "-- Using TASK_JSON environment variable for complete configuration"
    echo "-- TASK_JSON length: ${#TASK_JSON} characters"
    # No need to add command line arguments - main.py will use TASK_JSON
elif [ ! -z "$SWI_UID" ] && [ ! -z "$FLAIR_UID" ]; then
    echo "-- Using provided SeriesInstanceUIDs: SWI=\"$SWI_UID\", FLAIR=\"$FLAIR_UID\""
    CMD="$CMD --swi-uid \"$SWI_UID\" --flair-uid \"$FLAIR_UID\""
elif [ ! -z "$SWI_PATTERN" ] && [ ! -z "$FLAIR_PATTERN" ]; then
    echo "-- Using provided pattern matching: SWI=\"$SWI_PATTERN\", FLAIR=\"$FLAIR_PATTERN\""
    CMD="$CMD --swi-pattern \"$SWI_PATTERN\" --flair-pattern \"$FLAIR_PATTERN\""
else
    echo "-- No explicit configuration provided, will use task.json file or environment variables"
fi

# Execute the command
eval $CMD

# Clean up temp directory
rm -rf "$TEMP_DIR"

echo "-- Done."