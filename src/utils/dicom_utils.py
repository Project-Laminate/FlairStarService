import os
import pydicom
import logging
from collections import defaultdict
from pathlib import Path
from datetime import datetime
from .rule_checker import RuleChecker
import traceback

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

def extract_series_uid_from_path(filepath):
    """Try to extract the SeriesInstanceUID from the file path"""
    # Convert to string if it's a Path object
    if isinstance(filepath, Path):
        filepath = str(filepath)
    
    # Split the path into components
    parts = filepath.split(os.sep)
    
    # Look for a component that looks like a UID (has many dots and numbers)
    for part in parts:
        if part.count('.') > 5 and all(c.isdigit() or c == '.' for c in part):
            return part
    
    return None

def safe_dcm_read(filepath):
    """Try multiple approaches to read a DICOM file"""
    try:
        # First attempt - normal read with force=False
        try:
            return pydicom.dcmread(str(filepath), stop_before_pixels=True, force=False)
        except Exception as e:
            logger.debug(f"First attempt to read DICOM failed: {str(e)}")
            
        # Second attempt - force=True
        try:
            return pydicom.dcmread(str(filepath), stop_before_pixels=True, force=True)
        except Exception as e:
            logger.debug(f"Second attempt to read DICOM with force=True failed: {str(e)}")
            
        # Third attempt - try reading with different transfer syntax
        try:
            dataset = pydicom.dcmread(str(filepath), stop_before_pixels=True, force=True)
            dataset.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
            return dataset
        except Exception as e:
            logger.debug(f"Third attempt with different transfer syntax failed: {str(e)}")
            
        # Final attempt - read specific tags only
        try:
            tags = [(0x0020, 0x000e)]  # Series Instance UID
            dataset = pydicom.dcmread(str(filepath), specific_tags=tags, force=True)
            return dataset
        except Exception as e:
            logger.debug(f"Final attempt with specific tags failed: {str(e)}")
            
        raise ValueError("All DICOM reading attempts failed")
            
    except Exception as e:
        logger.debug(f"All attempts to read DICOM file {filepath} failed: {str(e)}")
        return None

def get_series_uid(dcm, filepath):
    """Extract SeriesInstanceUID using different methods"""
    if dcm is None:
        return None
    
    # Method 1: Get from DICOM attribute
    try:
        if hasattr(dcm, 'SeriesInstanceUID'):
            return dcm.SeriesInstanceUID
    except Exception as e:
        logger.debug(f"Failed to get SeriesInstanceUID from DICOM attribute: {str(e)}")
    
    # Method 2: Get from DICOM elements
    try:
        series_tag = (0x0020, 0x000e)  # Series Instance UID tag
        if series_tag in dcm:
            return dcm[series_tag].value
    except Exception as e:
        logger.debug(f"Failed to get SeriesInstanceUID from DICOM elements: {str(e)}")
    
    # Method 3: Extract from directory name
    return extract_series_uid_from_path(filepath)

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
    logger.info(f"Looking for patterns in settings: {settings.get('processing', {}).keys()}")
    
    # Get the target UIDs we're looking for
    swi_uid = None
    flair_uid = None
    proc_settings = settings.get('processing', {})
    
    if 'swi_pattern' in proc_settings and 'rules' in proc_settings['swi_pattern']:
        for rule in proc_settings['swi_pattern']['rules']:
            if rule.get('tag') == 'SeriesInstanceUID' and rule.get('operation') == 'equals':
                swi_uid = rule.get('value')
                logger.info(f"Looking for SWI UID: {swi_uid}")
                break
                
    if 'flair_pattern' in proc_settings and 'rules' in proc_settings['flair_pattern']:
        for rule in proc_settings['flair_pattern']['rules']:
            if rule.get('tag') == 'SeriesInstanceUID' and rule.get('operation') == 'equals':
                flair_uid = rule.get('value')
                logger.info(f"Looking for FLAIR UID: {flair_uid}")
                break
    
    rule_checker = RuleChecker()
    patterns = settings.get('processing', {})
    
    # Log all subdirectories for debugging
    all_dirs = []
    for root, dirs, _ in os.walk(directory):
        for dir_name in dirs:
            all_dirs.append(os.path.join(root, dir_name))
    logger.info(f"Found {len(all_dirs)} subdirectories to search")
    
    # Check if our target UIDs are in the directory names
    if swi_uid:
        matching_dirs = [d for d in all_dirs if swi_uid in d]
        logger.info(f"Found {len(matching_dirs)} directories containing SWI UID")
        if matching_dirs:
            for d in matching_dirs[:3]:  # Show first 3 matches
                logger.info(f"  - {d}")
    
    if flair_uid:
        matching_dirs = [d for d in all_dirs if flair_uid in d]
        logger.info(f"Found {len(matching_dirs)} directories containing FLAIR UID")
        if matching_dirs:
            for d in matching_dirs[:3]:  # Show first 3 matches
                logger.info(f"  - {d}")
    
    dcm_count = 0
    dcm_with_uid_count = 0
    series_files = defaultdict(list)
    series_info = {}
    
    # Store a mapping of extracted UIDs to files for thorough debugging
    found_uids = defaultdict(list)
    
    # First pass: collect all series
    for root, _, files in os.walk(directory):
        root_path = Path(root)
        for filename in files:
            if not filename.lower().endswith(('.dcm', '.ima', '.dicom')):
                continue
                
            dcm_count += 1
            filepath = root_path / filename
            
            # Try to read DICOM file with multiple approaches
            try:
                dcm = safe_dcm_read(str(filepath))
                if dcm is None:
                    continue
                    
                # Try to get SeriesInstanceUID using multiple methods
                series_uid = get_series_uid(dcm, filepath)
                if not series_uid:
                    # Last resort: just use the parent directory name if it looks like a UID
                    parent_dir = os.path.basename(os.path.dirname(filepath))
                    if parent_dir.count('.') > 5:
                        series_uid = parent_dir
                        logger.debug(f"Using parent directory as UID: {series_uid}")
                    else:
                        logger.debug(f"Skipping file {filepath}: No SeriesInstanceUID found in any method")
                        continue
                
                dcm_with_uid_count += 1
                
                # Add to our debugging map
                found_uids[series_uid].append(str(filepath))
                
                # Special handling for the specific UIDs we're looking for
                if series_uid == swi_uid or series_uid == flair_uid:
                    logger.info(f"Found exact match for target UID: {series_uid} in file {filepath}")
                
                rel_path = filepath.relative_to(directory)
                series_files[series_uid].append(str(rel_path))
                
                if series_uid not in series_info:
                    series_desc = getattr(dcm, 'SeriesDescription', 'Unknown')
                    logger.debug(f"Found series: {series_uid} - {series_desc}")
                    series_info[series_uid] = {
                        'description': series_desc,
                        'first_file': dcm,
                        'timestamp': get_series_timestamp(dcm)
                    }
            except Exception as e:
                logger.debug(f"Error processing file {filepath}: {str(e)}")
                logger.debug(traceback.format_exc())
                continue
    
    logger.info(f"Scanned {dcm_count} DICOM files, found {dcm_with_uid_count} with UIDs")
    logger.info(f"Found {len(series_info)} unique series")
    
    # Log all found series for debugging
    logger.info("Found series UIDs:")
    for uid in sorted(series_info.keys()):
        info = series_info[uid]
        logger.info(f"  - {uid}: {info['description']} ({len(series_files[uid])} files)")
    
    # If our target UIDs are found directly in the directory structure,
    # create a synthetic series entry for each
    if swi_uid and swi_uid not in series_info:
        matching_dirs = [d for d in all_dirs if swi_uid in d]
        if matching_dirs:
            logger.info(f"Creating synthetic entry for SWI UID from directory: {swi_uid}")
            # Find all DICOM files in and under this directory
            found_files = []
            swi_dir = matching_dirs[0]
            for root, _, files in os.walk(swi_dir):
                for file in files:
                    if file.lower().endswith(('.dcm', '.ima', '.dicom')):
                        found_files.append(os.path.join(root, file))
            
            if found_files:
                # Use the first file to get some metadata
                try:
                    dcm = safe_dcm_read(found_files[0])
                    if dcm:
                        series_info[swi_uid] = {
                            'description': getattr(dcm, 'SeriesDescription', 'SWI Series'),
                            'first_file': dcm,
                            'timestamp': get_series_timestamp(dcm)
                        }
                        # Add all files to this series
                        for file in found_files:
                            rel_path = os.path.relpath(file, str(directory))
                            series_files[swi_uid].append(rel_path)
                except Exception as e:
                    logger.error(f"Error creating synthetic SWI entry: {str(e)}")
    
    if flair_uid and flair_uid not in series_info:
        matching_dirs = [d for d in all_dirs if flair_uid in d]
        if matching_dirs:
            logger.info(f"Creating synthetic entry for FLAIR UID from directory: {flair_uid}")
            # Find all DICOM files in and under this directory
            found_files = []
            flair_dir = matching_dirs[0]
            for root, _, files in os.walk(flair_dir):
                for file in files:
                    if file.lower().endswith(('.dcm', '.ima', '.dicom')):
                        found_files.append(os.path.join(root, file))
            
            if found_files:
                # Use the first file to get some metadata
                try:
                    dcm = safe_dcm_read(found_files[0])
                    if dcm:
                        series_info[flair_uid] = {
                            'description': getattr(dcm, 'SeriesDescription', 'FLAIR Series'),
                            'first_file': dcm,
                            'timestamp': get_series_timestamp(dcm)
                        }
                        # Add all files to this series
                        for file in found_files:
                            rel_path = os.path.relpath(file, str(directory))
                            series_files[flair_uid].append(rel_path)
                except Exception as e:
                    logger.error(f"Error creating synthetic FLAIR entry: {str(e)}")
    
    # If we found any UIDs at all but not the ones we're looking for, do a more thorough search
    if dcm_with_uid_count > 0 and ((swi_uid and swi_uid not in series_info) or (flair_uid and flair_uid not in series_info)):
        # Log all UIDs and their counts
        logger.info("All UIDs found in dataset:")
        for uid, files in found_uids.items():
            logger.info(f"  - {uid}: {len(files)} files")
            # Show example paths for the first few files
            for file in files[:3]:
                logger.info(f"    - {file}")
    
    # Second pass: match patterns and handle multiple matches
    for series_uid, info in series_info.items():
        dcm = info['first_file']
        
        for pattern_name, pattern_rules in patterns.items():
            if pattern_name not in ['swi_pattern', 'flair_pattern']:
                continue
                
            # For SeriesInstanceUID matching, handle it directly
            if (pattern_rules.get('rules') and 
                len(pattern_rules['rules']) == 1 and 
                pattern_rules['rules'][0].get('tag') == 'SeriesInstanceUID' and
                pattern_rules['rules'][0].get('operation') == 'equals'):
                
                target_uid = pattern_rules['rules'][0].get('value')
                if series_uid == target_uid:
                    logger.info(f"Series {series_uid} matches pattern {pattern_name} by direct UID comparison")
                    pattern_series[pattern_name].append({
                        'series_uid': series_uid,
                        'description': info['description'],
                        'timestamp': info['timestamp'],
                        'files': series_files[series_uid]
                    })
                continue
                
            # Otherwise use the rule checker
            success, error_msg = rule_checker.check_pattern_rules(dcm, pattern_rules)
            if success:
                logger.info(f"Series {series_uid} matches pattern {pattern_name}")
                pattern_series[pattern_name].append({
                    'series_uid': series_uid,
                    'description': info['description'],
                    'timestamp': info['timestamp'],
                    'files': series_files[series_uid]
                })
            else:
                # Log reasons for not matching
                logger.debug(f"Series {series_uid} does not match {pattern_name}: {error_msg}")
    
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