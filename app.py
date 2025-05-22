import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, Spinbox
import os
import threading
import queue
import sys
import re
from tkinter import ttk # Import ttk for Notebook

# Import constants and PhotoOrganizer from main_logic.py
from main_logic import PhotoOrganizer, TEMP_RESIZE_FOLDER, NUM_TOP_TAGS, TAG_CONFIDENCE_THRESHOLD

import tkinterdnd2 as tkdnd


# Define the file where custom tags will be stored
CUSTOM_TAGS_FILE = "custom_tags.txt"

class PhotoOrganizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Photo Organizer")
        self.root.geometry("1000x800")
        self.root.resizable(True, True)

        self.source_path = tk.StringVar()
        self.destination_path = tk.StringVar()
        self.signature_prefix = tk.StringVar(value="")
        self.tag_delimiter = tk.StringVar(value="_")
        self.num_top_tags_var = tk.IntVar(value=NUM_TOP_TAGS)
        self.tag_confidence_var = tk.DoubleVar(value=TAG_CONFIDENCE_THRESHOLD)
        self.processing_mode = tk.StringVar(value="jpg_and_raw")

        self.current_custom_tags = [] 

        self.create_widgets()
        self.setup_drag_and_drop()

        self.log_queue = queue.Queue()
        self.after_id = self.root.after(100, self.process_queue)

        self.organizer_thread = None

        self.log_message("Application started. Ready for input.")
        self._load_custom_tags() 

    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # Tab 1: Main Organization
        main_tab = ttk.Frame(self.notebook)
        self.notebook.add(main_tab, text="Main Organization")

        # --- Frame for Inputs ---
        input_frame = tk.Frame(main_tab, padx=10, pady=10)
        input_frame.pack(pady=10, fill=tk.X)

        # Source Folder Input
        tk.Label(input_frame, text="Source Folder:").grid(row=0, column=0, sticky="w", pady=2)
        self.source_entry = tk.Entry(input_frame, textvariable=self.source_path, width=70, bd=2, relief="groove")
        self.source_entry.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        self.source_entry.bind("<FocusOut>", self._validate_path_entry)
        self.source_entry.bind("<Return>", self._validate_path_entry)
        tk.Button(input_frame, text="Browse", command=self.browse_source_folder).grid(row=0, column=2, padx=5, pady=2)

        # Destination Folder Input
        tk.Label(input_frame, text="Destination Folder:").grid(row=1, column=0, sticky="w", pady=2)
        self.destination_entry = tk.Entry(input_frame, textvariable=self.destination_path, width=70, bd=2, relief="groove")
        self.destination_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        self.destination_entry.bind("<FocusOut>", self._validate_path_entry)
        self.destination_entry.bind("<Return>", self._validate_path_entry)
        tk.Button(input_frame, text="Browse", command=self.browse_destination_folder).grid(row=1, column=2, padx=5, pady=2)

        # --- Naming Controls ---
        # Signature Prefix
        tk.Label(input_frame, text="Custom Prefix (e.g., SFH):").grid(row=2, column=0, sticky="w", pady=2)
        self.signature_entry = tk.Entry(input_frame, textvariable=self.signature_prefix, width=30, bd=2, relief="groove")
        self.signature_entry.grid(row=2, column=1, padx=5, pady=2, sticky="w")
        tk.Label(input_frame, text="Example: Prefix_YYYYMMDD_tags.jpg").grid(row=2, column=2, sticky="w")


        # Tag Delimiter
        tk.Label(input_frame, text="Tag Delimiter (e.g., _ or .):").grid(row=3, column=0, sticky="w", pady=2)
        self.delimiter_entry = tk.Entry(input_frame, textvariable=self.tag_delimiter, width=5, bd=2, relief="groove")
        self.delimiter_entry.grid(row=3, column=1, padx=5, pady=2, sticky="w")
        tk.Label(input_frame, text="Example: tag1.tag2 or tag1_tag2").grid(row=3, column=2, sticky="w")

        # Number of Top Tags
        tk.Label(input_frame, text="Max Tags per Image:").grid(row=4, column=0, sticky="w", pady=2)
        self.num_tags_spinbox = Spinbox(input_frame, from_=1, to_=10, textvariable=self.num_top_tags_var, width=5, bd=2, relief="groove")
        self.num_tags_spinbox.grid(row=4, column=1, padx=5, pady=2, sticky="w")

        # Tag Confidence Threshold
        tk.Label(input_frame, text="Min Tag Confidence (0.0 - 1.0):").grid(row=5, column=0, sticky="w", pady=2)
        self.confidence_spinbox = Spinbox(input_frame, from_=0.0, to_=1.0, increment=0.01, format="%.2f", textvariable=self.tag_confidence_var, width=5, bd=2, relief="groove")
        self.confidence_spinbox.grid(row=5, column=1, padx=5, pady=2, sticky="w")

        # New: Processing Mode Selection
        processing_mode_frame = ttk.LabelFrame(input_frame, text="Processing Mode")
        processing_mode_frame.grid(row=6, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

        tk.Radiobutton(processing_mode_frame, text="Process JPGs & Paired RAWs (Default)", variable=self.processing_mode, value="jpg_and_raw").pack(anchor="w", padx=5, pady=2)
        tk.Radiobutton(processing_mode_frame, text="Process RAWs Only (Convert to JPG & Tag)", variable=self.processing_mode, value="raw_only").pack(anchor="w", padx=5, pady=2)


        # Configure column 1 to expand horizontally
        input_frame.columnconfigure(1, weight=1)

        # --- Start Button (on main tab) ---
        self.start_button = tk.Button(main_tab, text="Start Photo Organization", command=self.start_organization, height=2, bg="#4CAF50", fg="white", font=("Arial", 12, "bold"))
        self.start_button.pack(pady=15, fill=tk.X, padx=10)

        # --- Log Output (on main tab) ---
        tk.Label(main_tab, text="Process Log:").pack(pady=(5, 0), anchor="w", padx=10)
        self.log_text = scrolledtext.ScrolledText(main_tab, wrap=tk.WORD, height=15, state='disabled', bg="#f0f0f0", bd=2, relief="sunken")
        self.log_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        self.log_text.tag_config('error_tag', foreground='red')
        self.log_text.tag_config('warning_tag', foreground='orange')
        self.log_text.tag_config('success_tag', foreground='green')
        self.log_text.tag_config('info_tag', foreground='blue')

        # Tab 2: Custom Tags
        tags_tab = ttk.Frame(self.notebook)
        self.notebook.add(tags_tab, text="Manage Custom Tags")

        # Frame for adding new tags
        add_tag_frame = ttk.LabelFrame(tags_tab, text="Add New Custom Tags")
        add_tag_frame.pack(padx=10, pady=10, fill=tk.X)

        tk.Label(add_tag_frame, text="Enter new tag (one per line, will be prefixed 'a photo of '):").pack(padx=5, pady=5, anchor="w")
        self.new_tag_entry = tk.Text(add_tag_frame, height=5, width=60, bd=2, relief="groove")
        self.new_tag_entry.pack(padx=5, pady=5, fill=tk.X)
        self.new_tag_entry.bind("<KeyRelease>", self._limit_tag_input_chars)

        add_tag_buttons_frame = tk.Frame(add_tag_frame)
        add_tag_buttons_frame.pack(pady=5)
        tk.Button(add_tag_buttons_frame, text="Add Tag(s)", command=self._add_custom_tags).pack(side=tk.LEFT, padx=5)
        tk.Button(add_tag_buttons_frame, text="Save All Tags", command=self._save_custom_tags).pack(side=tk.LEFT, padx=5)


        # Frame for displaying existing tags
        display_tags_frame = ttk.LabelFrame(tags_tab, text="Existing Custom Tags (Editable, will be prefixed 'a photo of ' for AI)")
        display_tags_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        self.existing_tags_text = scrolledtext.ScrolledText(display_tags_frame, wrap=tk.WORD, height=15, state='disabled', bg="#f0f0f0", bd=2, relief="sunken")
        self.existing_tags_text.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)
        self.existing_tags_text.config(state='normal') # Set to normal so _display_tags can write initially

        tk.Button(display_tags_frame, text="Update & Save Displayed Tags", command=self._update_and_save_displayed_tags).pack(pady=5)
        tk.Button(display_tags_frame, text="Remove Selected Tag(s) (then Update & Save)", command=self._remove_selected_tags).pack(pady=5)
        tk.Button(display_tags_frame, text="Reload Tags from File", command=self._load_custom_tags).pack(pady=5)


        # --- Status Label (at the bottom of the root window) ---
        self.status_label = tk.Label(self.root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def _limit_tag_input_chars(self, event):
        """Limits the length of lines in the new_tag_entry to prevent very long tags."""
        max_line_length = 60 # Arbitrary limit for readability/sanity
        content = self.new_tag_entry.get("1.0", tk.END)
        lines = content.split('\n')
        
        updated_lines = []
        changed = False
        for line in lines:
            if len(line) > max_line_length:
                updated_lines.append(line[:max_line_length])
                changed = True
            else:
                updated_lines.append(line)
        
        if changed:
            cursor_pos = self.new_tag_entry.index(tk.INSERT)
            self.new_tag_entry.delete("1.0", tk.END)
            self.new_tag_entry.insert("1.0", '\n'.join(updated_lines))
            try:
                self.new_tag_entry.mark_set(tk.INSERT, cursor_pos)
            except tk.TclError:
                self.new_tag_entry.mark_set(tk.INSERT, tk.END)


    def setup_drag_and_drop(self):
        self.source_entry.drop_target_register(tkdnd.DND_FILES)
        self.source_entry.dnd_bind('<<Drop>>', self.handle_drop)
        self.source_entry.dnd_bind('<<DragEnter>>', lambda e: self.source_entry.config(bg='lightblue'))
        self.source_entry.dnd_bind('<<DragLeave>>', lambda e: self.source_entry.config(bg='white'))
        self.source_entry.dnd_bind('<<DragOver>>', lambda e: self.source_entry.config(bg='lightblue'))

    def handle_drop(self, event):
        self.source_entry.config(bg='white')
        paths = self.root.tk.splitlist(event.data)

        if paths:
            first_path = paths[0]
            if os.path.isdir(first_path):
                self.source_path.set(first_path)
                self.log_message(f"Source folder set by drag-and-drop: {first_path}", level='info')
            else:
                messagebox.showwarning("Invalid Drop", "Please drop a folder, not a file.")
                self.log_message(f"Invalid drop: '{first_path}' is not a folder.", level='warning')

        self._validate_path_entry(event)

    def browse_source_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.source_path.set(folder_selected)
            self._validate_path_entry(None)

    def browse_destination_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.destination_path.set(folder_selected)
            self._validate_path_entry(None)

    def _validate_path_entry(self, event):
        current_source = self.source_path.get()
        current_dest = self.destination_path.get()

        if current_source and not os.path.isdir(current_source):
            self.source_entry.config(bg='salmon')
            self.log_message(f"Warning: Source path '{current_source}' is not a valid directory or does not exist.", level='warning')
        else:
            self.source_entry.config(bg='white')
            if current_source:
                self.log_message(f"Source path set: {current_source}", level='debug')

        if current_dest:
            parent_dir = os.path.dirname(current_dest)
            if not parent_dir:
                parent_dir = os.path.abspath(os.sep)
            
            if not os.path.exists(parent_dir):
                self.destination_entry.config(bg='salmon')
                self.log_message(f"Warning: Parent directory of destination '{current_dest}' does not exist:\n{parent_dir}", level='warning')
            elif not os.access(parent_dir, os.W_OK):
                self.destination_entry.config(bg='salmon')
                self.log_message(f"Warning: Parent directory of destination '{current_dest}' is not writable:\n{parent_dir}", level='warning')
            else:
                self.destination_entry.config(bg='white')
                if current_dest:
                    self.log_message(f"Destination path set: {current_dest}", level='debug')
        else:
            self.destination_entry.config(bg='white')

    def log_message(self, message, level='info'):
        self.log_queue.put((message, level))

    def process_queue(self):
        while not self.log_queue.empty():
            message, level = self.log_queue.get()
            self.log_text.config(state='normal')
            
            if level == 'error':
                self.log_text.insert(tk.END, message + "\n", 'error_tag')
            elif level == 'warning':
                self.log_text.insert(tk.END, message + "\n", 'warning_tag')
            elif level == 'success':
                self.log_text.insert(tk.END, message + "\n", 'success_tag')
            elif level == 'info':
                self.log_text.insert(tk.END, message + "\n", 'info_tag')
            else: # debug or unknown level
                self.log_text.insert(tk.END, message + "\n")
            
            self.log_text.config(state='disabled')
            self.log_text.see(tk.END)

        self.after_id = self.root.after(100, self.process_queue)

    def _load_custom_tags(self):
        """Loads custom tags from the specified file."""
        self.current_custom_tags = []
        if os.path.exists(CUSTOM_TAGS_FILE):
            try:
                with open(CUSTOM_TAGS_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        tag = line.strip()
                        # No need to add prefix here, as it's assumed to be saved with it
                        if tag:
                            self.current_custom_tags.append(tag)
                self.log_message(f"Loaded {len(self.current_custom_tags)} custom tags from '{CUSTOM_TAGS_FILE}'.", level='info')
            except Exception as e:
                self.log_message(f"Error loading custom tags from '{CUSTOM_TAGS_FILE}': {e}", level='error')
        else:
            self.log_message(f"No custom tags file found at '{CUSTOM_TAGS_FILE}'.", level='info')
        self._display_tags() # Update GUI after loading

    def _save_custom_tags(self):
        """Saves the current custom tags to the specified file."""
        try:
            # Get tags from the editable text widget first
            tags_to_save = []
            content = self.existing_tags_text.get("1.0", tk.END).strip()
            for line in content.split('\n'):
                tag = line.strip()
                if tag: # Only save non-empty lines
                    # Ensure the prefix is added if it's not already there
                    if not tag.startswith("a photo of "):
                        tag = "a photo of " + tag
                    tags_to_save.append(tag)

            # Deduplicate and sort for consistency
            self.current_custom_tags = sorted(list(set(tags_to_save)))

            with open(CUSTOM_TAGS_FILE, 'w', encoding='utf-8') as f:
                for tag in self.current_custom_tags:
                    f.write(tag + "\n")
            self.log_message(f"Saved {len(self.current_custom_tags)} custom tags to '{CUSTOM_TAGS_FILE}'.", level='success')
            self._display_tags() # Refresh display after saving
        except Exception as e:
            self.log_message(f"Error saving custom tags to '{CUSTOM_TAGS_FILE}': {e}", level='error')
            messagebox.showerror("Save Error", f"Could not save custom tags: {e}")

    def _add_custom_tags(self):
        """Adds tags from the input text widget to the current list."""
        new_tags_raw = self.new_tag_entry.get("1.0", tk.END).strip()
        if not new_tags_raw:
            messagebox.showwarning("No Input", "Please enter tags in the 'Add New Custom Tags' box.")
            return

        new_tags_list = [tag.strip() for tag in new_tags_raw.split('\n') if tag.strip()]
        
        if not new_tags_list:
            messagebox.showwarning("No Input", "No valid tags found in the input. Please enter tags (one per line).")
            return

        added_count = 0
        for tag_input in new_tags_list:
            # Add the prefix here for new tags
            prefixed_tag = "a photo of " + tag_input
            if prefixed_tag not in self.current_custom_tags:
                self.current_custom_tags.append(prefixed_tag)
                added_count += 1
        
        self.new_tag_entry.delete("1.0", tk.END) # Clear the input box
        self.current_custom_tags = sorted(list(set(self.current_custom_tags))) # Deduplicate and sort
        self._display_tags() # Update GUI
        self.log_message(f"Added {added_count} new custom tags (prefixed 'a photo of ').", level='info')
        self._save_custom_tags() # Automatically save after adding

    def _update_and_save_displayed_tags(self):
        self._save_custom_tags() # This function already reads from the display and saves

    def _remove_selected_tags(self):
        try:
            selected_indices = self.existing_tags_text.tag_ranges(tk.SEL)
            if not selected_indices:
                messagebox.showwarning("No Selection", "Please select the tags you wish to remove in the 'Existing Custom Tags' box.")
                return

            # Get all lines
            all_lines = self.existing_tags_text.get("1.0", tk.END).strip().split('\n')
            
            # Find which lines correspond to the selection
            lines_to_keep = []
            start_line_idx = int(selected_indices[0].string.split('.')[0]) - 1
            end_line_idx = int(selected_indices[1].string.split('.')[0]) - 1

            for i, line in enumerate(all_lines):
                if not (start_line_idx <= i <= end_line_idx):
                    lines_to_keep.append(line.strip())

            # Update the text widget and then call save
            self.existing_tags_text.config(state='normal')
            self.existing_tags_text.delete("1.0", tk.END)
            self.existing_tags_text.insert("1.0", '\n'.join(lines_to_keep))
            self.existing_tags_text.config(state='disabled') # Re-disable after update
            
            self.log_message("Removed selected tags. Now saving updated list.", level='info')
            self._save_custom_tags() # Save the new list of tags
        except Exception as e:
            self.log_message(f"Error removing tags: {e}", level='error')
            messagebox.showerror("Error", f"Could not remove selected tags: {e}")


    def _display_tags(self):
        self.existing_tags_text.config(state='normal')
        self.existing_tags_text.delete("1.0", tk.END)
        for tag in self.current_custom_tags:
            # Display the full tag, including the prefix
            self.existing_tags_text.insert(tk.END, tag + "\n")
        self.existing_tags_text.config(state='disabled') # Make it read-only for general viewing

    def _normalize_destination_path(self, path):
        original_path = path
        
        # Define patterns for year and month folders
        year_pattern = r'^\d{4}$'
        # Month pattern: 'MM-MonthName' (e.g., '01-January') or just 'MonthName'
        month_num_name_pattern = r'^\d{2}-(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)$'
        month_name_pattern = r'^(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)$'
        
        path_components = []
        current_path = path
        
        # Split path into components and analyze from the end
        while True:
            head, tail = os.path.split(current_path)
            if not tail and (not head or os.path.ismount(current_path)): # Reached root or empty path, break
                break
            path_components.insert(0, tail) # Add to the beginning of the list
            current_path = head
            if not head: # Reached root of the drive (e.g., C:\)
                break

        # Check for month and year components from the end
        stripped_count = 0
        if path_components and (re.match(month_num_name_pattern, path_components[-1], re.IGNORECASE) or re.match(month_name_pattern, path_components[-1], re.IGNORECASE)):
            path_components.pop() # Remove month
            stripped_count += 1
            if path_components and re.match(year_pattern, path_components[-1]):
                path_components.pop() # Remove year
                stripped_count += 1
        elif path_components and re.match(year_pattern, path_components[-1]):
            path_components.pop() # Remove year
            stripped_count += 1

        # Reconstruct the path from the remaining components
        if stripped_count == 0: # Nothing was stripped
            return original_path

        # If original_path was just a drive letter (e.g. "C:") or root ("/")
        if not path_components and os.path.ismount(original_path):
             return original_path # Return the root drive itself (e.g. C:\)
        elif not path_components: # If path became entirely empty (e.g., "2025\05-May" -> empty)
            return '/' if os.sep == '/' else os.path.splitdrive(original_path)[0] + os.sep

        if os.path.isabs(original_path) and not current_path and path_components:
            if os.path.splitdrive(original_path)[0]:
                return os.path.join(os.path.splitdrive(original_path)[0] + os.sep, *path_components)
            elif original_path.startswith(os.sep):
                return os.path.join(os.sep, *path_components)
            else:
                return os.path.join(current_path, *path_components)
        else:
             return os.path.join(current_path, *path_components)

    def start_organization(self):
        source = self.source_path.get()
        destination = self.destination_path.get()
        signature = self.signature_prefix.get()
        delimiter = self.tag_delimiter.get()
        num_tags = self.num_top_tags_var.get()
        confidence = self.tag_confidence_var.get()
        selected_mode = self.processing_mode.get() # Get the selected mode

        # Basic validation before starting the thread
        if not source or not os.path.isdir(source):
            messagebox.showerror("Invalid Input", "Please select a valid source folder.")
            self.log_message("Error: Invalid source folder selected or it does not exist.", level='error')
            return

        if not destination:
            messagebox.showerror("Invalid Input", "Please select a destination folder.")
            self.log_message("Error: Destination folder not specified.", level='error')
            return
        
        # Ensure delimiter is not empty
        if not delimiter:
            messagebox.showerror("Invalid Input", "Tag delimiter cannot be empty.")
            self.log_message("Error: Tag delimiter is empty.", level='error')
            return

        # Check parent directory for writability (destination itself might not exist yet)
        parent_dest_dir = os.path.dirname(destination)
        if not parent_dest_dir:
            parent_dest_dir = os.path.abspath(os.sep) # Handle root directory case

        if not os.path.exists(parent_dest_dir):
            messagebox.showerror("Invalid Input", f"The parent directory of the destination does not exist:\n{parent_dest_dir}")
            self.log_message(f"Error: Parent directory of destination '{destination}' does not exist.", level='error')
            return
        if not os.access(parent_dest_dir, os.W_OK):
            messagebox.showerror("Permission Error", f"Cannot write to the parent directory of the destination:\n{parent_dest_dir}\nPlease choose a writable location.")
            self.log_message(f"Error: Parent directory of destination '{destination}' is not writable.", level='error')
            return

        # Normalize the destination path to ensure it's the true *base* folder
        normalized_destination = self._normalize_destination_path(destination)
        if normalized_destination != destination:
            self.log_message(f"Adjusted destination path from '{destination}' to '{normalized_destination}' for correct year/month structuring.", level='info')
            destination = normalized_destination # Use the normalized path

        # Clear previous logs and update UI for start
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        self.status_label.config(text="Status: Organizing photos...")
        self.start_button.config(state='disabled', text="Processing...")

        self.log_message("Starting organization process...", level='info')
        self.log_message(f"Source: {source}", level='info')
        self.log_message(f"Destination: {destination} (normalized)", level='info')
        self.log_message(f"Custom Prefix: '{signature}'", level='info')
        self.log_message(f"Tag Delimiter: '{delimiter}'", level='info')
        self.log_message(f"Max Tags per Image: {num_tags}", level='info')
        self.log_message(f"Min Tag Confidence: {confidence}", level='info')
        self.log_message(f"Processing Mode: {selected_mode}", level='info') # Log the selected mode

        # Run organization in a separate thread to keep GUI responsive
        self.organizer_thread = threading.Thread(
            target=self._run_organization_in_thread,
            args=(source, destination, signature, delimiter, num_tags, confidence, self.current_custom_tags, selected_mode) # Pass selected_mode
        )
        self.organizer_thread.daemon = True
        self.organizer_thread.start()

    def _run_organization_in_thread(self, source, destination, signature, delimiter, num_tags, confidence, custom_tags, processing_mode):
        """Method to be run in a separate thread for the core organization logic."""
        try:
            organizer = PhotoOrganizer(
                source_folder=source,
                destination_base_folder=destination,
                file_id_prefix=signature,
                tag_delimiter=delimiter,
                num_top_tags=num_tags,
                tag_confidence_threshold=confidence,
                custom_tags=custom_tags,
                log_callback=self.log_message,
                processing_mode=processing_mode # Pass the processing mode
            )
            success = organizer.organize_photos()

            if os.path.exists(TEMP_RESIZE_FOLDER):
                self.log_message("Warning: Temporary folder still exists. Attempting final synchronous cleanup.", level='warning')
                try:
                    import shutil
                    shutil.rmtree(TEMP_RESIZE_FOLDER)
                    self.log_message(f"Final cleanup of temporary folder: {TEMP_RESIZE_FOLDER}", level='info')
                except Exception as e:
                    self.log_message(f"Error during final cleanup of '{TEMP_RESIZE_FOLDER}': {e}", level='error')
            
            if success:
                self.log_message("Organization process finished successfully!", level='success')
                messagebox.showinfo("Success", "Photo organization completed!")
            else:
                self.log_message("Organization process failed or completed with errors. Check log for details.", level='error')
                messagebox.showerror("Failed", "Photo organization failed or completed with errors. Check log for details.")

        except Exception as e:
            self.log_message(f"An unhandled error occurred during organization: {e}", level='error')
            messagebox.showerror("Error", f"An unexpected error occurred: {e}\nCheck log for details.")
        finally:
            self.root.after(0, self._organization_complete_ui_update)

    def _organization_complete_ui_update(self):
        self.start_button.config(state='normal', text="Start Photo Organization")
        self.status_label.config(text="Status: Ready")
        self.organizer_thread = None

    def on_closing(self):
        if self.organizer_thread and self.organizer_thread.is_alive():
            if messagebox.askyesno("Exit", "Organization is in progress. Do you want to stop and exit?"):
                self.log_message("Exiting while organization is in progress. Temporary files may be left behind.", level='warning')
                try:
                    import shutil
                    if os.path.exists(TEMP_RESIZE_FOLDER):
                        shutil.rmtree(TEMP_RESIZE_FOLDER)
                        self.log_message(f"Forced cleanup of temporary folder: {TEMP_RESIZE_FOLDER}", level='info')
                except Exception as e:
                    self.log_message(f"Error during forced cleanup on exit: {e}", level='error')
                self.root.quit()
                self.root.destroy()
            else:
                return
        else:
            self.root.quit()
            self.root.destroy()

if __name__ == "__main__":
    root = tkdnd.Tk()
    app = PhotoOrganizerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()