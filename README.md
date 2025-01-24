# ZPL Converter API

This repository contains a FastAPI-based application for converting PDF, images, and HTML to ZPL format.

## Features

- Convert PDF, PNG, JPG, JPEG, and HTML files to ZPL format.
- Supports ASCII, B64, and Z64 ZPL formats.
- Options to invert colors, use dithering, and set DPI.
- Split PDF pages into separate ZPL files.

## Requirements

- Docker

## Docker Setup

### Build the Docker Image

1. Clone the repository:

    ```sh
    git clone <repository-url>
    cd <repository-directory>
    ```

2. Build the Docker image:

    ```sh
    docker build -t zpl-converter-api .
    ```

### Run the Docker Container

1. Run the Docker container:

    ```sh
    docker run -p 8000:8000 zpl-converter-api
    ```

2. The application will be accessible at `http://localhost:8000`.

## API Documentation

Swagger UI is available at `http://localhost:8000/docs`.

## API Endpoints

### Convert HTML to ZPL

- **URL:** `/convert/html`
- **Method:** `POST`
- **Request Body:**

    ```json
    {
        "html_content": "<html>Your HTML content here</html>",
        "options": {
            "format": "ASCII",
            "width": 4.0,
            "height": 6.0,
            "scale": 1.0,
            "invert": false,
            "dpi": 203
        }
    }
    ```

- **Response:**

    ```json
    {
        "status": "success",
        "zpl_content": "^XA^FO50,50^ADN,36,20^FDZPL encoded image^FS^XZ",
        "timestamp": "2023-10-01T12:00:00Z"
    }
    ```

### Convert PDF to ZPL

- **URL:** `/upload_pdf`
- **Method:** `POST`
- **Request Body:**

    ```json
    {
        "file_content": "base64_encoded_pdf_content",
        "options": {
            "format": "ASCII",
            "invert": false,
            "dither": true,
            "threshold": 128,
            "dpi": 203,
            "split_pages": true
        }
    }
    ```

- **Response:**

    ```json
    {
        "status": "success",
        "zpl_content": "^XA^FO50,50^ADN,36,20^FDZPL encoded image^FS^XZ",
        "timestamp": "2023-10-01T12:00:00Z"
    }
    ```

## Environment Variables

- `MAX_UPLOAD_SIZE`: Maximum upload size in bytes (default: 10MB).
- `PORT`: Port to run the application (default: 8000).

## Deployment

This application can be deployed using Render. The configuration is provided in the [`render.yaml`](render.yaml) file.

## License

This project is licensed under the MIT License.
