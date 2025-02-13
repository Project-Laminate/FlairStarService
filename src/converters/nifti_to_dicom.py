import os
import logging
import numpy as np
import pydicom
import nibabel as nib
from pathlib import Path
from pydicom.uid import generate_uid, ExplicitVRLittleEndian
from datetime import datetime

logger = logging.getLogger(__name__)

def load_reference_series(reference_dicom):
    """
    Load and sort the entire reference DICOM series.
    
    Args:
        reference_dicom (pydicom.dataset.FileDataset): A reference DICOM from the series
        
    Returns:
        list: sorted list of DICOM datasets
    """
    reference_dir = Path(reference_dicom.filename).parent
    series_uid = reference_dicom.SeriesInstanceUID
    
    # Find all DICOMs from the same series
    series_files = []
    for file in reference_dir.glob('*.dcm'):
        try:
            ds = pydicom.dcmread(str(file), stop_before_pixels=True)
            if hasattr(ds, 'SeriesInstanceUID') and ds.SeriesInstanceUID == series_uid:
                series_files.append((ds, file))
        except Exception as e:
            logger.warning(f"Skipping file {file}: {str(e)}")
    
    if not series_files:
        raise ValueError(f"No valid DICOM files found in series {series_uid}")
    
    # Sort by InstanceNumber (for slice order)
    sorted_files = sorted(series_files, key=lambda x: int(x[0].InstanceNumber))
    return [dcm for dcm, _ in sorted_files]

def reorient_nifti_data(nifti_img):
    """
    Reorient NIFTI data to match DICOM orientation.
    
    Args:
        nifti_img (nibabel.Nifti1Image): Input NIFTI image
        
    Returns:
        tuple: (reoriented data array, number of slices)
    """
    # Get the orientation from the affine
    affine = nifti_img.affine
    nifti_data = nifti_img.get_fdata()
    
    # Log original shape and affine for debugging
    logger.info(f"Original NIFTI shape: {nifti_data.shape}")
    logger.info(f"NIFTI affine:\n{affine}")
    
    # Determine the slice axis (usually the z-axis)
    # The axis with the largest spacing is typically the slice axis
    voxel_spacing = np.sqrt(np.sum(affine[:3, :3] ** 2, axis=0))
    slice_axis = np.argmax(voxel_spacing)
    logger.info(f"Detected slice axis: {slice_axis}")
    
    # Reorder axes if necessary to ensure slice axis is last
    if slice_axis != 2:
        # Create the transpose order to move slice_axis to the end
        transpose_order = list(range(3))
        transpose_order.pop(slice_axis)
        transpose_order.append(slice_axis)
        logger.info(f"Transposing axes with order: {transpose_order}")
        nifti_data = np.transpose(nifti_data, transpose_order)
    
    # Get the final number of slices
    n_slices = nifti_data.shape[-1]
    logger.info(f"Final shape after reorientation: {nifti_data.shape}")
    
    return nifti_data, n_slices

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
        # Create output directory if it doesn't exist
        if not os.path.exists(out_folder):
            os.makedirs(out_folder)

        # Load the entire reference series
        logger.info("Loading reference DICOM series...")
        reference_series = load_reference_series(reference_dicom)
        n_slices_dicom = len(reference_series)
        logger.info(f"Loaded {n_slices_dicom} reference DICOM files")
        
        # Load the NIfTI file
        logger.info(f"Reading NIFTI file: {nifti_path}")
        nifti = nib.load(nifti_path)
        
        # Reorient NIFTI data to match DICOM orientation
        nifti_data, n_slices_nifti = reorient_nifti_data(nifti)
        
        # Verify slice count compatibility
        if n_slices_nifti != n_slices_dicom:
            raise ValueError(
                f"Number of NIFTI slices ({n_slices_nifti}) "
                f"doesn't match reference series ({n_slices_dicom})"
            )
        
        # Get study UID from reference series (keep the same study)
        study_uid = reference_series[0].StudyInstanceUID
        mr_image_storage_uid = "1.2.840.10008.5.1.4.1.1.4"  # MR Image Storage
        
        # Process each slice
        for z, ref_dcm in enumerate(reference_series):
            # Create new DICOM dataset by copying the reference
            ds = ref_dcm.copy()
            
            # Set transfer syntax: explicit VR, little endian
            ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds.is_implicit_VR = False
            ds.is_little_endian = True
            
            # Update UIDs and metadata
            ds.StudyInstanceUID = study_uid
            ds.SeriesInstanceUID = series_uid
            ds.SOPInstanceUID = generate_uid()
            ds.SOPClassUID = mr_image_storage_uid
            
            # Update series-specific attributes
            ds.SeriesDescription = 'FLAIR Star'
            ds.ProtocolName = 'FLAIR_Star'
            ds.SequenceName = 'flair-star'
            ds.ImageType = ['DERIVED', 'SECONDARY']
            
            # Keep original instance number for slice ordering
            ds.InstanceNumber = ref_dcm.InstanceNumber
            
            # Set Instance Creation Date/Time to current date/time
            now = datetime.now()
            ds.InstanceCreationDate = now.strftime("%Y%m%d")
            ds.InstanceCreationTime = now.strftime("%H%M%S")
            
            # Get the corresponding slice data
            slice_data = nifti_data[:, :, z]
            
            # Match dimensions: check if a transpose is needed
            orig_rows = ds.Rows
            orig_cols = ds.Columns
            if (slice_data.shape[0] == orig_cols) and (slice_data.shape[1] == orig_rows):
                slice_data = slice_data.T
            elif (slice_data.shape[0] != orig_rows) or (slice_data.shape[1] != orig_cols):
                logger.warning(f"Slice {z} shape {slice_data.shape} vs DICOM {orig_rows}x{orig_cols}. Applying transpose.")
                slice_data = slice_data.T
            
            # Apply orientation fixes if needed
            slice_data = np.flip(slice_data, (0, 1))
            
            # Scale to DICOM range while preserving relative intensities
            if np.any(slice_data):  # If not all zeros
                scaled_data = ((slice_data - np.min(slice_data)) / 
                             (np.max(slice_data) - np.min(slice_data)) * 4095)
            else:
                scaled_data = slice_data
            scaled_data = scaled_data.astype(np.uint16)
            
            # Set pixel-related attributes
            ds.Rows = scaled_data.shape[0]
            ds.Columns = scaled_data.shape[1]
            ds.PixelData = scaled_data.tobytes()
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = "MONOCHROME2"
            ds.BitsAllocated = 16
            ds.BitsStored = 12
            ds.HighBit = 11
            ds.PixelRepresentation = 0
            ds["PixelData"].VR = "OW"
            ds.SeriesNumber = 1000
            
            # Set window/level
            ds.WindowCenter = 2047
            ds.WindowWidth = 4095
            ds.RescaleIntercept = 0
            ds.RescaleSlope = 1
            
            # Save the DICOM file
            output_file = os.path.join(out_folder, f'{series_uid}_{z+1:04d}.dcm')
            ds.save_as(output_file, write_like_original=False)
            logger.debug(f"Saved slice {z + 1}/{n_slices_dicom}: {output_file}")
        
        logger.info(f"Successfully converted NIFTI to {n_slices_dicom} DICOM files")
        return True
        
    except Exception as e:
        logger.error(f"Error converting NIFTI to DICOM: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False