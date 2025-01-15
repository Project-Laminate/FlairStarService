import os
import logging
import numpy as np
import pydicom
import SimpleITK as sitk
from pathlib import Path
from pydicom.uid import generate_uid

logger = logging.getLogger(__name__)

def nifti_to_dicom(nifti_path, reference_dicom, out_folder, series_uid):
    """
    Convert NIFTI file to DICOM series using reference DICOM files.

    Args:
        nifti_path (str): Path to input NIFTI file
        reference_dicom (pydicom.dataset.FileDataset): Reference DICOM dataset
        out_folder (str): Output directory for DICOM files
        series_uid (str): Series Instance UID for the new series.

    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        # Read NIFTI file
        logger.info(f"Reading NIFTI file: {nifti_path}")
        nifti_image = sitk.ReadImage(nifti_path)
        nifti_array = sitk.GetArrayFromImage(nifti_image)

        # Normalize the NIfTI array to the DICOM range (e.g., 0–4095)
        logger.info("Normalizing NIfTI array to match DICOM pixel range.")
        nifti_array = (nifti_array - np.min(nifti_array)) / (np.max(nifti_array) - np.min(nifti_array)) * 4095
        nifti_array = nifti_array.astype(np.uint16)

        # Adjust orientation to match DICOM coordinate system
        logger.info("Adjusting NIfTI orientation to match DICOM coordinate system.")
        nifti_array = np.transpose(nifti_array, (0, 2, 1))  # Transpose axes
        nifti_array = np.flip(nifti_array, axis=1)          # Flip up-down
        nifti_array = np.rot90(nifti_array, k=1, axes=(1, 2))  # Rotate counterclockwise

        # Get reference DICOM directory
        reference_dir = str(Path(reference_dicom.filename).parent)
        logger.info(f"Using reference DICOM directory: {reference_dir}")
        
        # Get all DICOM files from reference directory
        reference_files = sorted([
            os.path.join(reference_dir, f) 
            for f in os.listdir(reference_dir) 
            if f.endswith('.dcm')
        ])
        
        if not reference_files:
            raise ValueError(f"No DICOM files found in reference directory: {reference_dir}")
            
        logger.info(f"Found {len(reference_files)} reference DICOM files")
        
        # Create output directory
        os.makedirs(out_folder, exist_ok=True)
        
        # Check dimensions
        if len(nifti_array) != len(reference_files):
            logger.warning(
                f"Number of NIFTI slices ({len(nifti_array)}) "
                f"doesn't match reference files ({len(reference_files)})"
            )
            
        # Process each slice
        for idx, ref_file in enumerate(reference_files):
            if idx >= len(nifti_array):
                break
                
            # Read reference DICOM
            ref_dcm = pydicom.dcmread(ref_file)
            
            # Create new DICOM dataset
            ds = pydicom.Dataset()
            
            # Copy metadata from reference
            for elem in ref_dcm:
                if elem.tag != pydicom.tag.Tag('PixelData'):
                    ds.add(elem)
            
            # Update necessary DICOM attributes
            ds.file_meta = ref_dcm.file_meta
            ds.is_implicit_VR = ref_dcm.is_implicit_VR
            ds.is_little_endian = ref_dcm.is_little_endian
            
            # Update series-specific attributes
            ds.SeriesInstanceUID = series_uid
            ds.SeriesDescription = 'FLAIR Star'
            ds.SeriesNumber = 1000
            ds.SOPInstanceUID = generate_uid()
            ds.InstanceNumber = idx + 1
            
            # Extract the slice data
            slice_data = nifti_array[idx]
            
            # Ensure pixel data is within 12-bit range (0–4095)
            pixel_data = np.clip(slice_data, 0, 4095).astype(np.uint16)
            
            # Update pixel data attributes
            ds.PixelData = pixel_data.tobytes()
            ds.Rows, ds.Columns = pixel_data.shape
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = "MONOCHROME2"
            ds.BitsAllocated = 16
            ds.BitsStored = 12
            ds.HighBit = 11
            ds.PixelRepresentation = 0
            ds.RescaleIntercept = 0
            ds.RescaleSlope = 1
            ds.WindowCenter = 2047
            ds.WindowWidth = 4095
            
            # Save new DICOM file
            output_file = os.path.join(out_folder, f'{series_uid}_{idx+1:04d}.dcm')
            ds.save_as(output_file, write_like_original=False)
            logger.debug(f"Saved slice {idx + 1}/{len(reference_files)}: {output_file}")
        
        logger.info(f"Successfully converted NIFTI to {len(reference_files)} DICOM files")
        return True
        
    except Exception as e:
        logger.error(f"Error converting NIFTI to DICOM: {str(e)}")
        return False