FROM python:3.9-slim-buster

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wkhtmltopdf \
    xvfb \
    libssl1.1 \
    libxrender1 \
    fontconfig \
    libjpeg62 \
    libxext6 \
    xfonts-75dpi \
    xfonts-base \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Command to run the application
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
