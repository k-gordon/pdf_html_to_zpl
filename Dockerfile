FROM ubuntu:20.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/usr/local/bin:${PATH}"

# Install system dependencies and Python
RUN apt-get update && apt-get install -y \
    software-properties-common \
    wget \
    build-essential \
    python3.9 \
    python3-pip \
    python3.9-venv \
    libcairo2 \
    libpango1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Debugging: Ensure Python is installed and accessible
RUN python3 --version && pip3 --version

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . ./

# Command to run the application
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
