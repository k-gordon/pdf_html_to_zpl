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
    libjpeg62 \
    libxext6 \
    wget \
    xfonts-75dpi \
    xfonts-base \
    && rm -rf /var/lib/apt/lists/*

# Download and install wkhtmltopdf from official release
RUN wget https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.focal_amd64.deb \
    && dpkg -i wkhtmltox_0.12.6.1-2.focal_amd64.deb || true \
    && apt-get -f install -y \
    && rm wkhtmltox_0.12.6.1-2.focal_amd64.deb

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Command to run the application
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
