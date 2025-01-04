import os
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Union
import uvicorn
from bs4 import BeautifulSoup
from io import BytesIO, StringIO
import html
import logging
from datetime import datetime
import json
from PIL import Image
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextBox, LTText, LTChar, LTAnno
from zpl2 import Label

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
            'label_width': 4,  # inches
            'label_height': 6,  # inches
            'density': 8,      # dots/mm (203 dpi)
            'font_size': 10,
            'start_x': 50,
            'start_y': 50,
            'rotation': 0,     # 0, 90, 180, or 270 degrees
        }
        self.options = {**self.default_options, **(options or {})}
        self.dpmm = self.options['density']
        self.dpi = self.dpmm * 25.4

    def html_to_zpl(self, html_content: str) -> str:
        """Convert HTML content to ZPL format"""
        zpl = Label(self.options['density'])
        current_y = self.options['start_y']
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Process text elements
        for element in soup.find_all(text=True):
            if element.strip():
                parent = element.parent
                font_size = self._get_font_size(parent)
                is_bold = self._is_bold(parent)
                
                # Add text field
                zpl.origin(self.options['start_x'], current_y)
                zpl.write_text(element.string.strip(), font_size, is_bold)
                
                current_y += int(font_size * 1.5)
        
        return str(zpl)

    def pdf_to_zpl(self, pdf_data: Union[str, bytes, BytesIO]) -> str:
        """Convert PDF to ZPL format with layout preservation"""
        try:
            # Create a Label instance
            label = Label(self.options['density'])
            current_y = self.options['start_y']
            
            # Create a temporary file if needed
            if isinstance(pdf_data, (bytes, BytesIO)):
                temp_file = BytesIO(pdf_data if isinstance(pdf_data, bytes) else pdf_data.getvalue())
            else:
                temp_file = pdf_data

            # Extract pages with layout
            for page_layout in extract_pages(temp_file):
                max_y = 0
                
                # Process each element in the page
                for element in page_layout:
                    if isinstance(element, LTTextBox):
                        # Get text and its properties
                        text = element.get_text().strip()
                        if not text:
                            continue
                            
                        # Calculate position
                        x = int(element.x0 * self.dpmm)
                        y = int(element.y0 * self.dpmm)
                        
                        # Get font properties
                        font_size = self.options['font_size']
                        is_bold = False
                        
                        for text_line in element:
                            if isinstance(text_line, LTText):
                                for character in text_line:
                                    if isinstance(character, LTChar):
                                        font_name = character.fontname
                                        font_size = int(character.size * self.dpmm)
                                        is_bold = 'Bold' in font_name or 'bold' in font_name
                                        break
                        
                        # Add text to label
                        label.origin(x + self.options['start_x'], y + self.options['start_y'])
                        label.write_text(text, font_size, is_bold)
                        
                        # Update maximum y position
                        max_y = max(max_y, y + self.options['start_y'] + font_size)
                
                # Add page separator if not the last page
                if max_y > current_y:
                    current_y = max_y + self.pixels_to_dots(20)
            
            return str(label)
                
        except Exception as e:
            raise Exception(f"Error converting PDF to ZPL: {str(e)}")

    def add_barcode(self, data: str, barcode_type: str = "CODE128", x: Optional[int] = None, y: Optional[int] = None) -> str:
        """Generate ZPL barcode"""
        x = x if x is not None else self.options['start_x']
        y = y if y is not None else self.options['start_y']
        
        label = Label(self.options['density'])
        label.origin(x, y)
        
        if barcode_type.upper() == 'QR':
            label.qr_code(data)
        elif barcode_type.upper() == 'CODE39':
            label.barcode('3', data)
        elif barcode_type.upper() == 'EAN13':
            label.barcode('E', data)
        elif barcode_type.upper() == 'UPC':
            label.barcode('U', data)
        else:  # Default to CODE128
            label.barcode('B', data)
        
        return str(label)

    def _get_font_size(self, element) -> int:
        """Get font size based on HTML element"""
        base_size = self.options['font_size']
        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            heading_level = int(element.name[1])
            return int(base_size * (2.5 - (heading_level * 0.2)))
        return base_size

    def _is_bold(self, element) -> bool:
        """Check if element should be bold"""
        return element.name in ['strong', 'b'] or 'font-weight: bold' in element.get('style', '')

    def pixels_to_dots(self, pixels: float) -> int:
        """Convert pixels to printer dots based on density."""
        return round((pixels / 96) * self.dpi)

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
