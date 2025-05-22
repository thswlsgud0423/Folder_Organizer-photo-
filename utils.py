import os
from PIL import Image, ExifTags, UnidentifiedImageError
from datetime import datetime

# Common file extensions
RAW_EXTENSIONS = ['.cr2', '.nef', '.arw', '.raf', '.orf', '.rw2', '.dng', '.pef', '.xmp']
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'] + RAW_EXTENSIONS

def get_image_date(image_path):
    try:
        with Image.open(image_path) as img:
            exif_data = img._getexif()
            if exif_data:
                for tag, value in exif_data.items():
                    if tag in [36867, 306]: # DateTimeOriginal, DateTime
                        try:
                            return datetime.strptime(str(value), '%Y:%m:%d %H') # second/minute are deleted - too much info
                        except ValueError:
                            continue
    except (AttributeError, KeyError, TypeError, ValueError, UnidentifiedImageError):
        print("one of AttributeError, KeyError, TypeError, ValueError, UnidentifiedImageError occured")
    except Exception:
        pass

    try:
        timestamp = os.path.getmtime(image_path)
        return datetime.fromtimestamp(timestamp)
    except Exception:
        return None
    
def sanitize_filename(filename):
    filename = filename.replace(" ", "_") # to make sure theres no space
    invalid_chars = '<>:"/\\|?*%'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    return filename

def find_paired_file(base_path, extensions_list):
    base_name, original_ext = os.path.splitext(base_path)
    original_ext_lower = original_ext.lower()
    
    for ext in extensions_list:
        if ext.lower() == original_ext_lower:
            continue

        paired_file = base_name + ext
        if os.path.exists(paired_file):
            return paired_file
    return None

def is_image_file(filepath):
    return os.path.splitext(filepath)[1].lower() in IMAGE_EXTENSIONS

def is_raw_file(filepath):
    return os.path.splitext(filepath)[1].lower() in RAW_EXTENSIONS

def is_jpg_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    return ext in ['.jpg', '.jpeg']