import os
import base64
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict
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

# FastAPI app initialization
app = FastAPI(
    title="ZPL Converter API",
    description="API for converting HTML and PDF documents to ZPL format using Zebrafy",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://*.render.com",  # Allow Render domains
        "http://localhost:3000",  # Local development
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConversionOptions(BaseModel):
    format: str = Field("ASCII", description="ZPL format type (ASCII, B64, or Z64)")
    invert: bool = Field(False, description="Invert black and white")
    dither: bool = Field(True, description="Use dithering")
    threshold: int = Field(128, description="Black pixel threshold (0-255)")
    width: int = Field(0, description="Output width (0 for original)")
    height: int = Field(0, description="Output height (0 for original)")
    pos_x: int = Field(0, description="X position")
    pos_y: int = Field(0, description="Y position")
    dpi: int = Field(72, description="PDF DPI (PDF only)")
    split_pages: bool = Field(False, description="Split PDF pages (PDF only)")

class Base64Request(BaseModel):
    file_content: str = Field(..., description="Base64 encoded file content")
    file_type: str = Field(..., description="File type (pdf or image)")
    options: Optional[ConversionOptions] = None

VALID_ZEBRAFY_OPTIONS = {
    'format',
    'invert',
    'dither',
    'threshold',
    'width',
    'height',
    'dpi',
    'split_pages'
}

def clean_options(options: dict) -> dict:
    """Remove unsupported parameters and None values"""
    if not options:
        return {}
    
    # Only keep supported options and remove None values
    cleaned = {k: v for k, v in options.items() 
              if k in VALID_ZEBRAFY_OPTIONS and v is not None and v != ""}
    
    return cleaned

@app.middleware("http")
async def check_file_size(request, call_next):
    if request.method == "POST":
        if "content-length" in request.headers:
            content_length = int(request.headers["content-length"])
            if content_length > MAX_UPLOAD_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={
                        "status": "error",
                        "message": f"File size exceeds maximum limit of {MAX_UPLOAD_SIZE/1024/1024}MB",
                        "timestamp": datetime.now().isoformat()
                    }
                )
    response = await call_next(request)
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global error handler caught: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "ZPL Converter API",
        "version": "1.0.0",
        "status": "active",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/convert/base64")
async def convert_base64(request: Base64Request):
    """Convert base64 encoded PDF or image to ZPL"""
    try:
        logger.info(f"Processing {request.file_type} to ZPL conversion request")
        
        # Decode base64 content
        try:
            file_content = base64.b64decode(request.file_content)
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid base64 content")
            
        # Prepare options
        options = clean_options(request.options.dict()) if request.options else {}
        logger.info(f"Using conversion options: {options}")
        
        # Convert based on file type
        if request.file_type.lower() == 'pdf':
            converter = ZebrafyPDF(file_content, **options)
        elif request.file_type.lower() in ['image', 'png', 'jpg', 'jpeg']:
            converter = ZebrafyImage(file_content, **options)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
            
        zpl_output = converter.to_zpl()
        
        return {
            "status": "success",
            "zpl_content": zpl_output,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in conversion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/convert/file")
async def convert_file(
    file: UploadFile = File(...),
    options: str = Form(None)
):
    """Convert uploaded file (PDF or image) to ZPL"""
    try:
        # Check file type
        file_ext = file.filename.lower().split('.')[-1]
        if file_ext not in ['pdf', 'png', 'jpg', 'jpeg']:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        logger.info(f"Processing file to ZPL conversion request for file: {file.filename}")
        contents = await file.read()
        
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large")
        
        # Parse options if provided
        conv_options = {}
        if options:
            try:
                conv_options = json.loads(options)
                conv_options = clean_options(conv_options)
                logger.info(f"Using conversion options: {conv_options}")
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid options format")
            
        # Convert based on file type
        if file_ext == 'pdf':
            converter = ZebrafyPDF(contents, **conv_options)
        else:
            converter = ZebrafyImage(contents, **conv_options)
            
        zpl_output = converter.to_zpl()
        
        return {
            "status": "success",
            "zpl_content": zpl_output,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in conversion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
