import os
import tkinter as tk
import re
from tkinter import filedialog, messagebox, ttk
import shutil
import time
from send2trash import send2trash
from tabs.delete_tab import DeleteTab
from tabs.print_tree_tab import PrintTreeTab
from tabs.converter_tab import ConverterTab

# Function to browse and select a folder (updates folder_var)
def browse_folder():
    path = filedialog.askdirectory(title="Select a folder")
    if path:  # If a folder is selected, update folder_var
        folder_var.set(path)
        print(f"Selected folder: {folder_var.get()}")  # For debugging


# ----------------Filters FUNCTIONS ----------------
def update_filters():
    # Get the selected filter mode from the UI (radio buttons, etc.)
    mode = filter_mode_var.get()  # This will get the selected mode ('include' or 'exclude')
    # print(f"update_filters function Selected mode: {mode}")  # Debugging line to check mode

    # Get the raw input from the user for filters
    exts_raw = ext_entry.get().strip()  # Extensions (e.g., .txt, .py)
    names_raw = name_entry.get().strip()  # Names (e.g., file1, report)
    names_ext_raw = name_ext_entry.get().strip()  # Full names (e.g., file1.txt)

    # Clean and convert raw inputs into lists of lowercased values
    extensions_var[:] = [e.strip().lower() for e in exts_raw.split(',') if e.strip()]
    names_var[:] = [n.strip().lower() for n in names_raw.split(',') if n.strip()]
    names_ext_var[:] = [ne.strip().lower() for ne in names_ext_raw.split(',') if ne.strip()]

    # Debugging output for the filters
    # print("Extensions:", extensions_var)
    # print("Names:", names_var)
    # print("Names + Extensions:", names_ext_var)
    # print(f"Filter Mode: {mode}")


def filter_item(item_lower, item_path, exts, names, names_ext, mode):
    """
    Filters files or folders based on the provided extensions, names, and full names.
    
    Args:
        item_lower (str): The lowercase version of the item (file or folder).
        item_path (str): The full path of the item.
        exts (list): List of extensions to filter by (e.g., ['.txt', '.jpg']).
        names (list): List of file/folder names to filter by (e.g., ['file1', 'image1']).
        names_ext (list): List of full names with extension to filter by (e.g., ['file1.txt', 'image1.jpg']).
        mode (str): Filter mode ('include' or 'exclude').

    Returns:
        bool: True if the item matches the filter criteria, False otherwise.
    """
    # Default match conditions to True, meaning we will include everything unless specified otherwise
    matches_ext = True  # No extension filter applied
    matches_name = True  # No name filter applied
    matches_full_name = True  # No full name filter applied

    # Apply extension filter if extensions list is not empty
    if exts:
        matches_ext = any(item_lower.endswith(ext) for ext in exts)

    # Apply name filter if names list is not empty
    if names:
        # Match the file name exactly or as a prefix
        matches_name = any(item_lower.startswith(name.lower()) for name in names)

    # Apply full name filter if names_ext list is not empty
    if names_ext:
        matches_full_name = any(item_lower == name.lower() for name in names_ext)

    # Debugging output to check the current match conditions
    print(f"Filter conditions - ext: {matches_ext}, name: {matches_name}, full name: {matches_full_name}")

    # If no filters are set (all fields are empty), treat it as "include all"
    if not any([exts, names, names_ext]):
        if mode == "exclude":
            # If no filters are provided and mode is exclude, include everything (do not exclude anything)
            return True

    # Combine conditions based on the filter mode (include or exclude)
    if mode == "include":
        # Item is included only if it matches all non-empty filters
        return matches_ext and matches_name and matches_full_name
    elif mode == "exclude":
        # Item is excluded if it matches all non-empty filters
        return not (matches_ext and matches_name and matches_full_name)

    return False  # If mode is neither 'include' nor 'exclude'

# ---------------- PRINT OPTIONS FUNCTIONS ----------------
def on_print_option_change(selected_var):
    for var in print_option_vars:
        if var != selected_var:
            var.set(False)

    if selected_var != folder_level_checkbox_var:
        # Uncheck folder level checkboxes when any print option above folder level is selected
        folder_level_folder_var.set(False)
        folder_level_file_var.set(False)
        folder_level_ext_var.set(False)
        folder_level_checkbox_var.set(False)

    # If Folder Level is checked, show the sub-options (Folder, File, Extension)
    if folder_level_checkbox_var.get():
        folder_level_frame.pack(anchor="w", pady=2)
    # else:
        # folder_level_frame.pack_forget()


def on_folder_level_sub_change():
    # If any sub-checkbox is checked, enable main Folder Levels checkbox
    if folder_level_folder_var.get() or folder_level_file_var.get() or folder_level_ext_var.get():
        folder_level_checkbox_var.set(True)
        # Uncheck other main options
        for var in print_option_vars:
            if var != folder_level_checkbox_var:
                var.set(False)



def format_output(folder_path, filename, levels):
    # Ensure that levels is not empty
    if not levels:
        levels = [1]  # Default to level 1 if no levels are provided

    # If levels is a list, pick the highest level
    level = max(levels) if levels else 1  # Ensure level is valid

    # Normalize folder path and split into parts
    folder_norm = os.path.normpath(folder_path)
    folder_parts = folder_norm.split(os.sep)
    full_file_path = os.path.join(folder_path, filename)

    # Clamp level so it never exceeds folder depth
    level = max(1, min(level, len(folder_parts)))  # Use max(levels) for folder level

    # Select last "level" folders
    selected_folders = folder_parts[-level:]

    # Start building the output
    result_parts = []

    # Folder Level logic (only for Folder Level checkbox)
    if folder_level_checkbox_var.get():
        # Check if all the Folder, File, and Extension checkboxes are unchecked
        if not (folder_level_folder_var.get() or folder_level_file_var.get() or folder_level_ext_var.get()):
            return ""  # If all are unchecked, return nothing


        if folder_level_folder_var.get():
            # Get the folder level input from the entry
            level_raw = folder_level_entry.get().strip()
            if not level_raw:  # If empty, show the full path of the folder
                # Normalize and replace backslashes with forward slashes
                normalized_folder_path = os.path.normpath(folder_path).replace("/", "\\")
                result_parts.append(normalized_folder_path)  # Full path of the folder (without filename)
            else:
                try:
                    level_int = int(level_raw)  # Convert to integer
                    level_int = max(1, min(level_int, len(folder_parts)))  # Clamp to folder depth
                    selected_folders = folder_parts[-level_int:]  # Select folder up to the given level
                    folder_path_with_level = "\\".join(selected_folders)  # Join with forward slashes

                    # Ensure the path ends with a forward slash
                    # folder_path_with_level = folder_path_with_level + "\\"  # Add forward slash at the end
                    result_parts.append(folder_path_with_level)  # Add only the folder path

                except ValueError:
                    result_parts.append("Invalid level input")  # In case the user enters an invalid level

        # Join folder parts with backslashes first (before file and extension)
        result = '\\'.join(result_parts)  # Use backslash for Windows path separator

        name, ext = os.path.splitext(filename)  # Strip the extension from the filename

        # Now, check if the File checkbox is checked
        if folder_level_folder_var.get():
            result += '\\'  # Add a backslash if it's a folder

        # Now, check if the File checkbox is checked
        if folder_level_file_var.get():
            result += name  # Add the filename (without extension) after folder path

        # Extension logic (if Extension Level is checked)
        if folder_level_ext_var.get():
            # Check if the path is a folder or a file
            if not os.path.isdir(full_file_path):  # If it's not a directory, it's a file
                _, ext = os.path.splitext(filename)  # Get the file extension
                if folder_level_folder_var.get() and not folder_level_file_var.get():
                    # Add the file extension (without leading dot)
                    result += "|" + f'.{ext.lstrip(".")}'
                else:
                    result += f'.{ext.lstrip(".")}'
            else:
                if folder_level_ext_var.get() and not folder_level_file_var.get() and not folder_level_folder_var.get():
                     result += f'.{ext.lstrip(".")}'
                pass


        # Return the final result
        return result


    # If Full Path is checked, include the full path
    if print_path_var.get():
        # Include full path (drive + folder + filename)
        full_path = os.path.join(folder_path, filename)
        full_path = full_path.replace("/", "\\")
        result_parts.insert(0, full_path)  # Insert the full path at the beginning

    # If FileName is checked, include the file name (without extension)
    if print_filename_var.get():
        name, ext = os.path.splitext(filename)  # Strip the extension from the filename
        result_parts.append(name)  # Only add the file name, no extension

    # If Filename with Extension is checked, include the full filename with extension
    if print_filename_ext_var.get():
        result_parts.append(filename)  # Append the full filename (with extension)

    # If Extension is checked, include only the file extension
    if print_extension_var.get():
        # Get the file extension
        _, ext = os.path.splitext(filename)  # Split filename into name and extension
        result_parts.append(f'.{ext.lstrip(".")}')  # Append the extension (without leading dot)
        print(f"aaa: {filename}")
 

    # If no options are selected, just show the filename (with extension)
    if not result_parts:
        return ""

    # Join the parts with forward slashes for the final output
    result = '\\'.join(result_parts)  # Use backslashes to join the result parts

    # Debug: Print for checking
    print(f"Result Path: {result}")

    return result


# ----------------Actions BUTTONS FUNCTIONS ----------------
def reset_form():
    # Clear the output box
    output_box.delete(1.0, tk.END)

    # Reset the folder path entry field
    folder_var.set("")

    # Reset all filter entries
    ext_entry.delete(0, tk.END)
    name_entry.delete(0, tk.END)
    name_ext_entry.delete(0, tk.END)

    # Reset all checkboxes to their default state
    list_files_var.set(True)  # Assuming List Files should be checked by default
    list_folders_var.set(True)  # Assuming List Folders should be checked by default
    recursive_var.set(False)  # Assuming Recursive should be unchecked by default
    max_depth_var.set(0)  # Reset the max depth to 0
    filter_mode_var.set("include")  # Reset the filter mode to "include"

    # Reset the print options checkboxes
    print_path_var.set(True)  # Full Path by default
    print_filename_var.set(False)
    print_filename_ext_var.set(False)
    print_extension_var.set(False)

    # Reset the folder level checkboxes
    folder_level_checkbox_var.set(False)
    folder_level_folder_var.set(False)
    folder_level_file_var.set(False)
    folder_level_ext_var.set(False)

    # Reset the folder level entry
    folder_level_entry.delete(0, tk.END)

    # Reset counts
    update_count_labels(0, 0)


def folder_sort_key(path):
    # Extract folder/file name only
    name = os.path.basename(path)

    # Try to match leading digits in the base name
    m = re.match(r"^(\d+)", name)

    num = int(m.group(1)) if m else float('inf')
    return (num, name.lower())


def list_items():
    folder = folder_var.get()
    if not folder:
        messagebox.showerror("Error", "Please select a folder first.")
        return

    list_files = list_files_var.get()
    list_folders = list_folders_var.get()
    recursive = recursive_var.get()
    
    mode = filter_mode_var.get()  # This is 'include' or 'exclude' based on the radio button

    # Debug print to confirm the mode
    print(f"Selected mode mmmmmm: {mode}")


    max_depth = max_depth_var.get() if recursive else 0

    # Get filters
    exts = extensions_var        # List of extensions, e.g., ['.doc']
    names = names_var            # List of names to filter by (if any)
    names_ext = names_ext_var    # List of full names (if any)

    # Folder level formatting (e.g., for hierarchical display)
    levels_raw = folder_level_entry.get().strip()
    levels = [int(x) for x in levels_raw.split(',') if x.strip().isdigit()]

    folders = []
    files = []

    # ----------------------------- 
    # WALK DIRECTORY
    # -----------------------------
    if recursive:
        for root_dir, dirs, files_in_dir in os.walk(folder):
            rel_path = os.path.relpath(root_dir, folder)
            depth = 0 if rel_path == '.' else rel_path.count(os.sep) + 1
            if max_depth != 0 and depth > max_depth:
                continue

            # Process folders
            if list_folders:
                for d in dirs:
                    folder_path = format_output(root_dir, d, levels)
                    if folder_path:
                        folders.append(folder_path)

            # Process files and apply filter
            if list_files:
                for f in files_in_dir:
                    f_lower = f.lower()
                    file_path = os.path.join(root_dir, f)

                    if filter_item(f_lower, file_path, exts, names, names_ext, mode):
                        file_path_formatted = format_output(root_dir, f, levels)
                        if file_path_formatted:
                            files.append(file_path_formatted)

    else:
        # NON-recursive listing
        for item in os.listdir(folder):
            path = os.path.join(folder, item)
            item_lower = item.lower()

            if os.path.isdir(path) and list_folders:
                folder_path = format_output(folder, item, levels)
                if folder_path:
                    folders.append(folder_path)

            elif os.path.isfile(path) and list_files:
                if filter_item(item_lower, path, exts, names, names_ext, mode):
                    file_path_formatted = format_output(folder, item, levels)
                    if file_path_formatted:
                        files.append(file_path_formatted)

    # ----------------------------- 
    # SORTING
    # -----------------------------
    folders.sort(key=folder_sort_key)
    files.sort(key=lambda x: x.lower())

    # ----------------------------- 
    # OUTPUT RESULTS
    # -----------------------------
    results = folders + files
    output_box.delete(1.0, tk.END)
    for r in results:
        output_box.insert(tk.END, r + "\n")

    # Update the counts after listing items
    update_count_labels(len(folders), len(files))

def update_count_labels(folder_count, file_count):
    folder_count_label.config(text=f"Folders: {folder_count}")
    file_count_label.config(text=f"Files: {file_count}")

# ---------------- COPY FUNCTIONS ----------------
# Function to choose destination folder
def choose_destination():
    dest = filedialog.askdirectory(title="Select Destination Folder")
    destination_var.set(dest)

# Function to copy files/folders based on the selected mode
def start_copy():
    dest = destination_var.get()
    if not dest:
        messagebox.showerror("Error", "Please select a destination folder first.")
        return

    src_folder = folder_var.get()
    mode = copy_mode_var.get()

    print(f"Selected mode: {mode}")  # Debugging line to check the selected mode

    if not os.path.exists(src_folder):
        messagebox.showerror("Error", "Source folder doesn't exist.")
        return

    # Example logic for copying based on the selected mode
    if mode == "folders_only":
        print("Copying folders only...")  # Debugging line
        for item in os.listdir(src_folder):
            item_path = os.path.join(src_folder, item)
            if os.path.isdir(item_path):
                dest_path = os.path.join(dest, item)
                print(f"Copying folder: {item_path} to {dest_path}")  # Debugging line
                shutil.copytree(item_path, dest_path, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*"))  # Ensure files are ignored
    elif mode == "folders_files":
        for item in os.listdir(src_folder):
            item_path = os.path.join(src_folder, item)
            dest_path = os.path.join(dest, item)

            if os.path.isdir(item_path):
                # Create the folder in the destination (empty)
                print(f"Creating empty folder: {dest_path}")
                os.makedirs(dest_path, exist_ok=True)

            elif os.path.isfile(item_path):
                # Copy only files directly inside the main folder
                print(f"Copying file: {item_path} to {dest_path}")
                shutil.copy2(item_path, dest_path)

    elif mode == "full_tree":
        print("Copying full tree...")  # Debugging line
        shutil.copytree(src_folder, dest, dirs_exist_ok=True)

    messagebox.showinfo("Copy Complete", "Selected items have been copied successfully!")


# Function to open the subwindow for selecting copy options
def open_copy_window():
    global copy_win
    copy_win = tk.Toplevel(root)
    copy_win.title("Copy Listed Items")
    copy_win.geometry("400x250")

    # Label for copy mode
    ttk.Label(copy_win, text="Select Copy Mode:").pack(anchor="w", padx=10, pady=5)

    # Radio buttons for the copy modes
    tk.Radiobutton(copy_win, text="Folders Only", variable=copy_mode_var, value="folders_only").pack(anchor="w", padx=20)
    tk.Radiobutton(copy_win, text="Folders with Files", variable=copy_mode_var, value="folders_files").pack(anchor="w", padx=20)
    tk.Radiobutton(copy_win, text="Folders + Subfolders + Files", variable=copy_mode_var, value="full_tree").pack(anchor="w", padx=20)

    # Button to select the destination folder
    ttk.Button(copy_win, text="Select Destination Folder", command=choose_destination).pack(pady=10)
    ttk.Label(copy_win, textvariable=destination_var).pack(pady=5)

    # Button to start the copy process
    ttk.Button(copy_win, text="Start Copy", command=start_copy).pack(pady=10)



# ------------------ ROOT ------------------
root = tk.Tk()
root.title("Folder Management Tool")
root.geometry("1000x750")

# ------------------ TAB NOTEBOOK ------------------
notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True)

# ------------------ TAB FRAMES ------------------
list_tab = ttk.Frame(notebook)
delete_tab = ttk.Frame(notebook)
# pprint_tab = ttk.Frame(notebook)

notebook.add(list_tab, text="List / Copy")
notebook.add(delete_tab, text="Delete & Wipe")
# notebook.add(pprint_tab, text="Print Folder & File Tree")  # Add to notebook

# ===================== VARIABLES =====================
folder_var = tk.StringVar()
extensions_var = []
names_var = []
names_ext_var = []

include_exclude_var = tk.StringVar(value="include")  # Default to "include"


# List options
list_files_var = tk.BooleanVar(value=True)
list_folders_var = tk.BooleanVar(value=True)
recursive_var = tk.BooleanVar(value=False)
max_depth_var = tk.IntVar(value=0)
filter_mode_var = tk.StringVar(value="include")


# Print options
print_path_var = tk.BooleanVar(value=True)
print_filename_var = tk.BooleanVar(value=False)
print_filename_ext_var = tk.BooleanVar(value=False)
print_extension_var = tk.BooleanVar(value=False)
folder_level_checkbox_var = tk.BooleanVar(value=False)

print_option_vars = [print_path_var, print_filename_var, print_filename_ext_var, print_extension_var, folder_level_checkbox_var]

# Folder level options
folder_level_folder_var = tk.BooleanVar(value=False)
folder_level_file_var = tk.BooleanVar(value=False)
folder_level_ext_var = tk.BooleanVar(value=False)

# Copy variables
folder_var = tk.StringVar(value="")  # This will store the folder path
destination_var = tk.StringVar()  # For destination path
copy_mode_var = tk.StringVar(value="folders_only")  # Copy mode (default is folders only)

# Delete variables
delete_folder_var = tk.StringVar()


# ===================== LIST TAB LAYOUT =====================
frame1 = ttk.Frame(list_tab)
frame1.pack(padx=10, pady=5, fill="x")

ttk.Label(frame1, text="Folder:").pack(side="left")
ttk.Entry(frame1, textvariable=folder_var, width=50).pack(side="left", padx=5)
ttk.Button(frame1, text="Browse", command=browse_folder).pack(side="left")

# ===================== FILTERS FRAME LAYOUT =====================
filters_frame = ttk.LabelFrame(list_tab, text="Filters")
filters_frame.pack(fill="x", padx=10, pady=5)

# Extensions
ttk.Label(filters_frame, text="Extensions:").grid(row=0, column=0, sticky="w")
ext_entry = ttk.Entry(filters_frame)
ext_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

# File Names
ttk.Label(filters_frame, text="File Names:").grid(row=1, column=0, sticky="w")
name_entry = ttk.Entry(filters_frame)
name_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

# File Names with Extension
ttk.Label(filters_frame, text="File Names with Extension:").grid(row=2, column=0, sticky="w")
name_ext_entry = ttk.Entry(filters_frame)
name_ext_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

# Apply Filters Button
ttk.Button(filters_frame, text="Apply Filters", command=update_filters).grid(row=3, column=0, columnspan=2, pady=5)

# Radio Buttons for "Include" or "Exclude" Mode
include_exclude_frame = ttk.Frame(filters_frame)
include_exclude_frame.grid(row=4, column=0, columnspan=2, pady=5)

# Ensure that filter_mode_var is properly updated by the radio buttons
include_radio = tk.Radiobutton(include_exclude_frame, text="Include", variable=filter_mode_var, value="include")
include_radio.pack(side="left", padx=5)

exclude_radio = tk.Radiobutton(include_exclude_frame, text="Exclude", variable=filter_mode_var, value="exclude")
exclude_radio.pack(side="left", padx=5)

# Update the column weight for the filter fields to allow resizing
filters_frame.columnconfigure(1, weight=1)

# ===================== Options LAYOUT =====================
options_frame = ttk.LabelFrame(list_tab, text="Options")
options_frame.pack(fill="x", padx=10, pady=5)
ttk.Checkbutton(options_frame, text="List Files", variable=list_files_var).pack(anchor="w")
ttk.Checkbutton(options_frame, text="List Folders", variable=list_folders_var).pack(anchor="w")
ttk.Checkbutton(options_frame, text="Include Subfolders", variable=recursive_var).pack(anchor="w")

depth_frame = ttk.Frame(options_frame)
depth_frame.pack(anchor="w", pady=5)
ttk.Label(depth_frame, text="Max Depth:").pack(side="left")
ttk.Spinbox(depth_frame, from_=0, to=50, width=5, textvariable=max_depth_var).pack(side="left", padx=5)

# ===================== PRINT OPTIONS =====================
print_frame = ttk.LabelFrame(list_tab, text="Print Options (choose only one)")
print_frame.pack(fill="x", padx=10, pady=5)

tk.Checkbutton(print_frame, text="Full Path", variable=print_path_var,
               command=lambda: on_print_option_change(print_path_var)).pack(anchor="w")
tk.Checkbutton(print_frame, text="Filename", variable=print_filename_var,
               command=lambda: on_print_option_change(print_filename_var)).pack(anchor="w")
tk.Checkbutton(print_frame, text="Filename with Extension", variable=print_filename_ext_var,
               command=lambda: on_print_option_change(print_filename_ext_var)).pack(anchor="w")
tk.Checkbutton(print_frame, text="Extension", variable=print_extension_var,
               command=lambda: on_print_option_change(print_extension_var)).pack(anchor="w")

# Folder level sub-options
folder_level_frame = ttk.Frame(print_frame)
folder_level_frame.pack(anchor="w", pady=2)

tk.Checkbutton(folder_level_frame, text="Folder Levels", variable=folder_level_checkbox_var,
               command=lambda: on_print_option_change(folder_level_checkbox_var)).pack(side="left", padx=2)
ttk.Label(folder_level_frame, text="Level (e.g., 1,2,3):").pack(side="left", padx=2)
folder_level_entry = ttk.Entry(folder_level_frame, width=20)
folder_level_entry.pack(side="left", padx=2)
tk.Checkbutton(folder_level_frame, text="Folder", variable=folder_level_folder_var,
               command=on_folder_level_sub_change).pack(side="left", padx=2)
tk.Checkbutton(folder_level_frame, text="File", variable=folder_level_file_var,
               command=on_folder_level_sub_change).pack(side="left", padx=2)
tk.Checkbutton(folder_level_frame, text="Extension", variable=folder_level_ext_var,
               command=on_folder_level_sub_change).pack(side="left", padx=2)

# Buttons and counts
button_frame = ttk.Frame(list_tab)
button_frame.pack(fill="x", padx=10, pady=5)

center_frame = ttk.Frame(button_frame)
center_frame.pack(side="left", expand=True)

ttk.Button(center_frame, text="List Items", command=list_items).pack(side="left", padx=5)
ttk.Button(center_frame, text="Copy Listed Items", command=open_copy_window).pack(side="left", padx=5)
ttk.Button(center_frame, text="Reset", command=reset_form).pack(side="left", padx=5)


folder_count_label = ttk.Label(button_frame, text="Total Folders: 0")
folder_count_label.pack(side="right", padx=5)
file_count_label = ttk.Label(button_frame, text="Total Files: 0")
file_count_label.pack(side="right", padx=5)

# Output box
output_frame = ttk.Frame(list_tab)
output_frame.pack(fill="both", expand=True, padx=10, pady=5)
x_scroll = tk.Scrollbar(output_frame, orient="horizontal")
y_scroll = tk.Scrollbar(output_frame, orient="vertical")
output_box = tk.Text(output_frame, height=20, wrap="none", xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
x_scroll.config(command=output_box.xview)
y_scroll.config(command=output_box.yview)
output_box.grid(row=0, column=0, sticky="nsew")
y_scroll.grid(row=0, column=1, sticky="ns")
x_scroll.grid(row=1, column=0, sticky="ew")
output_frame.rowconfigure(0, weight=1)
output_frame.columnconfigure(0, weight=1)


# ===================== DELETE TAB LAYOUT =====================
delete_tab_manager = DeleteTab(root, delete_tab)


# ===================== PRINT FOLDER TAB LAYOUT =====================
print_tree_tab_manager = PrintTreeTab(root, notebook)

# ===================== Converter FOLDER TAB LAYOUT =====================
converter_tab = ConverterTab(root, notebook)

# ------------------ RUN ------------------
root.mainloop()