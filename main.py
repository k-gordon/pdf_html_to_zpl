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
# Supported barcode types - make sure these match your Zebrafy library capabilities
SUPPORTED_BARCODE_TYPES = [
    "code128",
    "code39", 
    "code93",
    "codabar",
    "ean8",
    "ean13",
    "upca",
    "upce",
    "qr",
    "datamatrix",
    "interleaved2of5",
    "industrial2of5"
]

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

class HTMLOptions(BaseModel):
    format: str = Field("ASCII", description="ZPL format type (ASCII, B64, or Z64)")
    width: int = Field(400, gt=0, description="Width in pixels")
    height: int = Field(300, gt=0, description="Height in pixels")
    scale: float = Field(1.0, gt=0, description="Scaling factor")
    invert: bool = Field(False, description="Invert black and white")

class BarcodeOptions(BaseModel):
    barcode_type: str = Field(..., description=f"Barcode type ({', '.join(SUPPORTED_BARCODE_TYPES)})")
    data: str = Field(..., description="Data to encode in barcode")
    width: Optional[int] = Field(2, gt=0, description="Barcode width")
    height: Optional[int] = Field(100, gt=0, description="Barcode height")
    show_text: Optional[bool] = Field(True, description="Show human-readable text")
    rotation: Optional[int] = Field(0, ge=0, le=270, description="Rotation angle (0, 90, 180, 270)")

class HTMLRequest(BaseModel):
    html_content: str = Field(..., description="HTML content to convert")
    options: Optional[HTMLOptions] = None

class BarcodeRequest(BaseModel):
    options: BarcodeOptions


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

@app.post("/convert/html")
async def convert_html(request: HTMLRequest):
    """Convert HTML content to ZPL"""
    logger.info("Received request to convert HTML to ZPL.")
    try:
        options = request.options or HTMLOptions()
        
        converter = ZebrafyHTML(
            request.html_content,
            width=options.width,
            height=options.height,
            scale=options.scale,
            invert=not options.invert,  # Apply the same invert fix
            format=options.format
        )

        zpl_output = converter.to_zpl()

        return {
            "status": "success",
            "zpl_content": zpl_output,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"HTML conversion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate/barcode")
async def generate_barcode(request: BarcodeRequest):
    """Generate barcode in ZPL format"""
    logger.info(f"Received request to generate {request.options.barcode_type} barcode.")
    try:
        if request.options.barcode_type.lower() not in SUPPORTED_BARCODE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported barcode type. Supported types: {', '.join(SUPPORTED_BARCODE_TYPES)}"
            )

        converter = ZebrafyBarcode(
            barcode_type=request.options.barcode_type,
            data=request.options.data,
            width=request.options.width,
            height=request.options.height,
            show_text=request.options.show_text,
            rotation=request.options.rotation
        )

        zpl_output = converter.to_zpl()

        return {
            "status": "success",
            "zpl_content": zpl_output,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Barcode generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
