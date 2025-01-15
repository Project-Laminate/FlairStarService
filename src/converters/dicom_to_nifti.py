from pathlib import Path
import shutil
import pydicom
from nipype.interfaces.dcm2nii import Dcm2niix
from utils.rule_checker import RuleChecker

def process_series(series_files, in_folder, temp_folder, series_uid, settings):
    """Process a single DICOM series through the conversion pipeline"""

    first_dicom = pydicom.dcmread(str(Path(in_folder) / series_files[0]))
    series_description = getattr(first_dicom, 'SeriesDescription', '')
    
    processing_settings = settings.get("processing", {})
    swi_pattern = processing_settings.get("swi_pattern", {})
    flair_pattern = processing_settings.get("flair_pattern", {})
    
    rule_checker = RuleChecker()
    
    matches_swi, swi_error = rule_checker.check_pattern_rules(first_dicom, swi_pattern)
    matches_flair, flair_error = rule_checker.check_pattern_rules(first_dicom, flair_pattern)
    
    if not (matches_swi or matches_flair):
        return None
    
    safe_description = "".join(c if c.isalnum() else "_" for c in series_description)
    temp_nifti_dir = Path(temp_folder) / "temp_nifti" / safe_description
    temp_nifti_dir.mkdir(exist_ok=True, parents=True)
    
    temp_input_dir = temp_nifti_dir / "input_structure"
    temp_input_dir.mkdir(exist_ok=True, parents=True)
    
    for file in series_files:
        src_path = Path(in_folder) / file
        dst_path = temp_input_dir / Path(file).name
        dst_path.parent.mkdir(exist_ok=True, parents=True)
        shutil.copy2(src_path, dst_path)
    
    converter = Dcm2niix()
    converter.inputs.source_dir = str(temp_input_dir)
    converter.inputs.output_dir = str(temp_nifti_dir)
    converter.inputs.compress = 'y'
    converter.run()
    
    return temp_nifti_dir, series_description 