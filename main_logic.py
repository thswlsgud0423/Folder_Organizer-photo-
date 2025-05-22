import os
import shutil
from datetime import datetime
from PIL import Image

from image_tagger import ImageTagger
from utils import get_image_date, sanitize_filename, find_paired_file, is_image_file, is_raw_file, is_jpg_file, IMAGE_EXTENSIONS, RAW_EXTENSIONS

TEMP_RESIZE_FOLDER = "temp_resized_images"
TARGET_RESIZE_DIM = 224

# default parameters (can be overridden in GUI)
NUM_TOP_TAGS = 5
TAG_CONFIDENCE_THRESHOLD = 0.05

class PhotoOrganizer:
    def __init__(self, source_folder, destination_base_folder, 
                 file_id_prefix="", tag_delimiter="_", 
                 num_top_tags=NUM_TOP_TAGS, tag_confidence_threshold=TAG_CONFIDENCE_THRESHOLD):
        
        self.source_folder = source_folder
        self.destination_base_folder = destination_base_folder
        self.image_tagger = None
        self.tagged_image_cache = {}
        
        # Store user-defined parameters
        self.file_id_prefix = sanitize_filename(file_id_prefix)
        self.tag_delimiter = tag_delimiter 
        self.num_top_tags = num_top_tags
        self.tag_confidence_threshold = tag_confidence_threshold

    def _get_image_tagger(self):
        if self.image_tagger is None:
            self.image_tagger = ImageTagger()
        return self.image_tagger

    def organize_photos(self):
        if not os.path.isdir(self.source_folder):
            print(f"Error: Source folder does not exist: {self.source_folder}")
            return False

        os.makedirs(TEMP_RESIZE_FOLDER, exist_ok=True)
        print(f"Created temporary folder: {TEMP_RESIZE_FOLDER}")

        all_image_files = self._scan_images()
        if not all_image_files:
            print("No image files found in the source folder.")
            self._cleanup_temp_folder()
            return True

        # Resize JPEGs and prepare for batch tagging
        jpegs_to_tag = []
        original_jpeg_paths = []
        raw_to_tag = []
        original_raw_paths = []
        for file_path in all_image_files:
            if is_jpg_file(file_path):
                try:
                    img = Image.open(file_path)
                    if max(img.size) > TARGET_RESIZE_DIM:
                        img.thumbnail((TARGET_RESIZE_DIM, TARGET_RESIZE_DIM), Image.LANCZOS)
                    temp_path = os.path.join(TEMP_RESIZE_FOLDER, os.path.basename(file_path))
                    img.save(temp_path)
                    jpegs_to_tag.append(temp_path)
                    original_jpeg_paths.append(file_path)
                except Exception as e:
                    print(f"Warning: Could not process {file_path} for resizing: {e}. Skipping tagging for this file.")
        
            # Case: when you only have raw files like stonki SAM
            elif is_raw_file(file_path):
                try:
                    img = Image.open(file_path)
                    raw_to_jpg_img = img.convert('RGB') # converting to jpg
                    raw_to_jpg_img.save(file_path[:-4]+'.JPG')
                    if max(raw_to_jpg_img.size)  > TARGET_RESIZE_DIM:
                        raw_to_jpg_img.thumbnail((TARGET_RESIZE_DIM, TARGET_RESIZE_DIM), Image.LANCZOS)
                    temp_path = os.path.join(TEMP_RESIZE_FOLDER, os.path.basename(file_path))
                    raw_to_jpg_img.save(temp_path)
                    raw_to_tag.append(temp_path)
                    original_raw_paths.append(file_path)

                except Exception as e:
                    print(f"Warning: Could not process {file_path} for resizing: {e}. Skipping tagging for this file.")

        # Tag images in batches using the ImageTagger
        if jpegs_to_tag:
            image_tagger = self._get_image_tagger()
            print(f"Starting batch tagging for {len(jpegs_to_tag)} JPEGs...")
            temp_to_original_map = {os.path.join(TEMP_RESIZE_FOLDER, os.path.basename(original_path)): original_path for original_path in original_jpeg_paths}
            
            batch_size = 32
            for i in range(0, len(jpegs_to_tag), batch_size):
                batch_temp_paths = jpegs_to_tag[i:i + batch_size]
                
                valid_batch_temp_paths = [p for p in batch_temp_paths if os.path.exists(p)]
                
                if valid_batch_temp_paths:
                    # Pass self.num_top_tags from instance variable to the tagger
                    tags_batch_results = image_tagger.tag_images_batch(valid_batch_temp_paths, self.num_top_tags)
                    for temp_path, tags in tags_batch_results.items():
                        original_path = temp_to_original_map.get(temp_path)
                        if original_path:
                            # Filter tags by self.tag_confidence_threshold and clean them
                            filtered_tags = [
                                sanitize_filename(tag.replace("a photo of a ", "").replace("a photo of ", ""))
                                for tag, prob in tags if prob >= self.tag_confidence_threshold # Use self.tag_confidence_threshold
                            ]
                            self.tagged_image_cache[original_path] = filtered_tags
                        else:
                            print(f"Warning: Original path not found for temp file {temp_path}. Skipping tag cache.")
                print(f"Tagged {min(i + batch_size, len(jpegs_to_tag))} / {len(jpegs_to_tag)} JPEGs.")

        elif raw_to_tag:
            image_tagger = self._get_image_tagger()
            print(f"Starting batch tagging for {len(raw_to_tag)} RAWs...")
            temp_to_original_map = {os.path.join(TEMP_RESIZE_FOLDER, os.path.basename(original_path)): original_path for original_path in original_raw_paths}
            
            batch_size = 32
            for i in range(0, len(raw_to_tag), batch_size):
                batch_temp_paths = raw_to_tag[i:i + batch_size]
                
                valid_batch_temp_paths = [p for p in batch_temp_paths if os.path.exists(p)]
                
                if valid_batch_temp_paths:
                    # Pass self.num_top_tags from instance variable to the tagger
                    tags_batch_results = image_tagger.tag_images_batch(valid_batch_temp_paths, self.num_top_tags)
                    for temp_path, tags in tags_batch_results.items():
                        original_path = temp_to_original_map.get(temp_path)
                        if original_path:
                            # filter tags by self.tag_confidence_threshold and clean them
                            filtered_tags = [
                                sanitize_filename(tag.replace("a photo of a ", "").replace("a photo of ", ""))
                                for tag, prob in tags if prob >= self.tag_confidence_threshold
                            ]
                            self.tagged_image_cache[original_path] = filtered_tags
                        else:
                            print(f"Warning: Original path not found for temp file {temp_path}. Skipping tag cache.")
                print(f"Tagged {min(i + batch_size, len(raw_to_tag))} / {len(raw_to_tag)} JPEGs.")
        else:
            print("No RAWs found for tagging.")

        # Phase 3: Organize all files
        for file_path in all_image_files:
            self._process_single_file(file_path)

        self._cleanup_temp_folder()
        print("Organization process completed.")
        return True

    def _scan_images(self):
        """Scans the source folder for all relevant image files."""
        image_files = []
        for root, _, files in os.walk(self.source_folder):
            for file in files:
                if is_image_file(file):
                    image_files.append(os.path.join(root, file))
        return image_files

    def _process_single_file(self, file_path):
        """Processes a single image file, determining its date and new path."""
        file_name = os.path.basename(file_path)
        base_name, file_ext = os.path.splitext(file_name)
        
        # Get date
        file_date = get_image_date(file_path)
        if file_date is None:
            print(f"Could not determine date for {file_name}. Skipping.")
            return

        year_folder = file_date.strftime("%Y")
        month_name = file_date.strftime("%m-%B") # e.g., 01-January
        date_time_str = file_date.strftime("%Y%m%d_%H%M%S") # Detailed date-time for filename

        # Get tags (if JPEG and tagged)
        tags_str = ""
        if is_jpg_file(file_path) and file_path in self.tagged_image_cache:
            tags = self.tagged_image_cache[file_path]
            if tags:
                # Use the user-defined tag_delimiter
                tags_str = self.tag_delimiter + self.tag_delimiter.join(tags)

        # Construct new filename base name
        # Heuristic to match common camera/phone prefixes and include them
        original_prefix_match = ""
        if self.file_id_prefix: # If a custom signature is provided, use it
            original_prefix_match = sanitize_filename(self.file_id_prefix) + "_" + date_time_str
        elif file_name.startswith("SFH_"): 
            original_prefix_match = "SFH_" + date_time_str
        elif file_name.startswith("DSCF"): # Fujifilm
            original_prefix_match = base_name.split('_')[0] + "_" + date_time_str
        elif file_name.startswith("IMG_"): # Canon
            original_prefix_match = base_name.split('_')[0] + "_" + date_time_str
        elif file_name.startswith("DSC"): # Sony
            original_prefix_match = base_name.split('.')[0] + "_" + date_time_str
        elif file_name.startswith("_DSC"): # Sony
            original_prefix_match = base_name.split('.')[0] + "_" + date_time_str
        else:
            # Fallback: just use the date and time if no specific prefix is recognized
            original_prefix_match = date_time_str

        # Ensure the final filename is valid by re-sanitizing (removes any accidental invalid chars)
        # Note: tags_str already sanitized at creation
        new_base_name = f"{original_prefix_match}{tags_str}"
        new_base_name = sanitize_filename(new_base_name) # Final sanitization for full base name
        
        destination_dir = os.path.join(self.destination_base_folder, year_folder, month_name)
        os.makedirs(destination_dir, exist_ok=True)

        new_file_path = os.path.join(destination_dir, f"{new_base_name}{file_ext.lower()}")
        counter = 1
        while os.path.exists(new_file_path):
            if os.path.abspath(file_path) == os.path.abspath(new_file_path):
                print(f"Skipping move for identical file already at destination: {file_name}")
                return # Already in the correct place, do nothing

            new_file_path = os.path.join(destination_dir, f"{new_base_name}_{counter}{file_ext.lower()}")
            counter += 1

        try:
            shutil.move(file_path, new_file_path)
            print(f"Moved: {file_name} -> {os.path.basename(new_file_path)}")

            # Handle paired RAW files if the moved file was a JPEG
            if is_jpg_file(file_path):
                paired_raw_file = find_paired_file(file_path, RAW_EXTENSIONS)
                if paired_raw_file and os.path.exists(paired_raw_file):
                    paired_raw_name = os.path.basename(paired_raw_file)
                    _, paired_ext = os.path.splitext(paired_raw_name)
                    new_paired_path = os.path.join(destination_dir, f"{os.path.splitext(os.path.basename(new_file_path))[0]}{paired_ext.lower()}")
                    
                    shutil.move(paired_raw_file, new_paired_path)
                    print(f"Moved paired RAW: {paired_raw_name} -> {os.path.basename(new_paired_path)}")

            # Handle paired JPG files if the moved file was a RAW
            elif is_raw_file(file_path):
                paired_jpg_file = find_paired_file(file_path, ['.jpg', '.jpeg'])
                if paired_jpg_file and os.path.exists(paired_jpg_file):
                    paired_jpg_name = os.path.basename(paired_jpg_file)
                    _, paired_ext = os.path.splitext(paired_jpg_name)
                    new_paired_path = os.path.join(destination_dir, f"{os.path.splitext(os.path.basename(new_file_path))[0]}{paired_ext.lower()}")
                    
                    shutil.move(paired_jpg_file, new_paired_path)
                    print(f"Moved paired JPG: {paired_jpg_name} -> {os.path.basename(new_paired_path)}")

        except Exception as e:
            print(f"Error moving {file_name}: {e}")

    def _cleanup_temp_folder(self):
        """Removes the temporary resized images folder."""
        if os.path.exists(TEMP_RESIZE_FOLDER):
            try:
                shutil.rmtree(TEMP_RESIZE_FOLDER)
                print(f"Cleaned up temporary folder: {TEMP_RESIZE_FOLDER}")
            except Exception as e:
                print(f"Error cleaning up temporary folder '{TEMP_RESIZE_FOLDER}': {e}")

