FROM ubuntu:20.04

# Avoid timezone prompt during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    wget \
    software-properties-common \
    dcm2niix \
    pigz \
    bc \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Download and run the FSL installer
RUN wget -O fslinstaller.py https://fsl.fmrib.ox.ac.uk/fsldownloads/fslinstaller.py && \
    python3 fslinstaller.py -d /usr/local/fsl && \
    rm fslinstaller.py

# Set up FSL environment variables
ENV FSLDIR=/usr/local/fsl
ENV PATH=$FSLDIR/bin:$PATH
ENV LD_LIBRARY_PATH=$FSLDIR/lib:$LD_LIBRARY_PATH
ENV FSLOUTPUTTYPE=NIFTI_GZ

# Create app directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Make the entrypoint script executable
RUN chmod +x docker-entrypoint.sh

# Set entrypoint script
ENTRYPOINT ["/app/docker-entrypoint.sh"]