# FLAIR-STAR Processor

A Docker-based pipeline for processing FLAIR and SWI DICOM series to generate FLAIR-STAR images. This processor runs as a standalone local application.

## Requirements

- Docker
- Bash shell (Linux/macOS)
- Sufficient disk space for processing

## Quick Start

1. Make the script executable:

```bash
chmod +x flairstar.sh
```

2. Run the processor:

```bash
./flairstar.sh -i /path/to/input/dicoms -o /path/to/output
```
