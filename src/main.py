import argparse
import logging
import json
import shutil
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
    parser.add_argument('--input-dir', required=True, help='Input directory containing DICOM files')
    parser.add_argument('--output-dir', required=True, help='Output directory for processed files')
    parser.add_argument('--temp-dir', required=False, help='Temporary directory for intermediate files')
    return parser.parse_args()

def load_task_json(input_dir):
    """Load and validate task.json if it exists"""
    task_file = Path(input_dir) / 'task.json'
    if not task_file.exists():
        raise ValueError("task.json not found in input directory")
        
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
        
        return settings
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format in task.json: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error processing task.json: {str(e)}")

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
            # Step 1: Load and validate configuration
            logger.info("Step 1: Loading task.json configuration...")
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