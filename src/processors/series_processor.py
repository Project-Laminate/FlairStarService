from pathlib import Path
import logging
import shutil
import pydicom
from converters.dicom_to_nifti import process_series
from converters.nifti_to_dicom import nifti_to_dicom
from .nifti_processor import NiftiProcessor
import os
from pydicom.uid import generate_uid


class SeriesProcessor:
    def __init__(self, in_folder, out_folder, temp_folder, settings):
        self.in_folder = Path(in_folder)
        self.out_folder = Path(out_folder)
        self.temp_folder = Path(temp_folder)
        self.settings = settings
        self.logger = logging.getLogger(__name__)

    def _copy_input_dicoms(self, first_series, second_series):
        """Copy all input DICOM series and converted FLAIR-STAR files to output directory"""
        self.logger.info("Copying DICOM files to output directory...")
        
        try:
            self.logger.info("Copying all input DICOM files...")
            input_files = []
            
            for root, _, files in os.walk(self.in_folder):
                for file in files:
                    if file.endswith('.dcm'):
                        src_path = Path(root) / file
                        dst_path = self.out_folder / file
                        shutil.copy2(src_path, dst_path)
                        input_files.append(file)
            
            self.logger.info(f"Successfully copied {len(input_files)} input DICOM files")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to copy DICOM files: {str(e)}")
            return False

    def process_series(self, series_dict):
        """Main processing pipeline for series"""
        self.logger.info("Starting processing pipeline")
        
        swi_series = None
        flair_series = None
        
        for series_uid, data in series_dict.items():
            if data['pattern_type'] == 'swi_pattern':
                swi_series = (series_uid, data)
                self.logger.info(f"Found SWI series: {data['description']}")
            elif data['pattern_type'] == 'flair_pattern':
                flair_series = (series_uid, data)
                self.logger.info(f"Found FLAIR series: {data['description']}")

        if not (swi_series and flair_series):
            self.logger.error("Could not find both required series")
            return False

        try:
            nifti_files = self._convert_matched_series(swi_series, flair_series)
            if not nifti_files:
                return False

            result_file = self._process_nifti_files(nifti_files)
            if not result_file:
                return False

            success = self._convert_to_dicom(result_file, swi_series[1])
            if not success:
                return False
                
            # Check if we should copy all input DICOM files
            copy_all = self.settings.get('copy_all', False)
            if copy_all:
                self.logger.info("COPY_ALL flag is set, copying all input DICOM files...")
                if not self._copy_input_dicoms(swi_series, flair_series):
                    return False
            else:
                self.logger.info("COPY_ALL flag is not set, skipping copy of input DICOM files")

            return True

        except Exception as e:
            self.logger.error(f"Processing failed: {str(e)}")
            return False

    def _convert_matched_series(self, first_series, second_series):
        """Convert only the matched series to NIFTI"""
        self.logger.info("Starting DICOM to NIFTI conversion process...")
        
        nifti_base_dir = self.temp_folder / "temp_nifti"
        first_nifti_dir = nifti_base_dir / "first_series"
        second_nifti_dir = nifti_base_dir / "second_series"
        
        first_nifti_dir.mkdir(parents=True, exist_ok=True)
        second_nifti_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            self.logger.info(f"Converting first series ({first_series[1]['description']})...")
            self.logger.info(f"Number of files in first series: {len(first_series[1]['files'])}")
            
            for i, file in enumerate(first_series[1]['files'][:3]):
                self.logger.info(f"First series file {i}: {file}")
            
            first_result = process_series(
                first_series[1]['files'],
                self.in_folder,
                first_nifti_dir,
                first_series[0],
                self.settings
            )
            
            if first_result:
                self.logger.info(f"First series converted successfully: {first_result}")
                first_nifti_files = list(first_nifti_dir.glob('**/*.nii.gz'))
                self.logger.info(f"First series NIFTI files: {first_nifti_files}")
            else:
                self.logger.error("Failed to convert first series")
                return None
                
            self.logger.info(f"Converting second series ({second_series[1]['description']})...")
            self.logger.info(f"Number of files in second series: {len(second_series[1]['files'])}")
            
            for i, file in enumerate(second_series[1]['files'][:3]):
                self.logger.info(f"Second series file {i}: {file}")
                
            second_result = process_series(
                second_series[1]['files'],
                self.in_folder,
                second_nifti_dir,
                second_series[0],
                self.settings
            )
            
            if second_result:
                self.logger.info(f"Second series converted successfully: {second_result}")
                second_nifti_files = list(second_nifti_dir.glob('**/*.nii.gz'))
                self.logger.info(f"Second series NIFTI files: {second_nifti_files}")
            else:
                self.logger.error("Failed to convert second series")
                return None
                
            first_nifti = list(first_nifti_dir.glob('**/*.nii.gz'))
            second_nifti = list(second_nifti_dir.glob('**/*.nii.gz'))
            
            if not first_nifti:
                self.logger.error("No NIFTI file found for first series")
                return None
            if not second_nifti:
                self.logger.error("No NIFTI file found for second series")
                return None
                
            return (str(first_nifti[0]), str(second_nifti[0]))
            
        except Exception as e:
            self.logger.error(f"Error during conversion: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
        

    def _process_nifti_files(self, nifti_files):
        """Process NIFTI files using NiftiProcessor"""
        if not nifti_files:
            return None
            
        first_nifti, second_nifti = nifti_files
        result_dir = self.temp_folder / "processing_result"
        result_dir.mkdir(exist_ok=True, parents=True)
        
        try:
            processor = NiftiProcessor(str(result_dir))
            return processor.process(first_nifti, second_nifti)
        except Exception as e:
            self.logger.error(f"Failed to process images: {str(e)}")
            return None

    def _convert_to_dicom(self, nifti_file, series):
        """Convert NIFTI result back to DICOM"""
        try:
            reference_dicom = pydicom.dcmread(
                str(self.in_folder / series['files'][0])
            )
            result_series_uid = generate_uid()
            nifti_to_dicom(
                nifti_file, 
                reference_dicom, 
                self.out_folder, 
                result_series_uid
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to convert result to DICOM: {str(e)}")
            return False
            
    def _verify_series(self, series_data, series_type):
        """Verify that a series has valid DICOM files"""
        if not series_data['files']:
            self.logger.error(f"{series_type} series has no files")
            return False
            
        for file_path in series_data['files']:
            full_path = self.in_folder / file_path
            if not full_path.exists():
                self.logger.error(f"Missing DICOM file in {series_type} series: {file_path}")
                return False
                
        return True

    def _cleanup(self):
        """Clean up temporary files"""
        self.logger.info("Cleaning up temporary files")
        shutil.rmtree(self.temp_folder / "temp_nifti", ignore_errors=True)
        shutil.rmtree(self.temp_folder / "processing_result", ignore_errors=True)