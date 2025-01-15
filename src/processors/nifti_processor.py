import os
import subprocess
import shlex
from .base_processor import BaseProcessor

class NiftiProcessor(BaseProcessor):
    def process(self, input1, input2):
            """
            Register input1 to input2 space using FLIRT and then multiply
            
            Args:
                input1 (str): Path to first NIFTI file (will be registered to input2)
                input2 (str): Path to second NIFTI file (reference)
                
            Returns:
                str: Path to output multiplied file
            """
            try:
                registered_file = os.path.join(self.output_dir, 'input1_registered.nii.gz')
                output_file = os.path.join(self.output_dir, 'FLAIR-STAR.nii.gz')

                self.logger.info(f"Verifying input files...")
                self.logger.info(f"First input: {input1}")
                self.logger.info(f"Second input: {input2}")
                
                if not os.path.exists(input1):
                    raise FileNotFoundError(f"First input file not found: {input1}")
                if not os.path.exists(input2):
                    raise FileNotFoundError(f"Second input file not found: {input2}")

                self.logger.info("Starting FLIRT registration...")
                flirt_cmd = f"flirt -in {shlex.quote(input2)} -ref {shlex.quote(input1)} -out {shlex.quote(registered_file)}"
                self.logger.info(f"Running FLIRT command: {flirt_cmd}")
                subprocess.run(flirt_cmd, shell=True, check=True)

                if not os.path.exists(registered_file):
                    raise FileNotFoundError(f"Registration failed: {registered_file} not created")
                self.logger.info(f"Registration successful, output saved to: {registered_file}")

                self.logger.info("Starting fslmaths multiplication...")
                multiply_cmd = f"fslmaths {shlex.quote(registered_file)} -mul {shlex.quote(input1)} {shlex.quote(output_file)}"
                self.logger.info(f"Running fslmaths command: {multiply_cmd}")
                subprocess.run(multiply_cmd, shell=True, check=True)

                if not os.path.exists(output_file):
                    raise FileNotFoundError(f"Multiplication failed: {output_file} not created")
                self.logger.info(f"Multiplication successful, output saved to: {output_file}")

                self.logger.info("Processing completed successfully")
                return output_file

            except subprocess.CalledProcessError as e:
                self.logger.error(f"Command failed with error: {str(e)}")
                raise
            except Exception as e:
                self.logger.error(f"Error during processing: {str(e)}")
                raise