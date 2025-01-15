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

## Usage

The `flairstar.sh` script handles Docker setup and execution:

```bash
Usage: ./flairstar.sh -i <input_dir> -o <output_dir>

Options:
  -i, --input     Input directory containing DICOM files
  -o, --output    Output directory for processed files
  -h, --help      Show this help message
```

### Docker Integration

The script automatically:
- Checks for Docker installation
- Builds the Docker image if needed (`flair-star-processor:latest`)
- Mounts input/output directories
- Sets appropriate environment variables
- Configures network access (host network mode)
- Reports processing status

Input and output directories are mounted as Docker volumes:
- Input: `/data/input` (read-only)
- Output: `/data/output` (read-write)

Environment variables set in the container:
- `INPUT_DIR`: Path to input directory
- `OUTPUT_DIR`: Path to output directory

## Configuration

### Task Configuration

The pipeline uses `task.json` to configure series matching rules and DICOM sending options. Place it in the input directory with your DICOM files.

```json
{
    "process": {
        "settings": {
            "processing": {
                "swi_pattern": {
                    "rules": [
                        {
                            "tag": "SeriesDescription",
                            "operation": "equals",
                            "value": "SWI_Images"
                        }
                    ]
                },
                "flair_pattern": {
                    "rules": [
                        {
                            "tag": "SeriesDescription",
                            "operation": "contains",
                            "value": "t2_space_dark-fluid"
                        }
                    ]
                }
            },
            "dicom_send": {
                "enabled": true,
                "destinations": [
                    {
                        "name": "PACS",
                        "aet": "PACS_AET",
                        "host": "pacs.hospital.com",
                        "port": 11112
                    }
                ]
            }
        }
    }
}
```

### DICOM Send Configuration

The `dicom_send` section in `task.json` configures automatic DICOM sending after successful processing:

#### Configuration Options
- `enabled`: Enable/disable DICOM sending (boolean)
- `destinations`: List of DICOM destinations

#### Destination Parameters
- `name`: Friendly name for the destination
- `aet`: Application Entity Title of the destination
- `host`: Hostname or IP address of the DICOM receiver
- `port`: Port number of the DICOM receiver

Multiple destinations can be configured:

```json
"destinations": [
    {
        "name": "PACS1",
        "aet": "PACS1_AET",
        "host": "pacs1.hospital.com",
        "port": 11112
    },
    {
        "name": "PACS2",
        "aet": "PACS2_AET",
        "host": "pacs2.hospital.com",
        "port": 11112
    }
]
```

### Pattern Rules

Each pattern (`swi_pattern` and `flair_pattern`) uses rules to match DICOM attributes:

#### Rule Structure

```json
{
    "tag": "DICOM_TAG",
    "operation": "OPERATION",
    "value": "VALUE"
}
```

#### Available Operations

- `equals`: Exact match
- `contains`: String contains value
- `contains_all`: String contains all values in list
- `contains_any`: String contains any value in list
- `starts_with`: String starts with value
- `ends_with`: String ends with value
- `regex`: Regular expression match
- `range`: Numeric range check
- `greater_than`: Numeric greater than
- `less_than`: Numeric less than
- `not_equals`: Not equal to value
- `not_contains`: String does not contain value

#### Important Notes

1. If a pattern has only one rule, it is automatically required
2. Multiple rules can be combined
3. Each pattern must match exactly one series
4. If multiple series match a pattern, it's considered an error

## Processing Pipeline

1. **Series Detection**
   - Scans input directory for DICOM files
   - Applies pattern matching rules from task.json
   - Identifies SWI and FLAIR series

2. **DICOM to NIFTI Conversion**
   - Converts matched series to NIFTI format
   - Preserves metadata for later reconstruction

3. **FLAIR-STAR Processing**
   - Processes SWI and FLAIR NIFTI files
   - Generates FLAIR-STAR images

4. **NIFTI to DICOM Conversion**
   - Converts processed NIFTI back to DICOM
   - Maintains original DICOM attributes

5. **DICOM Sending**
   - Verifies DICOM sending configuration in task.json
   - Establishes connection with configured PACS destinations
   - Sends processed DICOM files using C-STORE
   - Validates successful transmission
   - Supports multiple PACS destinations
   - Reports sending status for each file and destination

Example DICOM sending configuration in task.json:

```json
    "dicom_send": {
        "enabled": true,
        "destinations": [
            {
                "name": "Primary PACS",
                "aet": "PACS_AET",
                "host": "pacs.hospital.com",
                "port": 11112
            }
        ]
    }
```