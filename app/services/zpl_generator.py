
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