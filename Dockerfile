FROM ubuntu:20.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and Python
RUN apt-get update && apt-get install -y \
    software-properties-common \
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
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Make wkhtmltopdf executable
RUN chmod +x bin/wkhtmltopdf

# Command to run the application
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
