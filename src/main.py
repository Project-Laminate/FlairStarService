"""
FLAIR-STAR Processing Pipeline

This script processes DICOM files to create FLAIR-STAR images by combining
SWI (Susceptibility Weighted Imaging) and FLAIR (Fluid Attenuated Inversion Recovery)
MRI sequences.

Usage:
    python main.py --input-dir INPUT_DIR --output-dir OUTPUT_DIR [OPTIONS]

Options:
    --input-dir DIR      Input directory containing DICOM files
    --output-dir DIR     Output directory for processed files
    --temp-dir DIR       Temporary directory for intermediate files
    --swi-pattern STR    Pattern to match SWI series in SeriesDescription
    --flair-pattern STR  Pattern to match FLAIR series in SeriesDescription

You have two options for specifying the series to process:
1. Use a task.json file in the input directory with detailed pattern rules
2. Use the --swi-pattern and --flair-pattern command-line options for simple name matching

If both --swi-pattern and --flair-pattern are provided, they take precedence over task.json.
"""

import argparse
import logging
import json
import shutil
import os
from pathlib import Path
from processors.series_processor import SeriesProcessor
from utils.dicom_utils import find_dicom_series
from utils.dicom_sender import DICOMSender
import sys

def setup_logging():
    """Configure logging with detailed formatting"""
    log_format = (
        '%(asctime)s - %(name)s - %(levelname)s\n'
        'Message: %(message)s\n'
        'Location: %(pathname)s:%(lineno)d\n'
    )
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Suppress excessive logging from some libraries
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('nibabel').setLevel(logging.WARNING)

def setup_argparse():
    parser = argparse.ArgumentParser(description='DICOM processing pipeline')
    parser.add_argument('--input-dir', required=False, help='Input directory containing DICOM files')
    parser.add_argument('--output-dir', required=False, help='Output directory for processed files')
    parser.add_argument('--temp-dir', required=False, help='Temporary directory for intermediate files')
    parser.add_argument('--swi-pattern', required=False, help='Pattern to match SWI series in SeriesDescription (e.g., "SWI")')
    parser.add_argument('--flair-pattern', required=False, help='Pattern to match FLAIR series in SeriesDescription (e.g., "FLAIR")')
    parser.add_argument('--swi-uid', required=False, help='SeriesInstanceUID for SWI series')
    parser.add_argument('--flair-uid', required=False, help='SeriesInstanceUID for FLAIR series')
    args = parser.parse_args()
    
    # Check environment variables if command line arguments aren't provided
    if not args.input_dir:
        args.input_dir = os.environ.get('DATASET_PATH', '/input')
        logging.getLogger(__name__).info(f"Using input directory from environment: {args.input_dir}")
    
    if not args.output_dir:
        args.output_dir = os.environ.get('RESULTS_PATH', '/output')
        logging.getLogger(__name__).info(f"Using output directory from environment: {args.output_dir}")
    
    return args

def load_task_json(input_dir):
    """Load and validate task.json if it exists"""
    task_file = Path(input_dir) / 'task.json'
    logger = logging.getLogger(__name__)
    
    if not task_file.exists():
        logger.warning("task.json not found in input directory")
        
        # Check environment variables for patterns
        swi_pattern = os.environ.get('SWI_PATTERN')
        flair_pattern = os.environ.get('FLAIR_PATTERN')
        
        if swi_pattern and flair_pattern:
            logger.info(f"Using patterns from environment variables: SWI='{swi_pattern}', FLAIR='{flair_pattern}'")
            return create_settings_from_patterns(swi_pattern, flair_pattern)
        else:
            raise ValueError("task.json not found and environment variables SWI_PATTERN and/or FLAIR_PATTERN are not set")
        
    try:
        with open(task_file) as f:
            task_data = json.load(f)
            
        # Check if required fields exist
        if not ('process' in task_data and 
                'settings' in task_data['process'] and 
                'processing' in task_data['process']['settings']):
            raise ValueError(
                "Invalid task.json structure. Required fields missing: "
                "process.settings.processing"
            )
            
        settings = task_data['process']['settings']
        
        # Validate pattern rules
        processing = settings['processing']
        if not ('swi_pattern' in processing and 'flair_pattern' in processing):
            raise ValueError(
                "Missing required patterns in task.json. Both 'swi_pattern' "
                "and 'flair_pattern' must be defined."
            )
        
        # Validate rule structure for each pattern
        for pattern in ['swi_pattern', 'flair_pattern']:
            pattern_rules = processing[pattern]
            if not isinstance(pattern_rules.get('rules', []), list):
                raise ValueError(f"Invalid rules format in {pattern}")
            
            # Check each rule has required fields
            for rule in pattern_rules['rules']:
                if not all(key in rule for key in ['tag', 'operation', 'value']):
                    raise ValueError(
                        f"Missing required fields in rule: {rule}. "
                        "Each rule must have 'tag', 'operation', and 'value'"
                    )
        
        # Add COPY_ALL flag to settings
        copy_all = os.environ.get('COPY_ALL', '').lower() in ('true', 'yes', '1')
        settings['copy_all'] = copy_all
        logger.info(f"COPY_ALL flag is set to: {copy_all}")
        
        return settings
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format in task.json: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error processing task.json: {str(e)}")

def create_settings_from_patterns(swi_pattern, flair_pattern):
    """Create a settings dictionary from pattern strings provided in command line"""
    logger = logging.getLogger(__name__)
    logger.info(f"Creating settings from patterns: SWI='{swi_pattern}', FLAIR='{flair_pattern}'")
    
    # Check for COPY_ALL environment variable
    copy_all = os.environ.get('COPY_ALL', '').lower() in ('true', 'yes', '1')
    
    # Create minimal settings structure with pattern rules
    settings = {
        "processing": {
            "swi_pattern": {
                "rules": [
                    {
                        "tag": "SeriesDescription",
                        "operation": "contains",
                        "value": swi_pattern
                    }
                ]
            },
            "flair_pattern": {
                "rules": [
                    {
                        "tag": "SeriesDescription",
                        "operation": "contains",
                        "value": flair_pattern
                    }
                ]
            }
        },
        "copy_all": copy_all
    }
    
    return settings

def create_settings_from_uids(swi_uid, flair_uid):
    """Create a settings dictionary from SeriesInstanceUIDs provided in command line"""
    logger = logging.getLogger(__name__)
    logger.info(f"Creating settings from UIDs: SWI='{swi_uid}', FLAIR='{flair_uid}'")
    
    # Check for COPY_ALL environment variable
    copy_all = os.environ.get('COPY_ALL', '').lower() in ('true', 'yes', '1')
    
    # Create minimal settings structure with UIDs
    settings = {
        "processing": {
            "swi_pattern": {
                "rules": [
                    {
                        "tag": "SeriesInstanceUID",
                        "operation": "equals",
                        "value": swi_uid
                    }
                ]
            },
            "flair_pattern": {
                "rules": [
                    {
                        "tag": "SeriesInstanceUID",
                        "operation": "equals",
                        "value": flair_uid
                    }
                ]
            }
        },
        "copy_all": copy_all
    }
    
    return settings

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting FLAIR-STAR processing pipeline")
    
    try:
        args = setup_argparse()
        logger.info(f"Processing input directory: {args.input_dir}")
        logger.info(f"Output will be saved to: {args.output_dir}")
        
        # Validate input directory
        input_dir = Path(args.input_dir)
        if not input_dir.exists():
            raise ValueError(f"Input directory does not exist: {input_dir}")
        if not input_dir.is_dir():
            raise ValueError(f"Input path is not a directory: {input_dir}")
        logger.info("Input directory validation successful")
            
        # Validate output directory
        output_dir = Path(args.output_dir)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Output directory created/verified successfully")
        except Exception as e:
            raise ValueError(f"Cannot create output directory: {str(e)}")
            
        # Set up temp directory
        if args.temp_dir:
            temp_dir = Path(args.temp_dir)
            logger.info(f"Using specified temporary directory: {temp_dir}")
        else:
            temp_dir = Path("/tmp") / "flair_star_temp"
            logger.info(f"Using default temporary directory: {temp_dir}")
            
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Temporary directory created successfully")
        except Exception as e:
            raise ValueError(f"Cannot create temporary directory: {str(e)}")
        
        try:
            # Step 1: Load or create configuration
            
            # Check if SeriesInstanceUIDs are provided
            if args.swi_uid and args.flair_uid:
                logger.info("Using SeriesInstanceUIDs for series matching...")
                settings = create_settings_from_uids(args.swi_uid, args.flair_uid)
                logger.info("UID settings created successfully")
            # Check if pattern matching is provided
            elif args.swi_pattern and args.flair_pattern:
                logger.info("Using command-line patterns for series matching...")
                settings = create_settings_from_patterns(args.swi_pattern, args.flair_pattern)
                logger.info("Pattern settings created successfully")
            # Check if one of each is provided (pattern and UID)
            elif (args.swi_pattern and args.flair_uid) or (args.swi_uid and args.flair_pattern):
                logger.warning("Mixed pattern and UID specification is not supported.")
                logger.warning("Please use either patterns or UIDs for both series.")
                
                # Check if env vars can complete the specification
                env_swi_uid = os.environ.get('SWI_UID')
                env_flair_uid = os.environ.get('FLAIR_UID')
                env_swi_pattern = os.environ.get('SWI_PATTERN')
                env_flair_pattern = os.environ.get('FLAIR_PATTERN')
                
                # Try to complete UIDs
                if (args.swi_uid or env_swi_uid) and (args.flair_uid or env_flair_uid):
                    swi = args.swi_uid or env_swi_uid
                    flair = args.flair_uid or env_flair_uid
                    logger.info(f"Using UIDs from combined sources: SWI='{swi}', FLAIR='{flair}'")
                    settings = create_settings_from_uids(swi, flair)
                # Try to complete patterns
                elif (args.swi_pattern or env_swi_pattern) and (args.flair_pattern or env_flair_pattern):
                    swi = args.swi_pattern or env_swi_pattern
                    flair = args.flair_pattern or env_flair_pattern
                    logger.info(f"Using patterns from combined sources: SWI='{swi}', FLAIR='{flair}'")
                    settings = create_settings_from_patterns(swi, flair)
                else:
                    logger.warning("Falling back to task.json configuration.")
                    settings = load_task_json(args.input_dir)
                    logger.info("Configuration loaded and validated successfully")
            # Check if only one pattern/UID is provided
            elif args.swi_pattern or args.flair_pattern or args.swi_uid or args.flair_uid:
                # Determine what's missing and what's provided
                if args.swi_pattern:
                    missing_type = "FLAIR pattern"
                    provided_type = "SWI pattern"
                elif args.flair_pattern:
                    missing_type = "SWI pattern"
                    provided_type = "FLAIR pattern"
                elif args.swi_uid:
                    missing_type = "FLAIR UID"
                    provided_type = "SWI UID"
                else:  # args.flair_uid
                    missing_type = "SWI UID"
                    provided_type = "FLAIR UID"
                
                logger.warning(f"Only {provided_type} was provided. Both are required.")
                
                # Check environment variables
                env_swi_uid = os.environ.get('SWI_UID')
                env_flair_uid = os.environ.get('FLAIR_UID')
                env_swi_pattern = os.environ.get('SWI_PATTERN')
                env_flair_pattern = os.environ.get('FLAIR_PATTERN')
                
                # Try to complete UIDs
                if (args.swi_uid or env_swi_uid) and (args.flair_uid or env_flair_uid):
                    swi = args.swi_uid or env_swi_uid
                    flair = args.flair_uid or env_flair_uid
                    logger.info(f"Using UIDs from combined sources: SWI='{swi}', FLAIR='{flair}'")
                    settings = create_settings_from_uids(swi, flair)
                # Try to complete patterns
                elif (args.swi_pattern or env_swi_pattern) and (args.flair_pattern or env_flair_pattern):
                    swi = args.swi_pattern or env_swi_pattern
                    flair = args.flair_pattern or env_flair_pattern
                    logger.info(f"Using patterns from combined sources: SWI='{swi}', FLAIR='{flair}'")
                    settings = create_settings_from_patterns(swi, flair)
                else:
                    logger.warning(f"Falling back to task.json configuration.")
                    settings = load_task_json(args.input_dir)
                    logger.info("Configuration loaded and validated successfully")
            else:
                # Check environment variables first
                env_swi_uid = os.environ.get('SWI_UID')
                env_flair_uid = os.environ.get('FLAIR_UID')
                env_swi_pattern = os.environ.get('SWI_PATTERN')
                env_flair_pattern = os.environ.get('FLAIR_PATTERN')
                
                if env_swi_uid and env_flair_uid:
                    logger.info(f"Using UIDs from environment variables: SWI='{env_swi_uid}', FLAIR='{env_flair_uid}'")
                    settings = create_settings_from_uids(env_swi_uid, env_flair_uid)
                    logger.info("UID settings created successfully")
                elif env_swi_pattern and env_flair_pattern:
                    logger.info(f"Using patterns from environment variables: SWI='{env_swi_pattern}', FLAIR='{env_flair_pattern}'")
                    settings = create_settings_from_patterns(env_swi_pattern, env_flair_pattern)
                    logger.info("Pattern settings created successfully")
                else:
                    logger.info("Loading task.json configuration...")
                    settings = load_task_json(args.input_dir)
                    logger.info("Configuration loaded and validated successfully")
            
            # Step 2: Find matching DICOM series
            logger.info("Step 2: Scanning for matching DICOM series...")
            series_dict = find_dicom_series(args.input_dir, settings)
            
            if not series_dict:
                raise ValueError("No matching DICOM series found in input directory")
            
            # Log found series details
            logger.info(f"Found {len(series_dict)} matching DICOM series:")
            for series_uid, data in series_dict.items():
                logger.info(f"  - Series UID: {series_uid}")
                logger.info(f"    Description: {data['description']}")
                logger.info(f"    Type: {data['pattern_type']}")
                logger.info(f"    Number of files: {len(data['files'])}")
            
            # Step 3: Initialize processor
            logger.info("Step 3: Initializing series processor...")
            processor = SeriesProcessor(
                args.input_dir,
                output_dir,
                temp_dir,
                settings
            )
            
            # Step 4: Process the series
            logger.info("Step 4: Starting series processing...")
            success = processor.process_series(series_dict)
            
            if not success:
                raise ValueError("Series processing failed")
                
            logger.info("Series processing completed successfully")
            
            # Step 5: DICOM sending (if configured)
            dicom_send_config = settings.get('dicom_send', {})
            if dicom_send_config:
                logger.info("Step 5: Starting DICOM sending process...")
                logger.info(f"DICOM destination: {dicom_send_config.get('host', 'unknown')}:"
                          f"{dicom_send_config.get('port', 'unknown')}")
                
                sender = DICOMSender(dicom_send_config)
                send_success = sender.send_dicom_files(str(output_dir))
                
                if not send_success:
                    raise ValueError("DICOM sending failed")
                logger.info("DICOM sending completed successfully")
            else:
                logger.info("Step 5: DICOM sending not configured, skipping")
                
            logger.info("All processing steps completed successfully")
                
        finally:
            # Cleanup step
            logger.info("Cleanup: Removing temporary files...")
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                    logger.info("Temporary directory removed successfully")
                except Exception as e:
                    logger.error(f"Error cleaning up temporary directory: {str(e)}")
            
    except ValueError as e:
        logger.error(f"Processing failed: {str(e)}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during processing: {str(e)}")
        logger.error("Stack trace:", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()