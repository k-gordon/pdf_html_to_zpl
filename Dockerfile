FROM python:3.9-slim-buster

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libssl1.1 \
        libxrender1 \
        fontconfig \
        libjpeg62-turbo \
        libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Make wkhtmltopdf executable
RUN chmod +x bin/wkhtmltopdf

# Command to run the application
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
