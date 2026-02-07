"""
Barcode Generation Service
"""
import barcode
from barcode.writer import ImageWriter
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def generate_barcode(barcode_number: str, output_dir: Path) -> str:
    """
    Generate a barcode image for the given barcode number.
    
    Args:
        barcode_number: The barcode number to encode
        output_dir: Directory to save the barcode image
        
    Returns:
        str: Full path to the generated barcode image
    """
    try:
        writer_options = {
            'module_width': 0.4,
            'module_height': 20.0,
            'quiet_zone': 6.5,
            'font_size': 14,
            'text_distance': 5,
            'dpi': 300,
            'write_text': True,
        }
        
        writer = ImageWriter()
        barcode_class = barcode.get_barcode_class('code128')
        barcode_instance = barcode_class(barcode_number, writer=writer)
        
        barcode_path = output_dir / f"barcode_{barcode_number}"
        barcode_instance.save(str(barcode_path), options=writer_options)
        
        full_path = output_dir / f"barcode_{barcode_number}.png"
        logger.info(f"Barcode generated: {full_path}")
        return str(full_path)
        
    except Exception as e:
        logger.error(f"Barcode generation failed: {e}")
        return ""