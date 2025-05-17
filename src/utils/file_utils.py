import os
from pathlib import Path
import pydicom

def find_dicom_files(directory):
    """Recursively find all DICOM files in directory"""
    dicom_files = []
    
    for root, _, files in os.walk(directory):
        for file in files:
            try:
                file_path = Path(root) / file
                pydicom.dcmread(str(file_path), force=True)
                rel_path = os.path.relpath(str(file_path), directory)
                dicom_files.append(rel_path)
            except:
                continue
    
    return dicom_files 