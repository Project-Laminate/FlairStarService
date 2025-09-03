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
    Handles both traditional multi-slice series and enhanced multiframe DICOM files.
    
    Args:
        reference_dicom (pydicom.dataset.FileDataset): A reference DICOM from the series
        
    Returns:
        tuple: (list of DICOM datasets, number of slices/frames, is_multiframe)
    """
    reference_dir = Path(reference_dicom.filename).parent
    series_uid = reference_dicom.SeriesInstanceUID
    
    # Check if this is an enhanced multiframe DICOM
    is_multiframe = hasattr(reference_dicom, 'NumberOfFrames') and reference_dicom.NumberOfFrames > 1
    
    if is_multiframe:
        logger.info(f"Detected enhanced multiframe DICOM with {reference_dicom.NumberOfFrames} frames")
        # For multiframe, we only need the single DICOM file
        return [reference_dicom], reference_dicom.NumberOfFrames, True
    
    # Traditional multi-slice series - find all DICOMs from the same series
    series_files = []
    for file in reference_dir.glob('*.dcm'):
        try:
            ds = pydicom.dcmread(str(file), stop_before_pixels=True, force=True)
            if hasattr(ds, 'SeriesInstanceUID') and ds.SeriesInstanceUID == series_uid:
                series_files.append((ds, file))
        except Exception as e:
            logger.warning(f"Skipping file {file}: {str(e)}")
    
    if not series_files:
        raise ValueError(f"No valid DICOM files found in series {series_uid}")
    
    # Sort by InstanceNumber (for slice order)
    sorted_files = sorted(series_files, key=lambda x: int(x[0].InstanceNumber))
    return [dcm for dcm, _ in sorted_files], len(sorted_files), False

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
        reference_series, n_slices_dicom, is_multiframe = load_reference_series(reference_dicom)
        logger.info(f"Loaded {len(reference_series)} reference DICOM files with {n_slices_dicom} slices/frames")
        
        # Load the NIfTI file
        logger.info(f"Reading NIFTI file: {nifti_path}")
        nifti = nib.load(nifti_path)
        
        # Reorient NIFTI data to match DICOM orientation
        nifti_data, n_slices_nifti = reorient_nifti_data(nifti)
        
        # Compute global min/max for the whole volume
        global_min = np.min(nifti_data)
        global_max = np.max(nifti_data)
        logger.info(f"Global min: {global_min}, max: {global_max} for NIfTI volume")
        
        # Verify slice count compatibility
        if n_slices_nifti != n_slices_dicom:
            raise ValueError(
                f"Number of NIFTI slices ({n_slices_nifti}) "
                f"doesn't match reference series ({n_slices_dicom})"
            )
        
        # Get study UID from reference series (keep the same study)
        study_uid = reference_series[0].StudyInstanceUID
        mr_image_storage_uid = "1.2.840.10008.5.1.4.1.1.4"  # MR Image Storage
        
        # For multiframe DICOM, extract ALL frame data BEFORE any copying
        if is_multiframe:
            ref_dcm = reference_series[0]
            
            # Pre-extract all frame data to avoid shallow copy issues
            frame_data = []
            for z in range(n_slices_dicom):
                frame_info = {
                    'slice_thickness': None,
                    'pixel_spacing': None,
                    'image_orientation': None,
                    'image_position': None,
                    'slice_location': None
                }
                
                if hasattr(ref_dcm, 'PerFrameFunctionalGroupsSequence') and len(ref_dcm.PerFrameFunctionalGroupsSequence) > z:
                    frame_group = ref_dcm.PerFrameFunctionalGroupsSequence[z]
                    logger.debug(f"Pre-extracting frame {z} from PerFrameFunctionalGroupsSequence")
                    
                    # Extract PixelMeasuresSequence (contains SliceThickness and PixelSpacing)
                    if hasattr(frame_group, 'PixelMeasuresSequence'):
                        pixel_measures = frame_group.PixelMeasuresSequence[0]
                        if hasattr(pixel_measures, 'SliceThickness'):
                            frame_info['slice_thickness'] = pixel_measures.SliceThickness
                        if hasattr(pixel_measures, 'PixelSpacing'):
                            frame_info['pixel_spacing'] = pixel_measures.PixelSpacing
                    
                    # Extract PlaneOrientationSequence (contains ImageOrientationPatient)
                    if hasattr(frame_group, 'PlaneOrientationSequence'):
                        plane_orientation = frame_group.PlaneOrientationSequence[0]
                        if hasattr(plane_orientation, 'ImageOrientationPatient'):
                            frame_info['image_orientation'] = plane_orientation.ImageOrientationPatient
                    
                    # Extract PlanePositionSequence (contains ImagePositionPatient) - THIS IS FRAME-SPECIFIC!
                    if hasattr(frame_group, 'PlanePositionSequence'):
                        plane_position = frame_group.PlanePositionSequence[0]
                        if hasattr(plane_position, 'ImagePositionPatient'):
                            frame_info['image_position'] = plane_position.ImagePositionPatient
                            frame_info['slice_location'] = plane_position.ImagePositionPatient[2]
                            
                            logger.debug(f"Pre-extracted ImagePositionPatient for frame {z}: {frame_info['image_position']}")
                
                # Fallback: try to get attributes from SharedFunctionalGroupsSequence
                if hasattr(ref_dcm, 'SharedFunctionalGroupsSequence'):
                    shared_group = ref_dcm.SharedFunctionalGroupsSequence[0]
                    if hasattr(shared_group, 'PixelMeasuresSequence'):
                        pixel_measures = shared_group.PixelMeasuresSequence[0]
                        if hasattr(pixel_measures, 'SliceThickness') and frame_info['slice_thickness'] is None:
                            frame_info['slice_thickness'] = pixel_measures.SliceThickness
                        if hasattr(pixel_measures, 'PixelSpacing') and frame_info['pixel_spacing'] is None:
                            frame_info['pixel_spacing'] = pixel_measures.PixelSpacing
                
                frame_data.append(frame_info)
        
        # Process each slice/frame
        for z in range(n_slices_dicom):
            if is_multiframe:
                # Use pre-extracted frame data
                frame_info = frame_data[z]
                slice_thickness = frame_info['slice_thickness']
                pixel_spacing = frame_info['pixel_spacing']
                image_orientation = frame_info['image_orientation']
                image_position = frame_info['image_position']
                slice_location = frame_info['slice_location']
                
                # Create new DICOM dataset by copying the reference
                ds = ref_dcm.copy()
                # Remove multiframe-specific attributes
                if hasattr(ds, 'NumberOfFrames'):
                    del ds.NumberOfFrames
                if hasattr(ds, 'PerFrameFunctionalGroupsSequence'):
                    del ds.PerFrameFunctionalGroupsSequence
                if hasattr(ds, 'SharedFunctionalGroupsSequence'):
                    del ds.SharedFunctionalGroupsSequence
            else:
                # For traditional series, use the corresponding reference file
                ref_dcm = reference_series[z]
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
            
            # Set instance number for slice ordering
            if is_multiframe:
                ds.InstanceNumber = z + 1
            else:
                ds.InstanceNumber = ref_dcm.InstanceNumber
            
            # Set essential spacing and positioning attributes
            if is_multiframe:
                # For multiframe DICOMs, use the extracted values
                if slice_thickness is not None:
                    ds.SliceThickness = slice_thickness
                if pixel_spacing is not None:
                    ds.PixelSpacing = pixel_spacing
                if image_orientation is not None:
                    ds.ImageOrientationPatient = image_orientation
                if image_position is not None:
                    ds.ImagePositionPatient = image_position
                if slice_location is not None:
                    ds.SliceLocation = slice_location
            else:
                # For traditional DICOMs, copy attributes directly
                if hasattr(ref_dcm, 'SliceThickness'):
                    ds.SliceThickness = ref_dcm.SliceThickness
                if hasattr(ref_dcm, 'SpacingBetweenSlices'):
                    ds.SpacingBetweenSlices = ref_dcm.SpacingBetweenSlices
                if hasattr(ref_dcm, 'PixelSpacing'):
                    ds.PixelSpacing = ref_dcm.PixelSpacing
                if hasattr(ref_dcm, 'ImageOrientationPatient'):
                    ds.ImageOrientationPatient = ref_dcm.ImageOrientationPatient
            
            # Handle slice positioning for traditional series (multiframe positioning is handled above)
            if not is_multiframe:
                # For traditional series, copy the original positioning
                if hasattr(ref_dcm, 'ImagePositionPatient'):
                    ds.ImagePositionPatient = ref_dcm.ImagePositionPatient
                if hasattr(ref_dcm, 'SliceLocation'):
                    ds.SliceLocation = ref_dcm.SliceLocation
            
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
            
            # Scale to DICOM range using global min/max
            if global_max > global_min:
                scaled_data = ((slice_data - global_min) / (global_max - global_min) * 4095)
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
            
            # Copy additional important attributes for proper 3D reconstruction
            if hasattr(ref_dcm, 'ImageType'):
                # Keep original ImageType but mark as derived
                original_type = list(ref_dcm.ImageType) if isinstance(ref_dcm.ImageType, list) else [str(ref_dcm.ImageType)]
                ds.ImageType = ['DERIVED', 'SECONDARY'] + original_type[2:] if len(original_type) > 2 else ['DERIVED', 'SECONDARY']
            
            # Copy study and patient information
            if hasattr(ref_dcm, 'StudyDate'):
                ds.StudyDate = ref_dcm.StudyDate
            if hasattr(ref_dcm, 'StudyTime'):
                ds.StudyTime = ref_dcm.StudyTime
            if hasattr(ref_dcm, 'PatientName'):
                ds.PatientName = ref_dcm.PatientName
            if hasattr(ref_dcm, 'PatientID'):
                ds.PatientID = ref_dcm.PatientID
            if hasattr(ref_dcm, 'PatientBirthDate'):
                ds.PatientBirthDate = ref_dcm.PatientBirthDate
            if hasattr(ref_dcm, 'PatientSex'):
                ds.PatientSex = ref_dcm.PatientSex
            if hasattr(ref_dcm, 'PatientAge'):
                ds.PatientAge = ref_dcm.PatientAge
            
            # Copy acquisition parameters
            if hasattr(ref_dcm, 'AcquisitionDate'):
                ds.AcquisitionDate = ref_dcm.AcquisitionDate
            if hasattr(ref_dcm, 'AcquisitionTime'):
                ds.AcquisitionTime = ref_dcm.AcquisitionTime
            if hasattr(ref_dcm, 'RepetitionTime'):
                ds.RepetitionTime = ref_dcm.RepetitionTime
            if hasattr(ref_dcm, 'EchoTime'):
                ds.EchoTime = ref_dcm.EchoTime
            if hasattr(ref_dcm, 'MagneticFieldStrength'):
                ds.MagneticFieldStrength = ref_dcm.MagneticFieldStrength
            if hasattr(ref_dcm, 'ScanningSequence'):
                ds.ScanningSequence = ref_dcm.ScanningSequence
            if hasattr(ref_dcm, 'SequenceVariant'):
                ds.SequenceVariant = ref_dcm.SequenceVariant
            if hasattr(ref_dcm, 'ScanOptions'):
                ds.ScanOptions = ref_dcm.ScanOptions
            if hasattr(ref_dcm, 'MRAcquisitionType'):
                ds.MRAcquisitionType = ref_dcm.MRAcquisitionType
            
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