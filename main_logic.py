import os
import shutil
from datetime import datetime
from PIL import Image
import re
import rawpy

from image_tagger import ImageTagger
from utils import get_image_date, sanitize_filename, find_paired_file, is_image_file, is_raw_file, is_jpg_file, IMAGE_EXTENSIONS, RAW_EXTENSIONS


TEMP_RESIZE_FOLDER = "temp_resized_images"
TARGET_RESIZE_DIM = 224
NUM_TOP_TAGS = 5
TAG_CONFIDENCE_THRESHOLD = 0.05
BATCH_SIZE = 10

class PhotoOrganizer:
    def __init__(self, source_folder, destination_base_folder,
                 file_id_prefix="", tag_delimiter=",",
                 num_top_tags=NUM_TOP_TAGS, tag_confidence_threshold=TAG_CONFIDENCE_THRESHOLD,
                 custom_tags=None,
                 log_callback=None,
                 processing_mode="jpg_and_raw"):
        
        self.source_folder = source_folder
        self.destination_base_folder = destination_base_folder
        self.file_id_prefix = sanitize_filename(file_id_prefix)
        self.tag_delimiter = tag_delimiter
        self.num_top_tags = num_top_tags
        self.tag_confidence_threshold = tag_confidence_threshold
        self.log_callback = log_callback if log_callback else self._default_log
        self.processing_mode = processing_mode
        self.processed_count = 0
        self.skipped_count = 0
        self.error_count = 0

        self.image_tagger = ImageTagger(custom_tags=custom_tags)
        self._log(f"ImageTagger initialized with {len(self.image_tagger.candidate_tags)} tags", level='info')

        self.tagged_image_cache = {}

    def _default_log(self, message, level='info'):
        print(f"[{level.upper()}] {message}")

    def _log(self, message, level='info'):
        if self.log_callback:
            self.log_callback(message, level)

    def _generate_new_filename(self, original_filename, date_obj, tags_with_probs):

        base, ext = os.path.splitext(original_filename)
        
        date_time_str = date_obj.strftime("%Y%m%d_%H%M%S") # Detailed date-time for filename

        cleaned_tags = []
        for tag_full_phrase, _ in tags_with_probs:
            cleaned_tag_part = re.sub(r"^a photo of (a |an |the )?", "", tag_full_phrase, flags=re.IGNORECASE).strip()
            cleaned_tag_part = re.sub(r'[^a-zA-Z0-9\s._-]+', '', cleaned_tag_part) 
            cleaned_tag_part = re.sub(r'\s+', ' ', cleaned_tag_part)
            cleaned_tag_part = cleaned_tag_part.strip()
            
            if cleaned_tag_part:
                cleaned_tags.append(cleaned_tag_part)

        tags_str_for_filename = self.tag_delimiter.join(cleaned_tags)

        new_name_parts = []
        if self.file_id_prefix:
            new_name_parts.append(sanitize_filename(self.file_id_prefix))
        
        new_name_parts.append(date_time_str)

        if tags_str_for_filename:
            new_name_parts.append(tags_str_for_filename)
        
        if not new_name_parts:
            new_name_parts.append("untitled")

        final_base_name_raw = self.tag_delimiter.join(new_name_parts)

        new_filename = sanitize_filename(final_base_name_raw, allowed_delimiter_chars=self.tag_delimiter) + ext.lower()
        
        new_filename = re.sub(r'(?:' + re.escape(self.tag_delimiter) + r')+', self.tag_delimiter, new_filename)
        new_filename = new_filename.strip(self.tag_delimiter)

        return new_filename


    def organize_photos(self):
        self._log(f"Scanning source folder for files based on mode: '{self.processing_mode}'...", level='info')
        all_files_to_process = [] 

        if self.processing_mode == "jpg_and_raw":
            for root, _, files in os.walk(self.source_folder):
                for file in files:
                    if is_image_file(file) or is_raw_file(file):
                        all_files_to_process.append(os.path.join(root, file))
        elif self.processing_mode == "raw_only":
            for root, _, files in os.walk(self.source_folder):
                for file in files:
                    if is_raw_file(file):
                        all_files_to_process.append(os.path.join(root, file))
        else:
            self._log(f"Error: Unknown processing mode '{self.processing_mode}'. Aborting.", level='error')
            return False


        if not all_files_to_process:
            self._log("No relevant files found in the source folder based on the selected mode.", level='info')
            self._cleanup_temp_folder()
            return True

        self._log(f"Found {len(all_files_to_process)} files to process.", level='info')

        files_for_clip_tagging = [] # Paths to temporary JPGs
        original_path_map = {}

        os.makedirs(TEMP_RESIZE_FOLDER, exist_ok=True)

        for file_path in all_files_to_process:
            temp_img_path = None
            original_file_name = os.path.basename(file_path)

            if is_jpg_file(file_path):
                if self.processing_mode == "jpg_and_raw":
                    try:
                        img = Image.open(file_path)
                        if max(img.size) > TARGET_RESIZE_DIM:
                            img.thumbnail((TARGET_RESIZE_DIM, TARGET_RESIZE_DIM), Image.LANCZOS)
                        temp_img_path = os.path.join(TEMP_RESIZE_FOLDER, original_file_name)
                        img.save(temp_img_path)
                        self._log(f"Prepared JPG '{original_file_name}' for tagging.", level='debug')
                    except Exception as e:
                        self._log(f"Warning: Could not prepare JPG '{original_file_name}' for tagging: {e}. It will be moved by date only.", level='warning')
                else:
                    self._log(f"Skipping JPG '{original_file_name}' for tagging in '{self.processing_mode}' mode. It will be moved by date only.", level='info')
            
            elif is_raw_file(file_path):
                if self.processing_mode == "raw_only":
                    if rawpy:
                        try:
                            with rawpy.imread(file_path) as raw:
                                rgb_img_np = raw.postprocess(use_camera_wb=True, no_auto_bright=True)
                                img = Image.fromarray(rgb_img_np)

                                if max(img.size) > TARGET_RESIZE_DIM:
                                    img.thumbnail((TARGET_RESIZE_DIM, TARGET_RESIZE_DIM), Image.LANCZOS)
                                
                                temp_img_name = os.path.splitext(original_file_name)[0] + ".jpg"
                                temp_img_path = os.path.join(TEMP_RESIZE_FOLDER, temp_img_name)
                                img.save(temp_img_path)
                                self._log(f"Prepared RAW '{original_file_name}' as temporary JPG for tagging.", level='debug')
                        except Exception as e:
                            self._log(f"Warning: Could not convert RAW '{original_file_name}' to temporary JPG for tagging: {e}. It will be moved by date only.", level='warning')
                    else:
                        self._log(f"DOWNLOAD rawpy YOU STONKI SAMUEL (pip install rawpy)", level='warning')
                else:
                    self._log(f"Skipping RAW '{original_file_name}' for tagging in '{self.processing_mode}' mode. It will be moved as a paired file.", level='info')
            else:
                self._log(f"Skipping CLIP tagging for '{original_file_name}' (non-JPG/RAW image type). It will be moved by date only.", level='info')
            
            if temp_img_path and os.path.exists(temp_img_path):
                files_for_clip_tagging.append(temp_img_path)
                original_path_map[temp_img_path] = file_path

        if files_for_clip_tagging:
            self._log(f"Starting tagging", level='info')
            
            num_batches = (len(files_for_clip_tagging) + BATCH_SIZE - 1) // BATCH_SIZE
            for i in range(0, len(files_for_clip_tagging), BATCH_SIZE):
                batch_temp_paths = files_for_clip_tagging[i:i + BATCH_SIZE]
                
                valid_batch_temp_paths = [p for p in batch_temp_paths if os.path.exists(p)]

                if valid_batch_temp_paths:
                    self._log(f"Tagging batch {i//BATCH_SIZE + 1}/{num_batches}...", level='info')
                    try:
                        tags_batch_results = self.image_tagger.tag_images_batch(valid_batch_temp_paths, self.num_top_tags)
                        for temp_path, tags in tags_batch_results.items():
                            original_path = original_path_map.get(temp_path)
                            if original_path:
                                self.tagged_image_cache[original_path] = tags
                            else:
                                self._log(f"Warning: Original path not found for temp file {temp_path}. Skipping tag cache.", level='warning')
                    except Exception as e:
                        self._log(f"Error during batch tagging for batch starting with {valid_batch_temp_paths[0] if valid_batch_temp_paths else 'N/A'}: {e}", level='error')
                else:
                    self._log(f"Skipping empty or invalid batch at index {i}.", level='warning')
        else:
            self._log("No JPEGs or convertible RAWs found for tagging. All files will be moved based on date only.", level='info')

        self._log("Moving and renaming all files...", level='info')
        for file_path in all_files_to_process:
            self._process_single_file(file_path)

        self._cleanup_temp_folder()
        self._log(f"Organization process completed. Processed: {self.processed_count}, Skipped: {self.skipped_count}, Errors: {self.error_count}", level='success')
        return self.error_count == 0

    def _process_single_file(self, file_path):
        file_name = os.path.basename(file_path)
        
        file_date = get_image_date(file_path)
        if file_date is None:
            self._log(f"Could not determine date for {file_name}. Skipping.", level='warning')
            self.skipped_count += 1
            return

        year_folder = str(file_date.year)
        month_name = file_date.strftime("%m-%B") # e.g., 01-January

        tags_for_filename = []
        
        is_primary_file_for_tagging = False
        if self.processing_mode == "jpg_and_raw" and is_jpg_file(file_path):
            is_primary_file_for_tagging = True
        elif self.processing_mode == "raw_only" and is_raw_file(file_path):
            is_primary_file_for_tagging = True

        # retrieve tags from cache if available and this is a primary file
        if is_primary_file_for_tagging and file_path in self.tagged_image_cache:
            all_tags_with_probs = self.tagged_image_cache[file_path]
            tags_for_filename = [
                (tag, prob) for tag, prob in all_tags_with_probs
                if prob >= self.tag_confidence_threshold
            ]
            tags_for_filename = sorted(tags_for_filename, key=lambda x: x[1], reverse=True)[:self.num_top_tags]
            self._log(f"Tags found for '{file_name}': {[t[0] for t in tags_for_filename]}", level='debug')
        else:
            self._log(f"No CLIP tags available for '{file_name}'. Moving based on date only.", level='info')
            tags_for_filename = []


        # Construct new filename
        new_filename = self._generate_new_filename(file_name, file_date, tags_for_filename)

        destination_dir = os.path.join(self.destination_base_folder, year_folder, month_name)
        os.makedirs(destination_dir, exist_ok=True)

        final_destination_path = os.path.join(destination_dir, new_filename)
        
        # Handle filename conflicts by appending a counter
        counter = 1
        original_attempt_path = final_destination_path
        while os.path.exists(final_destination_path):
            # If the file already exists at the exact destination and is the same file, skip
            if os.path.abspath(file_path) == os.path.abspath(final_destination_path):
                self._log(f"Skipping '{file_name}': Already exists at destination and is identical.", level='info')
                self.skipped_count += 1
                return

            name, ext = os.path.splitext(original_attempt_path)
            final_destination_path = f"{name}_{counter}{ext}"
            counter += 1

        try:
            shutil.move(file_path, final_destination_path)
            self._log(f"Moved: '{file_name}' -> '{os.path.relpath(final_destination_path, self.destination_base_folder)}'", level='info')
            self.processed_count += 1

            if self.processing_mode == "jpg_and_raw":
                # If the current file is a JPG, check for a paired RAW
                if is_jpg_file(file_path): 
                    paired_raw_file = find_paired_file(file_path, RAW_EXTENSIONS)
                    if paired_raw_file and os.path.exists(paired_raw_file):
                        paired_raw_name_base, paired_raw_ext = os.path.splitext(os.path.basename(paired_raw_file))
                        # Use the same new base name as the JPG, but with the RAW extension
                        new_paired_path = os.path.join(destination_dir, f"{os.path.splitext(new_filename)[0]}{paired_raw_ext.lower()}")
                        
                        paired_counter = 1
                        initial_paired_path = new_paired_path
                        while os.path.exists(new_paired_path):
                            if os.path.abspath(paired_raw_file) == os.path.abspath(new_paired_path):
                                self._log(f"Skipping paired RAW '{os.path.basename(paired_raw_file)}': Already exists at destination and is identical.", level='info')
                                break # Already in place, no need to move
                            paired_name_base, paired_ext = os.path.splitext(initial_paired_path)
                            new_paired_path = f"{paired_name_base}_{paired_counter}{paired_ext}"
                            paired_counter += 1

                        if not os.path.exists(new_paired_path) or os.path.abspath(paired_raw_file) != os.path.abspath(new_paired_path):
                            shutil.move(paired_raw_file, new_paired_path)
                            self._log(f"Moved paired RAW: '{os.path.basename(paired_raw_file)}' -> '{os.path.relpath(new_paired_path, self.destination_base_folder)}'", level='info')
            
            elif self.processing_mode == "raw_only":
                if is_raw_file(file_path):
                    paired_jpg_file = find_paired_file(file_path, IMAGE_EXTENSIONS)
                    if paired_jpg_file and os.path.exists(paired_jpg_file):
                        if os.path.abspath(paired_jpg_file) != os.path.abspath(file_path):
                            paired_jpg_name_base, paired_jpg_ext = os.path.splitext(os.path.basename(paired_jpg_file))
                            new_paired_path = os.path.join(destination_dir, f"{os.path.splitext(new_filename)[0]}{paired_jpg_ext.lower()}")
                            
                            paired_counter = 1
                            initial_paired_path = new_paired_path
                            while os.path.exists(new_paired_path):
                                if os.path.abspath(paired_jpg_file) == os.path.abspath(new_paired_path):
                                    self._log(f"Skipping paired JPG '{os.path.basename(paired_jpg_file)}': Already exists at destination and is identical.", level='info')
                                    break
                                paired_name_base, paired_ext = os.path.splitext(initial_paired_path)
                                new_paired_path = f"{paired_name_base}_{paired_counter}{paired_ext}"
                                paired_counter += 1

                            if not os.path.exists(new_paired_path) or os.path.abspath(paired_jpg_file) != os.path.abspath(new_paired_path):
                                shutil.move(paired_jpg_file, new_paired_path)
                                self._log(f"Moved paired JPG: '{os.path.basename(paired_jpg_file)}' -> '{os.path.relpath(new_paired_path, self.destination_base_folder)}'", level='info')

        except Exception as e:
            self._log(f"Error moving '{file_name}': {e}", level='error')
            self.error_count += 1

    def _cleanup_temp_folder(self):
        """Removes the temporary folder for resized images."""
        if os.path.exists(TEMP_RESIZE_FOLDER):
            try:
                shutil.rmtree(TEMP_RESIZE_FOLDER)
                self._log(f"Cleaned up temporary folder: {TEMP_RESIZE_FOLDER}", level='debug')
            except Exception as e:
                self._log(f"Error cleaning up temporary folder '{TEMP_RESIZE_FOLDER}': {e}", level='error')
