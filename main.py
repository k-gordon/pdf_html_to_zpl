import os
from fastapi import FastAPI, HTTPException, File, UploadFile, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
import uvicorn
from bs4 import BeautifulSoup
import PyPDF2
from io import BytesIO
import re
import html
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get environment variables
MAX_UPLOAD_SIZE = int(os.getenv('MAX_UPLOAD_SIZE', 10 * 1024 * 1024))  # 10MB default

class DocumentToZPL:
    def __init__(self, options: Optional[Dict] = None):
        self.default_options = {
            'label_width': 4,
            'label_height': 6,
            'density': 8,
            'font_size': 10,
            'start_x': 50,
            'start_y': 50
        }
        self.options = {**self.default_options, **(options or {})}
        self.dpmm = self.options['density']
        self.dpi = self.dpmm * 25.4

    # [Previous DocumentToZPL methods go here]
    # Copy all the methods from the previous implementation

# FastAPI app initialization
app = FastAPI(
    title="ZPL Converter API",
    description="API for converting HTML and PDF documents to ZPL format",
    version="1.0.0"
)

# Add CORS middleware with more restrictive settings
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
    label_width: Optional[float] = Field(4.0, description="Label width in inches")
    label_height: Optional[float] = Field(6.0, description="Label height in inches")
    density: Optional[int] = Field(8, description="Printer density in dots/mm")
    font_size: Optional[int] = Field(10, description="Default font size")
    start_x: Optional[int] = Field(50, description="Starting X position")
    start_y: Optional[int] = Field(50, description="Starting Y position")

class HTMLRequest(BaseModel):
    html_content: str = Field(..., description="HTML content to convert")
    options: Optional[ConversionOptions] = None

class BarcodeRequest(BaseModel):
    data: str = Field(..., description="Data to encode in barcode")
    barcode_type: str = Field("CODE128", description="Type of barcode")
    x: Optional[int] = None
    y: Optional[int] = None
    options: Optional[ConversionOptions] = None

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

@app.post("/convert/html")
async def convert_html(request: HTMLRequest):
    """Convert HTML to ZPL format"""
    try:
        logger.info("Processing HTML to ZPL conversion request")
        converter = DocumentToZPL(request.options.dict() if request.options else None)
        zpl_output = converter.html_to_zpl(request.html_content)
        
        return {
            "status": "success",
            "zpl_content": zpl_output,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in HTML conversion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/convert/pdf")
async def convert_pdf(
    file: UploadFile = File(...),
    options: Optional[Dict] = Body(None)
):
    """Convert PDF to ZPL format"""
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        logger.info(f"Processing PDF to ZPL conversion request for file: {file.filename}")
        contents = await file.read()
        
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large")
            
        converter = DocumentToZPL(options)
        zpl_output = converter.pdf_to_zpl(BytesIO(contents))
        
        return {
            "status": "success",
            "zpl_content": zpl_output,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in PDF conversion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate/barcode")
async def generate_barcode(request: BarcodeRequest):
    """Generate ZPL barcode"""
    try:
        logger.info("Processing barcode generation request")
        converter = DocumentToZPL(request.options.dict() if request.options else None)
        zpl_output = converter.add_barcode(
            data=request.data,
            barcode_type=request.barcode_type,
            x=request.x,
            y=request.y
        )
        
        return {
            "status": "success",
            "zpl_content": zpl_output,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in barcode generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)