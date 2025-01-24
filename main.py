import os
import base64
import tempfile
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Tuple, Dict, Any
import uvicorn
import logging
from datetime import datetime
import json
from weasyprint import HTML
from zebrafy import ZebrafyPDF, ZebrafyZPL  # Update import
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pdfplumber
import io
import requests
from fastapi.responses import Response
import fitz  # PyMuPDF
import pyzbar.pyzbar as pyzbar
from PIL import Image
import numpy as np
from decimal import Decimal

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

# Add near the top with other globals
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# Clean up old temp files periodically
def cleanup_old_files(directory, max_age_seconds=3600):  # 1 hour
    current_time = datetime.now().timestamp()
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        try:
            if current_time - os.path.getctime(filepath) > max_age_seconds:
                os.unlink(filepath)
        except:
            pass

# FastAPI app initialization
app = FastAPI(
    title="ZPL Converter API",
    description="API for converting PDF, images and HTML to ZPL format. This API supports various options for conversion, including format type, inversion, dithering, and DPI settings.",
    version="1.1.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc UI
    openapi_url="/openapi.json"  # OpenAPI schema
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://*.render.com", "http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/temp", StaticFiles(directory=TEMP_DIR), name="temp")  # Serve temp directory
templates = Jinja2Templates(directory="templates")


class ConversionOptions(BaseModel):
    format: str = Field("Z64", description="ZPL format type (ASCII, B64, or Z64)")
    invert: bool = Field(True, description="Invert black and white")
    dither: bool = Field(False, description="Use dithering")
    threshold: int = Field(128, ge=0, le=255, description="Black pixel threshold (0-255)")
    dpi: int = Field(72, gt=0, description="PDF DPI (PDF only)")
    split_pages: bool = Field(True, description="Split PDF pages (PDF only)")

    class Config:
        json_schema_extra = {
            "example": {
                "format": "Z64",
                "invert": True,
                "dither": False,
                "threshold": 128,
                "dpi": 72,
                "split_pages": True
            }
        }


class HTMLOptions(BaseModel):
    format: str = Field("ASCII", description="ZPL format type (ASCII, B64, or Z64)")
    width: float = Field(4.0, gt=0, description="Width in inches")
    height: float = Field(6.0, gt=0, description="Height in inches")
    scale: float = Field(1.0, gt=0, description="Scaling factor")
    invert: bool = Field(False, description="Invert black and white")
    dpi: int = Field(203, gt=0, description="DPI for conversion (default: 203 for Zebra printers)")

    class Config:
        json_schema_extra = {
            "example": {
                "format": "ASCII",
                "width": 4.0,
                "height": 6.0,
                "scale": 1.0,
                "invert": False,
                "dpi": 203
            }
        }


class Base64Request(BaseModel):
    file_content: str = Field(..., description="Base64 encoded PDF content")
    options: Optional[ConversionOptions] = None

    class Config:
        json_schema_extra = {
            "example": {
                "file_content": "JVBERi0xLjQKJcfs... (base64 encoded PDF content)",
                "options": {
                    "format": "Z64",
                    "invert": True,
                    "dither": False,
                    "threshold": 128,
                    "dpi": 72,
                    "split_pages": True
                }
            }
        }


class HTMLRequest(BaseModel):
    html_content: str = Field(..., description="HTML content to convert")
    options: Optional[HTMLOptions] = None

    class Config:
        json_schema_extra = {
            "example": {
                "html_content": "<html><body><h1>Hello, World!</h1></body></html>",
                "options": {
                    "format": "ASCII",
                    "width": 4.0,
                    "height": 6.0,
                    "scale": 1.0,
                    "invert": False,
                    "dpi": 203
                }
            }
        }


class HTMLToZPL:
    def __init__(self, html_content, width=4.0, height=6.0, scale=1.0, format="Z64", invert=False, dpi=203):
        self.html_content = html_content
        self.width_inches = width
        self.height_inches = height
        self.scale = scale
        self.format = format
        self.invert = invert
        self.dpi = dpi

        self.width_dots = int(self.width_inches * self.dpi)
        self.height_dots = int(self.height_inches * self.dpi)

        self.width_mm = self.width_inches * 25.4
        self.height_mm = self.height_inches * 25.4

        self.html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @page {{
                    size: {self.width_mm}mm {self.height_mm}mm;
                    margin: 0;
                }}
                body {{
                    margin: 0;
                    padding: 0;
                    transform: scale({scale});
                    transform-origin: top left;
                    width: {self.width_mm}mm;
                    height: {self.height_mm}mm;
                    font-family: Arial, sans-serif;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """

    def to_zpl(self):
        try:
            # Generate a PDF using WeasyPrint
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
                HTML(string=self.html_content).write_pdf(tmp_pdf.name)

                # Read the PDF file
                with open(tmp_pdf.name, 'rb') as pdf_file:
                    pdf_content = pdf_file.read()

                # Convert PDF to ZPL using ZebrafyPDF
                converter = ZebrafyPDF(
                    pdf_content,
                    invert=self.invert,  # Correctly apply the invert option
                    dither=False,
                    threshold=128,
                    dpi=self.dpi,
                    split_pages=True,
                    format=self.format
                )

                zpl_output = converter.to_zpl()

                # Add page width and height ZPL commands
                zpl_lines = zpl_output.split('\n')
                if zpl_lines[0] == '^XA':
                    zpl_lines.insert(1, f'^PW{self.width_dots}^LL{self.height_dots}^LS0')

                return '\n'.join(zpl_lines)

        except Exception as e:
            raise Exception(f"HTML to ZPL conversion failed: {str(e)}")

        finally:
            # Cleanup temporary file
            try:
                os.unlink(tmp_pdf.name)
            except:
                pass


class ZPLGenerator:
    @staticmethod
    def convert_to_zpl_units(value_inches: float, dpi: int) -> int:
        """Convert from PDF points (1/72 inch) to ZPL dots"""
        return int((value_inches / 72.0) * dpi)

    @staticmethod
    def generate_text(text: str, x: float, y: float, font_size: float, dpi: int) -> str:
        # Convert positions from PDF points to ZPL dots
        x_dots = ZPLGenerator.convert_to_zpl_units(x, dpi)
        y_dots = ZPLGenerator.convert_to_zpl_units(y, dpi)
        
        # Map font size to ZPL size (PDF points to ZPL proportional sizing)
        font_height = min(max(int(font_size * 1.2), 9), 120)
        font_width = int(font_height * 0.8)
        
        return f"^FO{x_dots},{y_dots}^A0,{font_height},{font_width}^FD{text}^FS"

    @staticmethod
    def generate_barcode(barcode_type: str, data: str, x: float, y: float, width: float, height: float, dpi: int) -> str:
        x_dots = ZPLGenerator.convert_to_zpl_units(x, dpi)
        y_dots = ZPLGenerator.convert_to_zpl_units(y, dpi)
        width_dots = ZPLGenerator.convert_to_zpl_units(width, dpi)
        height_dots = ZPLGenerator.convert_to_zpl_units(height, dpi)
        
        zpl_barcode_map = {
            'CODE128': ('^BC', 2),
            'CODE39': ('^B3', 2),
            'QR_CODE': ('^BQ', 2),
            'EAN13': ('^BE', 3),
            'EAN8': ('^B8', 3),
        }
        
        barcode_cmd, module_width = zpl_barcode_map.get(barcode_type.upper(), ('^BC', 2))
        
        if barcode_type.upper() == 'QR_CODE':
            magnification = max(1, min(10, int(width_dots / 100)))  # Scale QR size appropriately
            return f"^FO{x_dots},{y_dots}{barcode_cmd},{magnification},M^FD{data}^FS"
        else:
            height = min(height_dots, 400)  # Max reasonable height for 1D barcodes
            return f"^FO{x_dots},{y_dots}{barcode_cmd},{height},{module_width},Y,N^FD{data}^FS"


class PDFAnalyzer:
    def __init__(self, pdf_content: bytes):
        self.pdf_content = pdf_content
        self.pdf = pdfplumber.open(io.BytesIO(pdf_content))
        self.doc = fitz.open(stream=pdf_content, filetype="pdf")

    def analyze_page(self, page_num: int = 0) -> Dict[str, Any]:
        """Analyze a single page of the PDF"""
        result = {
            'text_blocks': [],
            'images': [],
            'barcodes': [],
            'fonts': set(),
            'tables': [],
            'errors': []  # Add error tracking
        }

        try:
            # Get page
            page = self.pdf.pages[page_num]
            
            # Extract text with more detail using pdfplumber
            text_blocks = page.extract_words(
                keep_blank_chars=True,
                x_tolerance=3,
                y_tolerance=3,
                extra_attrs=['fontname', 'size']
            )

            # Process text blocks
            for block in text_blocks:
                try:
                    bbox = tuple(float(v) for v in (block['x0'], block['top'], block['x1'], block['bottom']))
                    result['text_blocks'].append({
                        'text': block['text'],
                        'bbox': bbox,
                        'font': block.get('fontname', 'default'),
                        'size': float(block.get('size', 12)),
                    })
                    if block.get('fontname'):
                        result['fonts'].add(block['fontname'])
                except (KeyError, ValueError) as e:
                    result['errors'].append(f"Error processing text block: {str(e)}")

            # Extract images and analyze for barcodes
            fitz_page = self.doc[page_num]
            for img_index, img in enumerate(fitz_page.get_images()):
                try:
                    xref = img[0]
                    base_image = self.doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    
                    with Image.open(io.BytesIO(image_bytes)) as image:
                        # Convert to grayscale for better barcode detection
                        if image.mode not in ('L', 'RGB'):
                            image = image.convert('RGB')
                        
                        try:
                            barcodes = pyzbar.decode(image)
                            position = self._get_image_position(fitz_page, xref)
                            
                            if barcodes and position:
                                for barcode in barcodes:
                                    doc_rect = self._calculate_barcode_position(
                                        barcode, position, image.size)
                                    if doc_rect:
                                        result['barcodes'].append({
                                            'type': barcode.type.decode() if isinstance(barcode.type, bytes) else barcode.type,
                                            'data': barcode.data.decode('utf-8'),
                                            'position': doc_rect
                                        })
                            else:
                                if position:
                                    result['images'].append({
                                        'index': img_index,
                                        'size': image.size,
                                        'format': base_image["ext"],
                                        'position': position
                                    })
                        except Exception as e:
                            result['errors'].append(f"Error processing barcode: {str(e)}")
                finally:
                    # Ensure image is closed
                    if 'image' in locals():
                        del image

        except Exception as e:
            result['errors'].append(f"Error analyzing page: {str(e)}")

        return result

    def _calculate_barcode_position(self, barcode, image_pos, image_size):
        """Calculate barcode position in document coordinates"""
        try:
            rect = barcode.rect
            scale_x = (image_pos['x1'] - image_pos['x0']) / image_size[0]
            scale_y = (image_pos['y1'] - image_pos['y0']) / image_size[1]
            
            return {
                'x0': float(image_pos['x0'] + rect.left * scale_x),
                'y0': float(image_pos['y0'] + rect.top * scale_y),
                'x1': float(image_pos['x0'] + (rect.left + rect.width) * scale_x),
                'y1': float(image_pos['y0'] + (rect.top + rect.height) * scale_y)
            }
        except Exception:
            return None

    def generate_zpl_elements(self, dpi: int, width: float, height: float) -> Tuple[str, List[Dict[str, Any]]]:
        """Generate ZPL commands for text and barcode elements"""
        zpl_elements = []
        embedded_images = []
        analysis = self.analyze_page(0)
        
        # Calculate scale factors
        page = self.pdf.pages[0]
        scale_x = width / float(page.width)
        scale_y = height / float(page.height)
        
        # Process text blocks
        for block in analysis['text_blocks']:
            try:
                x = block['bbox'][0] * scale_x * 72  # Convert to points
                y = block['bbox'][1] * scale_y * 72
                if not self._is_point_in_barcode((x, y), analysis.get('barcodes', [])):
                    zpl_elements.append(ZPLGenerator.generate_text(
                        block['text'],
                        x,
                        y,
                        float(block['size']) * min(scale_x, scale_y),  # Scale font size
                        dpi
                    ))
            except Exception as e:
                logger.warning(f"Failed to process text block: {e}")

        # Process barcodes
        for barcode in analysis.get('barcodes', []):
            try:
                pos = barcode['position']
                width = (pos['x1'] - pos['x0']) * scale_x * 72
                height = (pos['y1'] - pos['y0']) * scale_y * 72
                zpl_elements.append(ZPLGenerator.generate_barcode(
                    barcode['type'],
                    barcode['data'],
                    pos['x0'] * scale_x * 72,
                    pos['y0'] * scale_y * 72,
                    width,
                    height,
                    dpi
                ))
            except Exception as e:
                logger.warning(f"Failed to process barcode: {e}")

        # Process remaining images
        for img in analysis['images']:
            if img.get('position'):
                embedded_images.append(img)

        return '\n'.join(zpl_elements), embedded_images

    def _is_point_in_barcode(self, point, barcodes):
        """Check if a point falls within any barcode area"""
        if not barcodes:
            return False
            
        x, y = point
        for barcode in barcodes:
            pos = barcode.get('position', {})
            if not pos:
                continue
                
            x0 = pos.get('x0', 0)
            x1 = pos.get('x1', 0)
            y0 = pos.get('y0', 0)
            y1 = pos.get('y1', 0)
            
            if (x0 <= x <= x1 and y0 <= y <= y1):
                return True
        return False

    def _get_image_position(self, page, xref):
        """Get the position of an image on the page"""
        for block in page.get_text("dict", flags=11)["blocks"]:
            if "image" in block and block["image"]["xref"] == xref:
                return {
                    'x0': block['bbox'][0],
                    'y0': block['bbox'][1],
                    'x1': block['bbox'][2],
                    'y1': block['bbox'][3]
                }
        return None

    def close(self):
        """Close all open PDF handlers"""
        self.pdf.close()
        self.doc.close()


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode('utf-8')
    if hasattr(obj, '__dict__'):
        return obj.__dict__
    raise TypeError(f"Type {type(obj)} not serializable")


@app.get("/", summary="Main Page", description="Serve the main page with file upload form")
async def main_page(request: Request):
    """Serve the main page with file upload form"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload_pdf", summary="Convert PDF to ZPL", description="Handle PDF file upload and convert to ZPL",
          responses={
              200: {
                  "description": "Successful conversion",
                  "content": {
                      "application/json": {
                          "example": {
                              "status": "success",
                              "zpl_content": "^XA^FO50,50^ADN,36,20^FDZPL encoded image^FS^XZ",
                              "timestamp": "2023-10-01T12:00:00Z",
                              "preview_url": "/static/preview_1234567890.pdf",
                              "zpl_preview_url": "/temp/zpl_preview_1234567890.pdf"
                          }
                      }
                  }
              },
              400: {"description": "Invalid file type"},
              500: {"description": "Conversion failed"}
          })
async def upload_pdf(
    file: UploadFile = File(...),
    width: float = Form(None),
    height: float = Form(None),
    dpi: int = Form(203),
    format: str = Form("ASCII"),
    invert: bool = Form(False),
    dither: bool = Form(True),
    split_pages: bool = Form(True),
    scaling: str = Form("fit")
):
    """Handle PDF file upload and convert to ZPL"""
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are allowed.")

        # Read file content
        file_content = await file.read()

        # Add analysis before conversion
        analyzer = PDFAnalyzer(file_content)
        try:
            analysis = analyzer.analyze_page(0)
            
            # Generate ZPL elements and get list of images to process
            zpl_elements, embedded_images = analyzer.generate_zpl_elements(dpi, width, height)
            
            # Process only the embedded images
            if embedded_images:
                # Create a new PDF with only the embedded images
                image_pdf = await create_image_only_pdf(file_content, embedded_images, width, height, dpi)
                
                # Convert image content to ZPL
                converter = ZebrafyPDF(
                    image_pdf,
                    invert=invert,
                    dither=dither,
                    threshold=128,
                    dpi=dpi,
                    split_pages=split_pages,
                    format=format,
                    width=width_dots,
                    height=height_dots,
                    pos_x=0,
                    pos_y=0,
                    rotation=0,
                    complete_zpl=True,
                    string_line_break=None
                )
                base_zpl = converter.to_zpl()
            else:
                base_zpl = "^XA^FS"  # Empty label if no images

            # Combine elements
            zpl_lines = base_zpl.split('\n')
            if zpl_lines[0] == '^XA':
                zpl_lines.insert(1, f'^PW{width_dots}')
                zpl_lines.insert(2, f'^LL{height_dots}')
                zpl_lines.insert(3, '^LS0')
                # Add text and barcode elements after dimensions but before image
                for element in zpl_elements.split('\n'):
                    zpl_lines.insert(4, element)

            final_zpl = '\n'.join(zpl_lines)

            # Save scaled PDF for preview
            preview_path = f"static/preview_{datetime.now().timestamp()}.pdf"
            with open(preview_path, "wb") as f:
                f.write(scaled_content)

            # Generate ZPL preview PDF
            zpl_preview_path = f"temp/zpl_preview_{datetime.now().timestamp()}.pdf"
            zpl_converter = ZebrafyZPL(final_zpl)
            zpl_preview_data = zpl_converter.to_pdf()
            with open(zpl_preview_path, "wb") as f:
                f.write(zpl_preview_data)

            return JSONResponse(
                content=json.loads(
                    json.dumps({
                        "status": "success", 
                        "zpl_content": final_zpl,
                        "preview_url": f"/{preview_path}",  # Add preview URL to response
                        "zpl_preview_url": f"/{zpl_preview_path}",  # Add ZPL preview URL to response
                        "analysis": analysis,  # Include analysis in response
                        "timestamp": datetime.now().isoformat()
                    }, default=json_serial)
                )
            )
        finally:
            analyzer.close()

    except Exception as e:
        logger.error(f"PDF conversion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def scale_pdf(content: bytes, width: float, height: float, dpi: int, maintain_ratio: bool = True):
    """Pre-scale PDF content to match desired dimensions using PyMuPDF"""
    try:
        if not width or not height:
            return content

        # Load PDF from bytes
        doc = fitz.open(stream=content, filetype="pdf")
        page = doc[0]  # Get first page
        
        # Get original dimensions
        orig_width = page.rect.width
        orig_height = page.rect.height
        
        # Calculate target dimensions in points (72 points per inch)
        target_width = width * 72
        target_height = height * 72
        
        # Create new PDF with target dimensions
        new_doc = fitz.open()
        new_page = new_doc.new_page(width=target_width, height=target_height)
        
        if maintain_ratio:
            # Calculate scaling factors
            scale_x = target_width / orig_width
            scale_y = target_height / orig_height
            scale = min(scale_x, scale_y)
            
            # Calculate centering offsets
            x_offset = (target_width - (orig_width * scale)) / 2
            y_offset = (target_height - (orig_height * scale)) / 2
            
            # Create transform matrix with scaling and translation
            matrix = fitz.Matrix(scale, scale).pretranslate(x_offset, y_offset)
        else:
            # Non-uniform scaling
            matrix = fitz.Matrix(target_width/orig_width, target_height/orig_height)
        
        # Copy content with transformation
        new_page.show_pdf_page(new_page.rect, doc, 0, transform=matrix)
        
        # Get the result as bytes
        return new_doc.tobytes()

    except Exception as e:
        logger.error(f"PDF scaling failed: {str(e)}")
        # Return original content if scaling fails
        return content


@app.post("/convert/html", summary="Convert HTML to ZPL", description="Convert HTML content to ZPL",
          responses={
              200: {
                  "description": "Successful conversion",
                  "content": {
                      "application/json": {
                          "example": {
                              "status": "success",
                              "zpl_content": "^XA^FO50,50^ADN,36,20^FDZPL encoded image^FS^XZ",
                              "timestamp": "2023-10-01T12:00:00Z"
                          }
                      }
                  }
              },
              500: {"description": "Conversion failed"}
          })
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
            invert=options.invert,
            dpi=options.dpi
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


@app.post("/extract_pdf_metadata", summary="Extract PDF Metadata", description="Extract metadata from the first page of the PDF")
async def extract_pdf_metadata(file: UploadFile = File(...)):
    """Extract metadata from the first page of the PDF"""
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are allowed.")

        # Read file content
        file_content = await file.read()

        # Extract metadata using pdfplumber
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            first_page = pdf.pages[0]
            # Convert Decimal to float
            width_in_inches = float(first_page.width / 72)
            height_in_inches = float(first_page.height / 72)
            dpi = 72  # Assuming 72 DPI for PDF

        return JSONResponse(content={
            "width": width_in_inches,
            "height": height_in_inches,
            "dpi": dpi
        })
    except Exception as e:
        logger.error(f"PDF metadata extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/preview_zpl")
async def preview_zpl(
    zpl_content: str = Form(...),
    width: float = Form(4.0),
    height: float = Form(6.0),
    dpi: int = Form(203)
):
    """Generate preview PDF using zebrafy"""
    try:
        # Calculate dimensions in pixels
        width_pixels = int(width * dpi)
        height_pixels = int(height * dpi)

        # Add label dimensions to ZPL if needed
        zpl_lines = zpl_content.split('\n')
        if zpl_lines[0] == '^XA':
            zpl_lines.insert(1, f'^PW{width_pixels}^LL{height_pixels}^LS0')
        modified_zpl = '\n'.join(zpl_lines)  # Fix the string join syntax

        # Use ZebrafyZPL for PDF preview
        converter = ZebrafyZPL(modified_zpl)
        pdf_data = converter.to_pdf()

        return Response(
            content=pdf_data,
            media_type="application/pdf"
        )

    except Exception as e:
        logger.error(f"ZPL preview generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scale_pdf")
async def scale_pdf_endpoint(
    file: UploadFile = File(...),
    width: float = Form(None),
    height: float = Form(None),
    dpi: int = Form(203),
    scaling: str = Form("fit")
):
    """Scale PDF and return the scaled version"""
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are allowed.")

        file_content = await file.read()
        scaled_content = await scale_pdf(
            file_content, 
            width, 
            height, 
            dpi, 
            scaling == "fit"
        )

        # Generate unique filename with timestamp
        timestamp = int(datetime.now().timestamp() * 1000)  # millisecond precision
        filename = f"scaled_{timestamp}.pdf"
        filepath = os.path.join(TEMP_DIR, filename)
        
        # Save scaled content with cache-busting URL
        with open(filepath, "wb") as f:
            f.write(scaled_content)
        
        # Clean up old files
        cleanup_old_files(TEMP_DIR)

        # Return URL with cache-busting query parameter
        return Response(
            content=scaled_content,
            media_type="application/pdf",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )

    except Exception as e:
        logger.error(f"PDF scaling failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))  # Fix syntax error


@app.post("/analyze_pdf", summary="Analyze PDF Elements", 
          description="Extract text blocks, images, and barcodes from PDF")
async def analyze_pdf(
    file: UploadFile = File(...),
    page: int = Form(0)
):
    """Analyze PDF elements including text, images, and barcodes"""
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Invalid file type")

        content = await file.read()
        analyzer = PDFAnalyzer(content)
        
        try:
            result = analyzer.analyze_page(page)
            # Convert set to list for JSON serialization
            result['fonts'] = list(result['fonts'])
            return JSONResponse(
                content=json.loads(
                    json.dumps(result, default=json_serial)
                )
            )
        finally:
            analyzer.close()

    except Exception as e:
        logger.error(f"PDF analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))  # Fix syntax error


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

async def create_image_only_pdf(content: bytes, images: list, width: float, height: float, dpi: int) -> bytes:
    """Create a new PDF containing only the specified images"""
    doc = fitz.open(stream=content, filetype="pdf")
    new_doc = fitz.open()
    page = new_doc.new_page(width=width*72, height=height*72)
    
    for img in images:
        if img.get('position'):
            # Copy image to new position
            page.show_pdf_page(
                fitz.Rect(
                    img['position']['x0'],
                    img['position']['y0'],
                    img['position']['x1'],
                    img['position']['y1']
                ),
                doc,
                0
            )
    
    return new_doc.tobytes()
