import os
import pydicom
import logging
from collections import defaultdict
from pathlib import Path
from datetime import datetime
from .rule_checker import RuleChecker

logger = logging.getLogger(__name__)

def get_series_timestamp(dcm):
    """Get timestamp from DICOM file for sorting"""
    try:
        # Try to get acquisition time
        date_str = getattr(dcm, 'AcquisitionDate', getattr(dcm, 'SeriesDate', getattr(dcm, 'StudyDate', '')))
        time_str = getattr(dcm, 'AcquisitionTime', getattr(dcm, 'SeriesTime', getattr(dcm, 'StudyTime', '')))
        
        if date_str and time_str:
            # Handle time format with fractional seconds
            time_str = time_str.split('.')[0]
            try:
                return datetime.strptime(f"{date_str}{time_str}", '%Y%m%d%H%M%S')
            except ValueError:
                return datetime.strptime(date_str, '%Y%m%d')
        elif date_str:
            return datetime.strptime(date_str, '%Y%m%d')
        else:
            return datetime.min
    except Exception as e:
        logger.debug(f"Error getting timestamp: {str(e)}")
        return datetime.min

def find_dicom_series(directory, settings):
    """
    Find and organize DICOM files into series based on pattern rules
    
    Args:
        directory (str): Path to directory containing DICOM files
        settings (dict): Settings containing pattern rules
        
    Returns:
        dict: Dictionary of series with their files and metadata
        {
            series_uid: {
                'files': [file_paths],
                'description': series_description,
                'pattern_type': 'swi_pattern' or 'flair_pattern'
            }
        }
    """
    pattern_series = {
        'swi_pattern': [],
        'flair_pattern': []
    }
    
    series_dict = defaultdict(lambda: {'files': [], 'description': None, 'pattern_type': None, 'timestamp': None})
    directory = Path(directory)
    
    logger.info(f"Scanning directory {directory} for DICOM files")
    
    rule_checker = RuleChecker()
    patterns = settings.get('processing', {})
    
    series_files = defaultdict(list)
    series_info = {}
    
    # First pass: collect all series
    for root, _, files in os.walk(directory):
        for filename in files:
            if not filename.endswith('.dcm'):
                continue
                
            filepath = Path(root) / filename
            try:
                dcm = pydicom.dcmread(str(filepath), stop_before_pixels=True)
                series_uid = dcm.SeriesInstanceUID
                rel_path = filepath.relative_to(directory)
                series_files[series_uid].append(str(rel_path))
                
                if series_uid not in series_info:
                    series_info[series_uid] = {
                        'description': getattr(dcm, 'SeriesDescription', 'Unknown'),
                        'first_file': dcm,
                        'timestamp': get_series_timestamp(dcm)
                    }
            except Exception as e:
                logger.debug(f"Skipping file {filepath}: {str(e)}")
                continue
    
    # Second pass: match patterns and handle multiple matches
    for series_uid, info in series_info.items():
        dcm = info['first_file']
        
        for pattern_name, pattern_rules in patterns.items():
            if pattern_name not in ['swi_pattern', 'flair_pattern']:
                continue
                
            success, error_msg = rule_checker.check_pattern_rules(dcm, pattern_rules)
            if success:
                pattern_series[pattern_name].append({
                    'series_uid': series_uid,
                    'description': info['description'],
                    'timestamp': info['timestamp'],
                    'files': series_files[series_uid]
                })
    
    # Handle multiple matches by selecting the latest series
    for pattern_name, matched_series in pattern_series.items():
        if len(matched_series) == 0:
            logger.error(f"No series found matching {pattern_name}")
            return None
        elif len(matched_series) > 1:
            logger.warning(f"Multiple series found matching {pattern_name}:")
            for series in matched_series:
                logger.warning(f"  - {series['description']} (Time: {series['timestamp']})")
            
            # Sort by timestamp and select the latest
            latest_series = max(matched_series, key=lambda x: x['timestamp'])
            logger.info(f"Selected latest series for {pattern_name}: {latest_series['description']} "
                       f"(Time: {latest_series['timestamp']})")
            
            # Update series_dict with only the latest series
            series_dict[latest_series['series_uid']] = {
                'files': latest_series['files'],
                'description': latest_series['description'],
                'pattern_type': pattern_name
            }
        else:
            # Single match case
            series = matched_series[0]
            series_dict[series['series_uid']] = {
                'files': series['files'],
                'description': series['description'],
                'pattern_type': pattern_name
            }
    
    if series_dict:
        logger.info(f"Found {len(series_dict)} matching series:")
        for uid, data in series_dict.items():
            logger.info(f"  - {data['pattern_type']}: {data['description']}")
    else:
        logger.warning("No matching series found")
    
    return series_dict 