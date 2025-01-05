import os
import base64
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import uvicorn
import logging
from datetime import datetime
import json
from zebrafy import ZebrafyPDF, ZebrafyImage

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get environment variables
MAX_UPLOAD_SIZE = int(os.getenv('MAX_UPLOAD_SIZE', 10 * 1024 * 1024))  # 10MB default

# Supported file types
SUPPORTED_FILE_TYPES = ["pdf", "png", "jpg", "jpeg"]

# FastAPI app initialization
app = FastAPI(
    title="ZPL Converter API",
    description="API for converting PDF and image files to ZPL format using Zebrafy",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://*.render.com", "http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConversionOptions(BaseModel):
    format: str = Field("ASCII", description="ZPL format type (ASCII, B64, or Z64)")
    invert: bool = Field(False, description="Invert black and white")
    dither: bool = Field(True, description="Use dithering")
    threshold: int = Field(128, ge=0, le=255, description="Black pixel threshold (0-255)")
    dpi: int = Field(72, gt=0, description="PDF DPI (PDF only)")
    split_pages: bool = Field(False, description="Split PDF pages (PDF only)")

class Base64Request(BaseModel):
    file_content: str = Field(..., description="Base64 encoded file content")
    file_type: str = Field(..., description=f"File type ({', '.join(SUPPORTED_FILE_TYPES)})")
    options: Optional[ConversionOptions] = None

@app.post("/convert/base64")
async def convert_base64(request: Base64Request):
    """Convert base64 encoded PDF or image to ZPL"""
    logger.info(f"Received request to convert base64 {request.file_type} to ZPL.")
    try:
        # Validate file type
        if request.file_type.lower() not in SUPPORTED_FILE_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {request.file_type}")

        # Decode base64 content
        try:
            file_content = base64.b64decode(request.file_content)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 content")

        # Perform the conversion
        options = request.options or ConversionOptions()

        if request.file_type.lower() == "pdf":
            converter = ZebrafyPDF(
                file_content,
                invert= not options.invert,
                dither=options.dither,
                threshold=options.threshold,
                dpi=options.dpi,
                split_pages=options.split_pages,
                format=options.format
            )
        else:
            converter = ZebrafyImage(
                file_content,
                invert= not options.invert,
                dither=options.dither,
                threshold=options.threshold
            )

        zpl_output = converter.to_zpl()

        return {"status": "success", "zpl_content": zpl_output, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Conversion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/convert/file")
async def convert_file(file: UploadFile = File(...), options: str = Form(None)):
    """Convert uploaded file (PDF or image) to ZPL"""
    logger.info(f"Received file {file.filename} for conversion.")
    try:
        # Check file size
        contents = await file.read()
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large")

        # Validate file extension
        file_ext = file.filename.rsplit('.', 1)[-1].lower()
        if file_ext not in SUPPORTED_FILE_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

        # Parse options
        options_dict = json.loads(options) if options else {}
        options = ConversionOptions(**options_dict)

        # Perform the conversion
        if file_ext == "pdf":
            converter = ZebrafyPDF(
                contents,
                invert= not options.invert,
                dither=options.dither,
                threshold=options.threshold,
                dpi=options.dpi,
                split_pages=options.split_pages,
                format=options.format
            )
        else:
            converter = ZebrafyImage(
                contents,
                invert= not options.invert,
                dither=options.dither,
                threshold=options.threshold
            )

        zpl_output = converter.to_zpl()

        return {"status": "success", "zpl_content": zpl_output, "timestamp": datetime.now().isoformat()}
    except json.JSONDecodeError:
        logger.error("Invalid JSON in options.")
        raise HTTPException(status_code=400, detail="Invalid options format")
    except Exception as e:
        logger.error(f"Conversion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
