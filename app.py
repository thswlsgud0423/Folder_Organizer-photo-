import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, Spinbox
import os
import threading
import queue
import sys
from main_logic import PhotoOrganizer, TEMP_RESIZE_FOLDER, NUM_TOP_TAGS, TAG_CONFIDENCE_THRESHOLD

try:
    import tkinterdnd2 as tkdnd
except ImportError:
    messagebox.showerror("Error", "tkinterdnd2 not found.\nPlease install it: pip install tkinterdnd2")
    sys.exit(1)

class PhotoOrganizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Photo Organizer")
        self.root.geometry("800x700")
        self.root.resizable(True, True)

        self.source_path = tk.StringVar()
        self.destination_path = tk.StringVar()
        self.signature_prefix = tk.StringVar(value="")
        self.tag_delimiter = tk.StringVar(value="_")
        self.num_top_tags_var = tk.IntVar(value=NUM_TOP_TAGS)
        self.tag_confidence_var = tk.DoubleVar(value=TAG_CONFIDENCE_THRESHOLD)

        self.create_widgets()
        self.setup_drag_and_drop()

        self.log_queue = queue.Queue()
        self.after_id = self.root.after(100, self.process_queue)

        self.organizer_thread = None

        self.log_message("Application started. Ready for input.")

    def create_widgets(self):
        # --- Frame for Inputs ---
        input_frame = tk.Frame(self.root, padx=10, pady=10)
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

        # --- New Controls ---
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
        # Spinbox for numerical input with up/down arrows
        self.num_tags_spinbox = Spinbox(input_frame, from_=1, to_=10, textvariable=self.num_top_tags_var, width=5, bd=2, relief="groove")
        self.num_tags_spinbox.grid(row=4, column=1, padx=5, pady=2, sticky="w")

        # Tag Confidence Threshold
        tk.Label(input_frame, text="Min Tag Confidence (0.0 - 1.0):").grid(row=5, column=0, sticky="w", pady=2)
        self.confidence_spinbox = Spinbox(input_frame, from_=0.0, to_=1.0, increment=0.01, format="%.2f", textvariable=self.tag_confidence_var, width=5, bd=2, relief="groove")
        self.confidence_spinbox.grid(row=5, column=1, padx=5, pady=2, sticky="w")

        # Configure column 1 to expand horizontally
        input_frame.columnconfigure(1, weight=1)

        # --- Start Button ---
        self.start_button = tk.Button(self.root, text="Start Photo Organization", command=self.start_organization, height=2, bg="#4CAF50", fg="white", font=("Arial", 12, "bold"))
        self.start_button.pack(pady=15, fill=tk.X, padx=10)

        # --- Log Output ---
        tk.Label(self.root, text="Process Log:").pack(pady=(5, 0), anchor="w", padx=10)
        self.log_text = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, height=15, state='disabled', bg="#f0f0f0", bd=2, relief="sunken")
        self.log_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        self.log_text.tag_config('error_tag', foreground='red')
        self.log_text.tag_config('warning_tag', foreground='orange')
        self.log_text.tag_config('success_tag', foreground='green')
        self.log_text.tag_config('info_tag', foreground='blue')

        # --- Status Label ---
        self.status_label = tk.Label(self.root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

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
            else:
                self.log_text.insert(tk.END, message + "\n")
            
            self.log_text.config(state='disabled')
            self.log_text.see(tk.END)

        self.after_id = self.root.after(100, self.process_queue)

    def start_organization(self):
        source = self.source_path.get()
        destination = self.destination_path.get()
        # Get new parameters from GUI
        signature = self.signature_prefix.get()
        delimiter = self.tag_delimiter.get()
        num_tags = self.num_top_tags_var.get()
        confidence = self.tag_confidence_var.get()

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

        parent_dest_dir = os.path.dirname(destination)
        if not parent_dest_dir:
            parent_dest_dir = os.path.abspath(os.sep)

        if not os.path.exists(parent_dest_dir):
            messagebox.showerror("Invalid Input", f"The parent directory of the destination does not exist:\n{parent_dest_dir}")
            self.log_message(f"Error: Parent directory of destination '{destination}' does not exist.", level='error')
            return
        if not os.access(parent_dest_dir, os.W_OK):
            messagebox.showerror("Permission Error", f"Cannot write to the parent directory of the destination:\n{parent_dest_dir}\nPlease choose a writable location.")
            self.log_message(f"Error: Parent directory of destination '{destination}' is not writable.", level='error')
            return

        # Clear previous logs and update UI for start
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        self.status_label.config(text="Status: Organizing photos...")
        self.start_button.config(state='disabled', text="Processing...")

        self.log_message("Starting organization process...", level='info')
        self.log_message(f"Source: {source}", level='info')
        self.log_message(f"Destination: {destination}", level='info')
        self.log_message(f"Custom Prefix: '{signature}'", level='info')
        self.log_message(f"Tag Delimiter: '{delimiter}'", level='info')
        self.log_message(f"Max Tags per Image: {num_tags}", level='info')
        self.log_message(f"Min Tag Confidence: {confidence}", level='info')


        # Run organization in a separate thread to keep GUI responsive
        self.organizer_thread = threading.Thread(
            target=self._run_organization_in_thread,
            args=(source, destination, signature, delimiter, num_tags, confidence)
        )
        self.organizer_thread.daemon = True
        self.organizer_thread.start()

    def _run_organization_in_thread(self, source, destination, signature, delimiter, num_tags, confidence):
        """Method to be run in a separate thread for the core organization logic."""
        try:
            organizer = PhotoOrganizer(
                source_folder=source,
                destination_base_folder=destination,
                file_id_prefix=signature,
                tag_delimiter=delimiter,
                num_top_tags=num_tags,
                tag_confidence_threshold=confidence
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