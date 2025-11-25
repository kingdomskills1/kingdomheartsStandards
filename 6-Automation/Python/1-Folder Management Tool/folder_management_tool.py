import os
import tkinter as tk
import re
from tkinter import filedialog, messagebox, ttk
import shutil
import time
from send2trash import send2trash

# -------------------
# SETTINGS
# -------------------
# IGNORED_FILES = {
#     "desktop.ini",
#     ".DS_Store",
#     "_folder_tree.txt",
#     "Source.docx",
#     "Transfer.txt",
#     ".gitattributes",
# }
# IGNORED_FOLDERS = {".git"}

# -------------------
# GLOBAL VARIABLES
# -------------------
IGNORED_FILES = set()
IGNORED_FOLDERS = set()
IGNORED_EXTENSIONS = []

# -------------------
# TREE PRINT FUNCTION
# -------------------
# -------------------
# UTILITY: NUMERIC SORT
# -------------------
def numerical_sort(value):
    parts = re.split(r'(\d+)', value)
    return [int(p) if p.isdigit() else p.lower() for p in parts]

# -------------------
# CHOOSE FOLDER
# -------------------
def choose_folder():
    folder = filedialog.askdirectory(title="Select a folder")
    return folder

# -------------------
# TREE PRINT FUNCTION
# -------------------
def print_tree(path, prefix=""):
    try:
        items = sorted(os.listdir(path), key=numerical_sort)  # List directory items
    except PermissionError:
        return  # Handle permission error

    # Filter ignored files/folders
    items = [i for i in items if i not in IGNORED_FILES and i not in IGNORED_FOLDERS and not i.startswith(".")]

    # Filter ignored extensions (files that end with any ignored extension)
    items = [i for i in items if not any(i.endswith(ext) for ext in IGNORED_EXTENSIONS)]

    # Separate files and folders
    files = [i for i in items if os.path.isfile(os.path.join(path, i))]
    folders = [i for i in items if os.path.isdir(os.path.join(path, i))]

    # Print files first
    for i, file_name in enumerate(files):
        is_last_file = (i == len(files) - 1) and not folders  # last file if no folders follow
        connector = "└── " if is_last_file else "├── "
        # Change '/' to '\\' for file paths
        tree_text.insert(tk.END, prefix + connector + file_name.replace('/', '\\') + "\n")

    # Print folders after files
    for idx, folder_name in enumerate(folders):
        folder_path = os.path.join(path, folder_name)

        # Print a blank line before folder if it's not the first folder
        if idx > 0 or files:  # blank line if there were files before
            tree_text.insert(tk.END, prefix + "│\n")

        # Change '/' to '\\' for folder paths
        tree_text.insert(tk.END, prefix + ("└── " if idx == len(folders) - 1 else "├── ") + folder_name.replace('/', '\\') + "\\\n")

        # Determine new prefix for child items
        new_prefix = prefix + ("    " if idx == len(folders) - 1 else "│   ")
        print_tree(folder_path, new_prefix)

# -------------------
# ADD IGNORED FILES/FOLDERS & EXTENSIONS
# -------------------
def update_ignored_files():
    global IGNORED_FILES, IGNORED_FOLDERS, IGNORED_EXTENSIONS
    ignored_files_str = ignored_files_entry.get().strip()
    ignored_folders_str = ignored_folders_entry.get().strip()
    ignored_extensions_str = ignored_extensions_entry.get().strip()

    # Clean up the lists (remove extra spaces, commas, etc.)
    IGNORED_FILES = set(ignored_files_str.split(","))
    IGNORED_FOLDERS = set(ignored_folders_str.split(","))
    IGNORED_EXTENSIONS = [ext.strip().lstrip(".") for ext in ignored_extensions_str.split(",") if ext.strip()]

    print("Updated ignored files, folders, and extensions.")

# -------------------
# COPY TREE TEXT TO CLIPBOARD
# -------------------
def copy_tree_to_clipboard():
    tree_content = tree_text.get("1.0", tk.END).strip()
    if tree_content:
        root.clipboard_clear()
        root.clipboard_append(tree_content)
        messagebox.showinfo("Success", "Tree has been copied to clipboard.")
    else:
        messagebox.showwarning("No content", "No content to copy.")

# -------------------
# PRINT TREE CONTENT
# -------------------
def print_tree_content():
    if current_folder:  # Check if the folder is selected
        tree_text.delete(1.0, tk.END)  # Clear any existing content
        root_name = os.path.basename(current_folder.rstrip("/\\"))  # Get the root folder name
        tree_text.insert(tk.END, root_name + "\\\n")  # Print root folder name in tree_text with backslash
        print_tree(current_folder)  # Now call print_tree with the current folder path
    else:
        messagebox.showwarning("No folder selected", "Please choose a folder first.")  # Show warning if no folder is selected


# -------------------
# CREATE PRINT FOLDER TAB
# -------------------
def create_print_folder_tab():
    global ignored_files_entry, ignored_folders_entry, ignored_extensions_entry, tree_text
    
    # Create the tab for folder tree printing
    pprint_tab = ttk.Frame(notebook)
    notebook.add(pprint_tab, text="Print Folder & File Tree")  # Add to notebook

    # Folder selection
    folder_frame = ttk.Frame(pprint_tab)
    folder_frame.pack(padx=10, pady=5, fill="x")

    ttk.Label(folder_frame, text="Folder:").pack(side="left")
    choose_folder_button = ttk.Button(folder_frame, text="Choose Folder", command=choose_print_folder)
    choose_folder_button.pack(side="left", padx=5)

    # Ignored files/folders fields
    ignored_frame = ttk.Frame(pprint_tab)
    ignored_frame.pack(padx=10, pady=5, fill="x")

    ttk.Label(ignored_frame, text="Ignored Files (comma separated):").pack(side="left")
    ignored_files_entry = ttk.Entry(ignored_frame, width=50)
    ignored_files_entry.pack(side="left", padx=5)

    ttk.Label(ignored_frame, text="Ignored Folders (comma separated):").pack(side="left")
    ignored_folders_entry = ttk.Entry(ignored_frame, width=50)
    ignored_folders_entry.pack(side="left", padx=5)

    ttk.Label(ignored_frame, text="Ignored Extensions (comma separated):").pack(side="left")
    ignored_extensions_entry = ttk.Entry(ignored_frame, width=50)
    ignored_extensions_entry.pack(side="left", padx=5)

    ttk.Button(pprint_tab, text="Update Ignored Files/Folders/Extensions", command=update_ignored_files).pack(pady=5)

    # Scrollable text box for printing the tree
    tree_text_frame = ttk.Frame(pprint_tab)
    tree_text_frame.pack(padx=10, pady=5, fill="both", expand=True)

    # Create the Text widget to display the tree content
    tree_text = tk.Text(tree_text_frame, wrap="none", height=15)
    tree_text.pack(side="left", fill="both", expand=True, padx=5, pady=5)

    # Create a frame for the scrollbars (separate the horizontal scrollbar)
    scrollbar_frame = ttk.Frame(pprint_tab)
    scrollbar_frame.pack(padx=10, pady=5, fill="x")

    # Create vertical scrollbar for the Text widget
    scroll_y = ttk.Scrollbar(tree_text_frame, orient="vertical", command=tree_text.yview)
    scroll_y.pack(side="right", fill="y")

    # Create horizontal scrollbar for the Text widget and pack it below the Text widget
    scroll_x = ttk.Scrollbar(scrollbar_frame, orient="horizontal", command=tree_text.xview)
    scroll_x.pack(side="bottom", fill="x")

    # Link the scrollbars to the Text widget
    tree_text.config(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

    # Copy button
    copy_button = ttk.Button(pprint_tab, text="Copy Tree to Clipboard", command=copy_tree_to_clipboard)
    copy_button.pack(pady=10)

    # Print button
    print_button = ttk.Button(pprint_tab, text="Print Tree Content", command=print_tree_content)
    print_button.pack(pady=10)

# -------------------
# CHOOSE FOLDER AND PRINT TREE
# -------------------
def choose_print_folder():
    global current_folder
    folder = choose_folder()  # Let the user select the folder
    if folder:
        current_folder = folder  # Save the selected folder path globally
        print("Folder selected:", current_folder)  # Debug: To check the selected folder
    else:
        print("No folder selected.")


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



# ----------------DELETE FUNCTIONS ----------------
def open_delete_window():
    # New Toplevel window
    delete_win = tk.Toplevel(root)
    delete_win.title("Delete & Wipe Folder")
    delete_win.geometry("450x150")

    # Use root as master for StringVar
    folder_to_delete = tk.StringVar(master=root)

    # Function to choose folder
    def choose_folder_to_delete():
        path = filedialog.askdirectory(title="Select Folder to Delete")
        if path:
            folder_to_delete.set(path)

    # Function to start delete
    def start_delete():
        folder = folder_to_delete.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder first.")
            return

        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete and wipe:\n{folder}?"):
            wipe_and_recycle(folder)
            messagebox.showinfo("Done", f"Folder wiped and deleted:\n{folder}")
            delete_win.destroy()

    # Layout widgets
    frame = ttk.Frame(delete_win, padding=10)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="Select folder to delete & wipe:").pack(anchor="w", pady=5)
    ttk.Entry(frame, textvariable=folder_to_delete, width=50).pack(anchor="w", pady=5)
    ttk.Button(frame, text="Browse Folder", command=choose_folder_to_delete).pack(anchor="w", pady=5)
    ttk.Button(frame, text="Start Delete & Wipe", command=start_delete).pack(anchor="w", pady=5)


def collect_files_and_folders(root_folder):
    all_files = []
    all_folders = []
    for dirpath, dirnames, filenames in os.walk(root_folder, topdown=False):
        for filename in filenames:
            all_files.append(os.path.abspath(os.path.join(dirpath, filename)))
        for dirname in dirnames:
            all_folders.append(os.path.abspath(os.path.join(dirpath, dirname)))
    return all_files, all_folders

def force_delete_file(file_path, retries=3):
    import time
    from send2trash import send2trash
    for attempt in range(retries):
        try:
            if os.path.exists(file_path):
                os.chmod(file_path, 0o777)
                open(file_path, "w").close()
                send2trash(file_path)
            return True
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            print(f"Failed to delete {file_path}: {e}")
            return False
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        return True
    except Exception as e:
        print(f"Final removal failed for {file_path}: {e}")
        return False

def force_delete_folder(folder_path, retries=3):
    import time
    from send2trash import send2trash
    for attempt in range(retries):
        try:
            if os.path.exists(folder_path):
                os.chmod(folder_path, 0o777)
                send2trash(folder_path)
            return True
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            print(f"Failed to delete folder {folder_path}: {e}")
            return False
    try:
        if os.path.exists(folder_path):
            os.rmdir(folder_path)
        return True
    except Exception as e:
        print(f"Final folder removal failed for {folder_path}: {e}")
        return False

def wipe_and_recycle(root_folder):
    import os, time
    if not root_folder:
        print("No folder selected.")
        return

    files, folders = collect_files_and_folders(root_folder)

    temp_file_paths = []
    for index, file_path in enumerate(files, start=1):
        folder = os.path.dirname(file_path)
        new_name = f"temp_delete_file_{index}"
        new_path = os.path.abspath(os.path.join(folder, new_name))
        try:
            os.rename(file_path, new_path)
            temp_file_paths.append(new_path)
        except Exception as e:
            print(f"Rename failed for {file_path}: {e}")

    for file_path in temp_file_paths:
        if os.path.exists(file_path):
            force_delete_file(file_path)

    temp_folder_paths = []
    for index, folder_path in enumerate(folders, start=1):
        if folder_path == root_folder:
            continue
        parent = os.path.dirname(folder_path)
        new_name = f"temp_delete_folder_{index}"
        new_path = os.path.abspath(os.path.join(parent, new_name))
        try:
            os.rename(folder_path, new_path)
            temp_folder_paths.append(new_path)
        except Exception as e:
            print(f"Folder rename failed for {folder_path}: {e}")

    for folder_path in sorted(temp_folder_paths, key=lambda x: x.count(os.sep), reverse=True):
        if os.path.exists(folder_path):
            force_delete_folder(folder_path)

def choose_delete_folder():
    path = filedialog.askdirectory(title="Select Folder to Delete")
    if path:
        delete_folder_var.set(path)

def start_delete():
    folder = delete_folder_var.get()
    if not folder:
        messagebox.showerror("Error", "Please select a folder first.")
        return

    if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete and wipe:\n{folder}?"):
        wipe_and_recycle(folder)
        messagebox.showinfo("Done", f"Folder wiped and deleted:\n{folder}")


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
ttk.Label(delete_tab, text="Select folder to delete & wipe:").pack(anchor="w", padx=10, pady=5)
ttk.Entry(delete_tab, textvariable=delete_folder_var, width=50).pack(anchor="w", padx=10, pady=5)
ttk.Button(delete_tab, text="Browse Folder", command=choose_delete_folder).pack(anchor="w", padx=10, pady=5)
ttk.Button(delete_tab, text="Start Delete & Wipe", command=start_delete).pack(anchor="w", padx=10, pady=5)

# -------------------
# CREATE PRINT FOLDER TAB
# -------------------
create_print_folder_tab()

# ------------------ RUN ------------------
root.mainloop()