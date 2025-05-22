import os
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import re

# Define common image and RAW extensions
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')
RAW_EXTENSIONS = ('.cr2', '.arw', '.nef', '.orf', '.sr2', '.dng', '.raf', '.pef', '.xmp') # Common RAW formats

def get_image_date(filepath):
    try:
        with Image.open(filepath) as img:
            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, tag_id)
                    if tag_name == 'DateTimeOriginal' or tag_name == 'DateTimeDigitized':
                        return datetime.strptime(value, "%Y:%m:%d %H")
    except Exception:
        pass

    try:
        return datetime.fromtimestamp(os.path.getmtime(filepath))
    except Exception as e:
        print(f"Warning: Could not get file system date for {filepath}: {e}")
        return None 

def sanitize_filename(filename, allowed_delimiter_chars=""):
    safe_chars_pattern = r'a-zA-Z0-9\s._\-'
    
    if allowed_delimiter_chars:
        escaped_delimiter_chars = re.escape(allowed_delimiter_chars)
        safe_chars_pattern += escaped_delimiter_chars

    sanitized = re.sub(r'[^' + safe_chars_pattern + r']', '', filename)

    sanitized = re.sub(r'\s+', '_', sanitized)    
    sanitized = re.sub(r'__+', '_', sanitized)
    return sanitized.strip('_')

def find_paired_file(image_path, paired_extensions):
    base_name, _ = os.path.splitext(image_path)
    directory = os.path.dirname(image_path)

    for ext in paired_extensions:
        paired_path = base_name + ext.lower() # Check lowercase extension
        if os.path.exists(paired_path):
            return paired_path
        # Also check original casing if needed, though lowercasing is safer
        paired_path_orig_case = base_name + ext # Check original case
        if os.path.exists(paired_path_orig_case):
            return paired_path_orig_case
    return None

def is_image_file(filename):
    return filename.lower().endswith(IMAGE_EXTENSIONS)

def is_raw_file(filename):
    return filename.lower().endswith(RAW_EXTENSIONS)

def is_jpg_file(filename):
    return filename.lower().endswith(('.jpg', '.jpeg'))
