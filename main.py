import os
import base64
import pdfkit
import tempfile
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
SUPPORTED_FILE_TYPES = ["pdf", "png", "jpg", "jpeg", "html"]

# FastAPI app initialization
app = FastAPI(
    title="ZPL Converter API",
    description="API for converting PDF, images and HTML to ZPL format",
    version="1.1.0"
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

class Base64Request(BaseModel):
    file_content: str = Field(..., description="Base64 encoded file content")
    file_type: str = Field(..., description=f"File type ({', '.join(SUPPORTED_FILE_TYPES)})")
    options: Optional[ConversionOptions] = None

class HTMLRequest(BaseModel):
    html_content: str = Field(..., description="HTML content to convert")
    options: Optional[HTMLOptions] = None

class HTMLToZPL:
    def __init__(self, html_content, width=400, height=300, scale=1.0, format="ASCII", invert=False):
        self.html_content = html_content
        self.width = width
        self.height = height
        self.scale = scale
        self.format = format
        self.invert = invert
        
        # wkhtmltopdf options
        self.options = {
            'page-width': f'{width * scale}mm',
            'page-height': f'{height * scale}mm',
            'margin-top': '0',
            'margin-right': '0',
            'margin-bottom': '0',
            'margin-left': '0',
            'disable-smart-shrinking': '',
            'zoom': '1.0'
        }

    def to_zpl(self):
        try:
            # Create a temporary file for the PDF
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
                # Set path to wkhtmltopdf binary
                config = pdfkit.configuration(wkhtmltopdf='./bin/wkhtmltopdf')
                
                # Convert HTML to PDF
                pdfkit.from_string(
                    self.html_content,
                    tmp_pdf.name,
                    options=self.options,
                    configuration=config
                )
                
                # Read the PDF file
                with open(tmp_pdf.name, 'rb') as pdf_file:
                    pdf_content = pdf_file.read()
                
                # Convert PDF to ZPL using existing ZebrafyPDF
                converter = ZebrafyPDF(
                    pdf_content,
                    invert=not self.invert,  # Apply the invert fix
                    dither=True,
                    threshold=128,
                    dpi=203,  # Standard Zebra printer DPI
                    split_pages=False,
                    format=self.format
                )
                
                zpl_output = converter.to_zpl()
                
                return zpl_output
                
        except Exception as e:
            raise Exception(f"HTML to ZPL conversion failed: {str(e)}")
            
        finally:
            # Cleanup temporary file
            try:
                os.unlink(tmp_pdf.name)
            except:
                pass

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
                invert=not options.invert,
                dither=options.dither,
                threshold=options.threshold,
                dpi=options.dpi,
                split_pages=options.split_pages,
                format=options.format
            )
        else:
            converter = ZebrafyImage(
                file_content,
                invert=not options.invert,
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
                invert=not options.invert,
                dither=options.dither,
                threshold=options.threshold,
                dpi=options.dpi,
                split_pages=options.split_pages,
                format=options.format
            )
        else:
            converter = ZebrafyImage(
                contents,
                invert=not options.invert,
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
        
        converter = HTMLToZPL(
            request.html_content,
            width=options.width,
            height=options.height,
            scale=options.scale,
            format=options.format,
            invert=options.invert
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

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)