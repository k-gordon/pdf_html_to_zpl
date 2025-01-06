FROM ubuntu:20.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/usr/local/bin:${PATH}"

# Install system dependencies and Python
RUN apt-get update && apt-get install -y \
    software-properties-common \
    wget \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y \
    python3.9 \
    python3-pip \
    python3.9-venv \
    libssl1.1 \
    libxrender1 \
    fontconfig \
    libjpeg-turbo8 \
    libxext6 \
    xfonts-75dpi \
    xfonts-base \
    && wget https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox_0.12.6-1.focal_amd64.deb \
    && apt install -y ./wkhtmltox_0.12.6-1.focal_amd64.deb \
    && rm ./wkhtmltox_0.12.6-1.focal_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# Debugging: Ensure wkhtmltopdf is installed and accessible
RUN which wkhtmltopdf && wkhtmltopdf --version

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Command to run the application
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
