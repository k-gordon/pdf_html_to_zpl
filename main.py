import os
from fastapi import FastAPI, HTTPException, File, UploadFile, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Union
import uvicorn
from bs4 import BeautifulSoup
import PyPDF2
from io import BytesIO
import re
import html
import logging
from datetime import datetime
import json
from fastapi import Form

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

    def pixels_to_dots(self, pixels: float) -> int:
        """Convert pixels to printer dots based on density."""
        return round((pixels / 96) * self.dpi)

    def escape_zpl(self, text: str) -> str:
        """Escape special characters in ZPL."""
        text = html.unescape(text)
        escapes = {
            '\\': '\\\\',
            '^': '\\^',
            '~': '\\~',
            ',': '\\,',
            ':': '\\:',
            '"': '\\"'
        }
        for char, escape in escapes.items():
            text = text.replace(char, escape)
        return text

    def html_to_zpl(self, html_content: str) -> str:
        """Convert HTML content to ZPL format."""
        zpl = ['^XA']  # Start ZPL format
        current_y = self.options['start_y']
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Process text elements
        for element in soup.find_all(text=True):
            if element.strip():
                # Get parent tag for styling
                parent = element.parent
                
                # Determine font size based on tag
                font_size = self.options['font_size']
                if parent.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    # Scale font size based on heading level
                    heading_level = int(parent.name[1])
                    font_size = int(font_size * (2.0 - (heading_level * 0.2)))
                
                # Convert font size to dots
                font_size_dots = self.pixels_to_dots(font_size)
                
                # Determine if bold
                is_bold = parent.name in ['strong', 'b'] or parent.get('style', '').find('font-weight: bold') != -1
                
                # Add text field
                zpl.extend([
                    f'^FO{self.options["start_x"]},{current_y}',  # Field Origin
                    f'^A0,{font_size_dots}',  # Font selection
                    '^FB' if is_bold else '',  # Bold text if needed
                    f'^FD{self.escape_zpl(element.string.strip())}^FS'  # Field Data and Separator
                ])
                
                # Update vertical position
                current_y += int(font_size_dots * 1.5)  # Add line spacing
        
        zpl.append('^XZ')  # End ZPL format
        return '\n'.join(filter(None, zpl))

    def pdf_to_zpl(self, pdf_data: Union[str, bytes, BytesIO]) -> str:
        """
        Convert PDF content to ZPL format with table and formatting preservation.
        """
        zpl = ['^XA']  # Start ZPL format
        current_y = self.options['start_y']
        table_border = True  # Enable table borders
        
        try:
            # Handle different input types
            if isinstance(pdf_data, str):
                pdf_file = open(pdf_data, 'rb')
            elif isinstance(pdf_data, bytes):
                pdf_file = BytesIO(pdf_data)
            elif isinstance(pdf_data, BytesIO):
                pdf_file = pdf_data
            else:
                raise ValueError("Unsupported PDF input type")
            
            # Read PDF
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            # Process each page
            for page_num, page in enumerate(pdf_reader.pages):
                if page_num > 0:
                    # Add page separator
                    current_y += self.pixels_to_dots(20)  # Add space between pages
                
                # Get page layout
                layout = page.extract_text(layout=True)
                
                # Process tables if present
                tables = page.find_tables()
                if tables:
                    for table in tables:
                        # Table header
                        if table_border:
                            zpl.extend([
                                f'^FO{self.options["start_x"]},{current_y}',
                                '^GB750,2,2^FS'  # Horizontal line
                            ])
                        
                        current_y += self.pixels_to_dots(5)
                        
                        # Process table headers
                        col_widths = table.column_widths()
                        x_pos = self.options["start_x"]
                        
                        for col_num, header in enumerate(table.headers):
                            width = self.pixels_to_dots(col_widths[col_num])
                            zpl.extend([
                                f'^FO{x_pos},{current_y}',
                                f'^A0,{self.pixels_to_dots(10)}',  # Slightly larger font for headers
                                '^FB' if table_border else '',  # Bold for headers
                                f'^FD{self.escape_zpl(header.strip())}^FS'
                            ])
                            x_pos += width + self.pixels_to_dots(10)  # Add padding
                        
                        current_y += self.pixels_to_dots(15)
                        
                        # Table rows
                        for row in table.rows:
                            x_pos = self.options["start_x"]
                            max_height = 0
                            
                            for col_num, cell in enumerate(row):
                                width = self.pixels_to_dots(col_widths[col_num])
                                cell_text = cell.strip()
                                
                                # Handle multi-line cells
                                lines = cell_text.split('\n')
                                line_height = self.pixels_to_dots(10)  # Base height for text
                                total_height = line_height * len(lines)
                                max_height = max(max_height, total_height)
                                
                                for line in lines:
                                    zpl.extend([
                                        f'^FO{x_pos},{current_y}',
                                        f'^A0,{self.pixels_to_dots(8)}',  # Normal font size for cell content
                                        f'^FB{width},{len(lines)},0,L,0',  # Field block for text wrapping
                                        f'^FD{self.escape_zpl(line)}^FS'
                                    ])
                                    current_y += line_height
                                
                                current_y -= total_height  # Reset Y position for next cell
                                x_pos += width + self.pixels_to_dots(10)  # Add padding
                            
                            current_y += max_height + self.pixels_to_dots(5)  # Move to next row
                            
                            # Add row separator
                            if table_border:
                                zpl.extend([
                                    f'^FO{self.options["start_x"]},{current_y}',
                                    '^GB750,1,1^FS'  # Thinner horizontal line for row separator
                                ])
                        
                        current_y += self.pixels_to_dots(10)  # Space after table
                
                # Process regular text with formatting
                for text_obj in layout:
                    if isinstance(text_obj, str) and text_obj.strip():
                        # Detect formatting
                        font_size = text_obj.font.size if hasattr(text_obj, 'font') else self.options['font_size']
                        is_bold = text_obj.font.is_bold if hasattr(text_obj, 'font') else False
                        
                        # Convert formatting to ZPL
                        font_size_dots = self.pixels_to_dots(font_size)
                        
                        zpl.extend([
                            f'^FO{self.options["start_x"]},{current_y}',
                            f'^A0,{font_size_dots}',
                            '^FB' if is_bold else '',
                            f'^FD{self.escape_zpl(text_obj.strip())}^FS'
                        ])
                        
                        current_y += int(font_size_dots * 1.5)  # Add line spacing
            
            if isinstance(pdf_data, str):
                pdf_file.close()
                
        except Exception as e:
            raise Exception(f"Error converting PDF to ZPL: {str(e)}")
        
        zpl.append('^XZ')  # End ZPL format
        return '\n'.join(filter(None, zpl))

    def add_barcode(self, data: str, barcode_type: str = "CODE128", x: Optional[int] = None, y: Optional[int] = None) -> str:
        """Generate ZPL barcode."""
        x = x if x is not None else self.options['start_x']
        y = y if y is not None else self.options['start_y']
        
        barcode_commands = {
            'CODE128': '^BC',
            'CODE39': '^B3',
            'QR': '^BQ',
            'EAN13': '^BE',
            'UPC': '^BU'
        }
        
        command = barcode_commands.get(barcode_type.upper(), '^BC')
        
        return f'^XA\n^FO{x},{y}\n{command}\n^FD{self.escape_zpl(data)}^FS\n^XZ'

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
    options: str = Form(None)  # Changed from Body to Form, and type to str
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
