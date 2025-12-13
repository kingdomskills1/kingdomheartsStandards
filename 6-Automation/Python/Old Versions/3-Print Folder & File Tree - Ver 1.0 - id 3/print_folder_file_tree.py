import os
import re
import tkinter as tk
from tkinter import filedialog

# -------------------
# SETTINGS
# -------------------
IGNORED_FILES = {
    "desktop.ini",
    ".DS_Store",
    "_folder_tree.txt",
    "Source.docx",
    "Transfer.txt",
    ".gitattributes",
}
IGNORED_FOLDERS = {".git"}

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
    root = tk.Tk()
    root.withdraw()
    return filedialog.askdirectory(title="Select a folder")

# -------------------
# TREE PRINT FUNCTION
# -------------------
def print_tree(path, prefix=""):
    try:
        items = sorted(os.listdir(path), key=numerical_sort)
    except PermissionError:
        return

    # Filter ignored files/folders
    items = [i for i in items if i not in IGNORED_FILES and i not in IGNORED_FOLDERS and not i.startswith(".")]

    # Separate files and folders
    files = [i for i in items if os.path.isfile(os.path.join(path, i))]
    folders = [i for i in items if os.path.isdir(os.path.join(path, i))]

    # Print files first
    for i, file_name in enumerate(files):
        is_last_file = (i == len(files) - 1) and not folders  # last if no folders follow
        connector = "└── " if is_last_file else "├── "
        print(prefix + connector + file_name)

    # Print folders after files
    for idx, folder_name in enumerate(folders):
        folder_path = os.path.join(path, folder_name)

        # Print a blank line before folder if it's not the first folder
        if idx > 0 or files:  # blank line if there were files before
            print(prefix + "│")

        print(prefix + ("└── " if idx == len(folders) - 1 else "├── ") + folder_name + "/")

        # Determine new prefix for child items
        new_prefix = prefix + ("    " if idx == len(folders) - 1 else "│   ")
        print_tree(folder_path, new_prefix)

# -------------------
# MAIN
# -------------------
folder = choose_folder()

if folder:
    root_name = os.path.basename(folder.rstrip("/\\"))
    print(root_name + "/")
    print_tree(folder)
else:
    print("No folder selected.")
