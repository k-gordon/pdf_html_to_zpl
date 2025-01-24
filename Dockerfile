FROM ubuntu:22.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/usr/local/bin:${PATH}"
ENV PORT=8000

# Install system dependencies and Python in a single layer
RUN apt-get update && apt-get install -y \
    wget \
    build-essential \
    python3 \
    python3-venv \
    python3-dev \
    python3-pip \
    libcairo2 \
    libpango1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    zbar-tools \
    libzbar0 \
    libzbar-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN python3 -m pip install --upgrade pip

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . ./

# Command to run the application
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
