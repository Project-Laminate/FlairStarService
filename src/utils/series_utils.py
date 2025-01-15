from pathlib import Path
import pydicom

def collect_series(in_folder, dicom_files, settings):
    """Collect DICOM series that match the patterns"""
    series = {}
    
    for file in dicom_files:
        try:
            dicom_path = Path(in_folder) / file
            dicom = pydicom.dcmread(str(dicom_path))
            
            series_desc = getattr(dicom, 'SeriesDescription', 'Unknown')
            series_uid = getattr(dicom, 'SeriesInstanceUID', 'Unknown')
            
            if (settings["first_pattern"].lower() in series_desc.lower() or 
                settings["second_pattern"].lower() in series_desc.lower()):
                
                if series_uid not in series:
                    series[series_uid] = {
                        'description': series_desc,
                        'files': []
                    }
                series[series_uid]['files'].append(file)
                
        except Exception:
            continue
    
    return series 