#!/bin/bash

DOCKER_IMAGE="amrshadid/flair-star-processor:latest"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BUILD_LOCALLY=false
SWI_PATTERN=""
FLAIR_PATTERN=""
SWI_UID=""
FLAIR_UID=""
COPY_ALL="false"

detect_os() {
    case "$(uname -s)" in
        Darwin*)
            echo "macos"
            ;;
        Linux*)
            echo "linux"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            echo "windows"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

OS_TYPE=$(detect_os)

convert_path() {
    local path="$1"
    
    if [ "$OS_TYPE" = "windows" ]; then
        path=$(echo "$path" | sed 's/\\/\//g')
        path=$(echo "$path" | sed 's/^\([A-Za-z]\):/\/\L\1/')
    fi
    
    if [[ "$path" = /* ]] || [[ "$OS_TYPE" = "windows" && "$path" =~ ^/[a-z]/ ]]; then
        echo "$path"
    else
        echo "$(pwd)/$path"
    fi
}

usage() {
    echo "Usage: $0 -i <input_dir> -o <output_dir> [-b] [--swi <pattern>] [--flair <pattern>] [--swi-uid <uid>] [--flair-uid <uid>] [--copy-all]"
    echo
    echo "Options:"
    echo "  -i, --input     Input directory containing DICOM files"
    echo "  -o, --output    Output directory for processed files"
    echo "  -b, --build     Build Docker image locally instead of pulling from Docker Hub"
    echo "  --swi           Pattern to match SWI series in SeriesDescription"
    echo "  --flair         Pattern to match FLAIR series in SeriesDescription"
    echo "  --swi-uid       SeriesInstanceUID for SWI series"
    echo "  --flair-uid     SeriesInstanceUID for FLAIR series"
    echo "  --copy-all      Copy all input DICOM files to output (default: false)"
    echo "  -h, --help      Show this help message"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--input)
            INPUT_DIR="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -b|--build)
            BUILD_LOCALLY=true
            shift
            ;;
        --swi)
            SWI_PATTERN="$2"
            shift 2
            ;;
        --flair)
            FLAIR_PATTERN="$2"
            shift 2
            ;;
        --swi-uid)
            SWI_UID="$2"
            shift 2
            ;;
        --flair-uid)
            FLAIR_UID="$2"
            shift 2
            ;;
        --copy-all)
            COPY_ALL="true"
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

if [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT_DIR" ]; then
    echo "Error: Input and output directories are required"
    usage
fi

INPUT_DIR=$(convert_path "$INPUT_DIR")
OUTPUT_DIR=$(convert_path "$OUTPUT_DIR")

check_dir() {
    local dir="$1"
    if [ "$OS_TYPE" = "windows" ]; then
        local win_path=$(echo "$dir" | sed 's/^\/\([a-z]\)\//\U\1:\//g' | sed 's/\//\\/g')
        cmd.exe /c "if not exist \"$win_path\" exit 1" >/dev/null 2>&1
    else
        [ -d "$dir" ]
    fi
}

if ! check_dir "$INPUT_DIR"; then
    echo "Error: Input directory does not exist: $INPUT_DIR"
    exit 1
fi

if [ "$OS_TYPE" = "windows" ]; then
    win_out_path=$(echo "$OUTPUT_DIR" | sed 's/^\/\([a-z]\)\//\U\1:\//g' | sed 's/\//\\/g')
    cmd.exe /c "mkdir \"$win_out_path\"" >/dev/null 2>&1
else
    mkdir -p "$OUTPUT_DIR"
fi

if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "Error: Docker daemon is not running. Please start Docker and try again."
    exit 1
fi

# Check if Docker image exists locally
if ! docker image inspect "$DOCKER_IMAGE" &> /dev/null; then
    if [ "$BUILD_LOCALLY" = true ]; then
        echo "Building Docker image locally..."
        if ! docker build -t "$DOCKER_IMAGE" "$SCRIPT_DIR"; then
            echo "Error: Failed to build Docker image"
            exit 1
        fi
        echo "Docker image built successfully"
    else
        echo "Docker image not found locally. Pulling from Docker Hub..."
        if ! docker pull "$DOCKER_IMAGE"; then
            echo "Error: Failed to pull Docker image from Docker Hub"
            echo "You can try building the image locally using the -b flag"
            exit 1
        fi
        echo "Docker image pulled successfully"
    fi
else
    echo "Using existing Docker image: $DOCKER_IMAGE"
fi

echo "Starting FLAIR-STAR processing"

DOCKER_CMD="docker run --rm"

if [ "$OS_TYPE" = "linux" ]; then
    DOCKER_CMD="$DOCKER_CMD --network host"
fi

ENV_VARS=(
    "-e MERCURE_IN_DIR=/input"
    "-e MERCURE_OUT_DIR=/output"
    "-e DATASET_PATH=/input"
    "-e RESULTS_PATH=/output"
    "-e COPY_ALL=\"$COPY_ALL\""
)

# Add UID variables if they were provided
if [ ! -z "$SWI_UID" ]; then
    ENV_VARS+=("-e SWI_UID=\"$SWI_UID\"")
    echo "Using SWI UID: $SWI_UID"
fi

if [ ! -z "$FLAIR_UID" ]; then
    ENV_VARS+=("-e FLAIR_UID=\"$FLAIR_UID\"")
    echo "Using FLAIR UID: $FLAIR_UID"
fi

# Add pattern variables if they were provided
if [ ! -z "$SWI_PATTERN" ]; then
    ENV_VARS+=("-e SWI_PATTERN=\"$SWI_PATTERN\"")
    echo "Using SWI pattern: $SWI_PATTERN"
fi

if [ ! -z "$FLAIR_PATTERN" ]; then
    ENV_VARS+=("-e FLAIR_PATTERN=\"$FLAIR_PATTERN\"")
    echo "Using FLAIR pattern: $FLAIR_PATTERN"
fi

CMD="/app/src/main.py"

$DOCKER_CMD \
    -v "$INPUT_DIR:/input:ro" \
    -v "$OUTPUT_DIR:/output" \
    ${ENV_VARS[@]} \
    "$DOCKER_IMAGE" \
    ${CMD:-}

if [ $? -eq 0 ]; then
    echo "Processing completed successfully"
    echo "Output files are in: $OUTPUT_DIR"
else
    echo "Error: Processing failed"
    exit 1
fi 