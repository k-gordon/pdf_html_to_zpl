from pydantic import BaseModel, Field
from typing import Optional

class ConversionOptions(BaseModel):
    format: str = Field("Z64", description="ZPL format type (ASCII, B64, or Z64)")
    invert: bool = Field(True, description="Invert black and white")
    dither: bool = Field(False, description="Use dithering")
    threshold: int = Field(128, ge=0, le=255, description="Black pixel threshold (0-255)")
    dpi: int = Field(72, gt=0, description="PDF DPI (PDF only)")
    split_pages: bool = Field(True, description="Split PDF pages (PDF only)")

class HTMLOptions(BaseModel):
    format: str = Field("ASCII", description="ZPL format type (ASCII, B64, or Z64)")
    width: float = Field(4.0, gt=0, description="Width in inches")
    height: float = Field(6.0, gt=0, description="Height in inches")
    scale: float = Field(1.0, gt=0, description="Scaling factor")
    invert: bool = Field(False, description="Invert black and white")
    dpi: int = Field(203, gt=0, description="DPI for conversion (default: 203 for Zebra printers)")

# ... other models from main.py ...
