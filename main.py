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
        "https://*.render.com",  
        "http://localhost:3000",  
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
    rotation: int = Field(0, description="Rotation (0, 90, 180, or 270)")
    string_line_break: Optional[int] = Field(None, description="Characters per line")
    complete_zpl: bool = Field(True, description="Include ZPL header/footer")
    dpi: int = Field(72, description="PDF DPI (PDF only)")
    split_pages: bool = Field(False, description="Split PDF pages (PDF only)")

class Base64Request(BaseModel):
    file_content: str = Field(..., description="Base64 encoded file content")
    file_type: str = Field(..., description="File type (pdf or image)")
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
            
        # Convert based on file type
        try:
            if request.file_type.lower() == 'pdf':
                converter = ZebrafyPDF(
                    file_content,
                    invert=request.options.invert if request.options else False,
                    dither=request.options.dither if request.options else True,
                    threshold=request.options.threshold if request.options else 128,
                    width=request.options.width if request.options else 0,
                    height=request.options.height if request.options else 0,
                    pos_x=request.options.pos_x if request.options else 0,
                    pos_y=request.options.pos_y if request.options else 0,
                    rotation=request.options.rotation if request.options else 0,
                    dpi=request.options.dpi if request.options else 72,
                    split_pages=request.options.split_pages if request.options else False
                )
            elif request.file_type.lower() in ['image', 'png', 'jpg', 'jpeg']:
                converter = ZebrafyImage(
                    file_content,
                    invert=request.options.invert if request.options else False,
                    dither=request.options.dither if request.options else True,
                    threshold=request.options.threshold if request.options else 128,
                    width=request.options.width if request.options else 0,
                    height=request.options.height if request.options else 0,
                    pos_x=request.options.pos_x if request.options else 0,
                    pos_y=request.options.pos_y if request.options else 0,
                    rotation=request.options.rotation if request.options else 0
                )
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type")
                
            zpl_format = request.options.format if request.options else "ASCII"
            zpl_output = converter.to_zpl(format=zpl_format)
            
            return {
                "status": "success",
                "zpl_content": zpl_output,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Conversion error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
            
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
        if options:
            try:
                options_dict = json.loads(options)
                logger.info(f"Using conversion options: {options_dict}")
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid options format")
        else:
            options_dict = {}
            
        # Convert based on file type
        try:
            if file_ext == 'pdf':
                converter = ZebrafyPDF(
                    contents,
                    invert=options_dict.get('invert', False),
                    dither=options_dict.get('dither', True),
                    threshold=options_dict.get('threshold', 128),
                    width=options_dict.get('width', 0),
                    height=options_dict.get('height', 0),
                    pos_x=options_dict.get('pos_x', 0),
                    pos_y=options_dict.get('pos_y', 0),
                    rotation=options_dict.get('rotation', 0),
                    dpi=options_dict.get('dpi', 72),
                    split_pages=options_dict.get('split_pages', False)
                )
            else:
                converter = ZebrafyImage(
                    contents,
                    invert=options_dict.get('invert', False),
                    dither=options_dict.get('dither', True),
                    threshold=options_dict.get('threshold', 128),
                    width=options_dict.get('width', 0),
                    height=options_dict.get('height', 0),
                    pos_x=options_dict.get('pos_x', 0),
                    pos_y=options_dict.get('pos_y', 0),
                    rotation=options_dict.get('rotation', 0)
                )
                
            zpl_format = options_dict.get('format', 'ASCII')
            zpl_output = converter.to_zpl(format=zpl_format)
            
            return {
                "status": "success",
                "zpl_content": zpl_output,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Conversion error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
            
    except Exception as e:
        logger.error(f"Error in conversion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
