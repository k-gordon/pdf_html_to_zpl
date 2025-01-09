import os
import base64
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
from weasyprint import HTML
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
    width: float = Field(4.0, gt=0, description="Width in inches")
    height: float = Field(6.0, gt=0, description="Height in inches")
    scale: float = Field(1.0, gt=0, description="Scaling factor")
    invert: bool = Field(False, description="Invert black and white")
    dpi: int = Field(203, gt=0, description="DPI for conversion (default: 203 for Zebra printers)")


class Base64Request(BaseModel):
    file_content: str = Field(..., description="Base64 encoded file content")
    file_type: str = Field(..., description=f"File type ({', '.join(SUPPORTED_FILE_TYPES)})")
    options: Optional[ConversionOptions] = None


class HTMLRequest(BaseModel):
    html_content: str = Field(..., description="HTML content to convert")
    options: Optional[HTMLOptions] = None


class HTMLToZPL:
    def __init__(self, html_content, width=4.0, height=6.0, scale=1.0, format="ASCII", invert=False, dpi=203):
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
                    invert=not self.invert,
                    dither=True,
                    threshold=128,
                    dpi=self.dpi,
                    split_pages=False,
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


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
