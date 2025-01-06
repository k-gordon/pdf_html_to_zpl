class HTMLToZPL:
    def __init__(self, html_content, width=4.0, height=6.0, scale=1.0, format="ASCII", invert=False, dpi=203):
        self.html_content = html_content
        # Store original dimensions
        self.width_inches = float(width)
        self.height_inches = float(height)
        self.scale = float(scale)
        self.format = format
        self.invert = invert
        self.dpi = int(dpi)
        
        # Calculate dimensions in dots
        self.width_dots = int(self.width_inches * self.dpi)
        self.height_dots = int(self.height_inches * self.dpi)
        
        # Convert to mm for wkhtmltopdf (1 inch = 25.4 mm)
        self.width_mm = self.width_inches * 25.4
        self.height_mm = self.height_inches * 25.4
        
        # wkhtmltopdf options - using only supported options
        self.options = {
            'page-width': f'{self.width_mm}mm',
            'page-height': f'{self.height_mm}mm',
            'margin-top': '0',
            'margin-right': '0',
            'margin-bottom': '0',
            'margin-left': '0',
            'dpi': str(self.dpi)
        }

        # Add HTML wrapper with size constraints
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
                    width: {self.width_dots}px;
                    height: {self.height_dots}px;
                    overflow: hidden;
                    font-family: Arial, Helvetica, sans-serif;
                }}
                h1 {{
                    font-size: {int(self.dpi/3)}px;
                    font-weight: 900;
                    line-height: 1.2;
                    margin: {int(self.dpi/10)}px 0;
                    padding: 0;
                    letter-spacing: 1px;
                }}
                p {{
                    font-size: {int(self.dpi/4)}px;
                    line-height: 1.4;
                    margin: {int(self.dpi/12)}px 0;
                    padding: 0;
                    font-weight: 500;
                }}
            </style>
        </head>
        <body>
            <div style="transform: scale({scale}); transform-origin: top left;">
                {html_content}
            </div>
        </body>
        </html>
        """

    def to_zpl(self):
        try:
            # Create a temporary file for the PDF
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
                # Set path to wkhtmltopdf binary
                config = pdfkit.configuration(wkhtmltopdf='/usr/bin/wkhtmltopdf')
                
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
                
                # Modify ZPL output to include proper dimensions
                zpl_lines = zpl_output.split('\n')
                if zpl_lines[0] == '^XA':
                    # Insert dimension commands after ^XA
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
