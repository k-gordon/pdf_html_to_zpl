import os
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Union
import uvicorn
from bs4 import BeautifulSoup
from io import BytesIO
import html
import logging
from datetime import datetime
import json
from PIL import Image
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextBox, LTText, LTChar, LTAnno
import zpl

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
            'label_width': 100,  # mm
            'label_height': 60,  # mm
            'char_height': 10,   # Default character height
            'char_width': 8,     # Default character width
            'line_width': 60,    # Default line width
            'justification': 'L'  # L, C, R for Left, Center, Right
        }
        self.options = {**self.default_options, **(options or {})}
        
    def html_to_zpl(self, html_content: str) -> str:
        """Convert HTML content to ZPL format"""
        # Create a new label with specified dimensions
        label = zpl.Label(self.options['label_width'], self.options['label_height'])
        current_height = 0
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Process text elements
        for element in soup.find_all(text=True):
            if element.strip():
                parent = element.parent
                char_height, char_width = self._get_text_dimensions(parent)
                justification = self._get_justification(parent)
                
                # Add text to label
                label.origin(0, current_height)
                label.write_text(
                    element.strip(),
                    char_height=char_height,
                    char_width=char_width,
                    line_width=self.options['line_width'],
                    justification=justification
                )
                label.endorigin()
                
                # Update height for next element
                current_height += char_height + 2  # Add some spacing
        
        return label.dumpZPL()

    def pdf_to_zpl(self, pdf_data: Union[str, bytes, BytesIO]) -> str:
        """Convert PDF to ZPL format with layout preservation"""
        try:
            # Create a new label
            label = zpl.Label(self.options['label_width'], self.options['label_height'])
            current_height = 0
            
            # Create a temporary file if needed
            if isinstance(pdf_data, (bytes, BytesIO)):
                temp_file = BytesIO(pdf_data if isinstance(pdf_data, bytes) else pdf_data.getvalue())
            else:
                temp_file = pdf_data

            # Extract pages with layout
            for page_layout in extract_pages(temp_file):
                for element in page_layout:
                    if isinstance(element, LTTextBox):
                        text = element.get_text().strip()
                        if not text:
                            continue
                        
                        # Calculate relative position
                        x_pos = int(element.x0 * self.options['label_width'] / page_layout.width)
                        y_pos = current_height + int(element.y0 * self.options['label_height'] / page_layout.height)
                        
                        # Get font properties
                        char_height = int(element.height * 10 / page_layout.height)
                        char_width = int(char_height * 0.8)  # Approximate width
                        
                        # Add text to label
                        label.origin(x_pos, y_pos)
                        label.write_text(
                            text,
                            char_height=max(5, char_height),  # Ensure minimum size
                            char_width=max(4, char_width),
                            line_width=self.options['line_width']
                        )
                        label.endorigin()
                        
                        # Update height
                        current_height = max(current_height, y_pos + char_height + 5)
            
            return label.dumpZPL()
                
        except Exception as e:
            raise Exception(f"Error converting PDF to ZPL: {str(e)}")

    def add_barcode(self, data: str, barcode_type: str = "128", x: Optional[int] = None, y: Optional[int] = None) -> str:
        """Generate ZPL barcode"""
        # Create a new label
        label = zpl.Label(self.options['label_width'], self.options['label_height'])
        
        # Set position
        x = x if x is not None else 10
        y = y if y is not None else 10
        
        label.origin(x, y)
        
        # Map barcode types to zpl library format
        barcode_types = {
            'CODE128': '128',
            'CODE39': '3',
            'QR': 'Q',
            'EAN13': 'E',
            'UPC': 'U'
        }
        
        bc_type = barcode_types.get(barcode_type.upper(), '128')
        
        if bc_type == 'Q':  # QR Code
            label.barcode(bc_type, data, magnification=5)
        elif bc_type == 'U':  # UPC
            label.barcode(bc_type, data, height=70, check_digit='Y')
        else:  # Other barcodes
            label.barcode(bc_type, data, height=60)
            
        label.endorigin()
        
        return label.dumpZPL()

    def _get_text_dimensions(self, element) -> tuple:
        """Get text dimensions based on HTML element"""
        base_height = self.options['char_height']
        base_width = self.options['char_width']
        
        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            heading_level = int(element.name[1])
            multiplier = 2.5 - (heading_level * 0.3)
            return (int(base_height * multiplier), int(base_width * multiplier))
        return (base_height, base_width)

    def _get_justification(self, element) -> str:
        """Get text justification based on HTML element"""
        style = element.get('style', '')
        if 'text-align: center' in style:
            return 'C'
        elif 'text-align: right' in style:
            return 'R'
        return 'L'  # Default left alignment

# FastAPI app initialization
app = FastAPI(
    title="ZPL Converter API",
    description="API for converting HTML and PDF documents to ZPL format",
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
    label_width: Optional[float] = Field(100, description="Label width in mm")
    label_height: Optional[float] = Field(60, description="Label height in mm")
    char_height: Optional[int] = Field(10, description="Character height")
    char_width: Optional[int] = Field(8, description="Character width")
    line_width: Optional[int] = Field(60, description="Line width")
    justification: Optional[str] = Field('L', description="Text justification (L, C, R)")

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
    options: str = Form(None)
):
    """Convert PDF to ZPL format"""
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        logger.info(f"Processing PDF to ZPL conversion request for file: {file.filename}")
        contents = await file.read()
        
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large")
        
        # Parse options if provided
        options_dict = None
        if options:
            try:
                options_dict = json.loads(options)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid options format")
            
        converter = DocumentToZPL(options_dict)
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