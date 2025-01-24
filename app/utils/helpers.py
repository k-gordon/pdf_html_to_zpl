import json
from decimal import Decimal
import base64
from datetime import datetime
import os

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

def cleanup_old_files(directory: str, max_age_seconds: int = 3600) -> None:
    """Clean up old temporary files"""
    current_time = datetime.now().timestamp()
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        try:
            if current_time - os.path.getctime(filepath) > max_age_seconds:
                os.unlink(filepath)
        except:
            pass
