import os
import logging
import pydicom
from pynetdicom import AE, StoragePresentationContexts

logger = logging.getLogger(__name__)

class DICOMSender:
    def __init__(self, config):
        """
        Initialize DICOM sender with configuration
        
        Args:
            config (dict): DICOM sending configuration from task.json
        """
        self.config = config
        self.ae = AE()
        self.ae.requested_contexts = StoragePresentationContexts

    def send_dicom_files(self, dicom_directory):
        """
        Send all DICOM files in the specified directory to configured destinations
        
        Args:
            dicom_directory (str): Directory containing DICOM files to send
            
        Returns:
            bool: True if all sends were successful, False otherwise
        """
        if not self.config.get('enabled', False):
            logger.info("DICOM sending is disabled in configuration")
            return True

        success = True
        for destination in self.config.get('destinations', []):
            try:
                success &= self._send_to_destination(dicom_directory, destination)
            except Exception as e:
                logger.error(f"Error sending to {destination['name']}: {str(e)}")
                success = False

        return success

    def _send_to_destination(self, dicom_directory, destination):
        """
        Send DICOM files to a specific destination
        
        Args:
            dicom_directory (str): Directory containing DICOM files
            destination (dict): Destination configuration
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Sending DICOM files to {destination['name']}")
        
        try:
            assoc = self.ae.associate(
                destination['host'],
                destination['port'],
                ae_title=destination['aet']
            )
            
            if not assoc.is_established:
                logger.error(f"Failed to associate with {destination['name']}")
                return False

            success = True
            for root, _, files in os.walk(dicom_directory):
                for filename in files:
                    try:
                        filepath = os.path.join(root, filename)
                        ds = pydicom.dcmread(filepath)
                        
                        status = assoc.send_c_store(ds)
                        
                        if status:
                            logger.debug(f"Successfully sent {filename}")
                        else:
                            logger.error(f"Failed to send {filename}")
                            success = False
                            
                    except Exception as e:
                        logger.error(f"Error processing {filename}: {str(e)}")
                        success = False

            assoc.release()
            return success

        except Exception as e:
            logger.error(f"Connection error with {destination['name']}: {str(e)}")
            return False 