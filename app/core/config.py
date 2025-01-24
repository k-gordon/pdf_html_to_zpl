import os

MAX_UPLOAD_SIZE = int(os.getenv('MAX_UPLOAD_SIZE', 10 * 1024 * 1024))
SUPPORTED_FILE_TYPES = ["pdf", "png", "jpg", "jpeg", "html"]
TEMP_DIR = "temp"

# Create temp directory
os.makedirs(TEMP_DIR, exist_ok=True)
