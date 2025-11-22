import os
import tkinter as tk
from tkinter import filedialog

# ------------------------
# SETTINGS
# ------------------------

# 1) Folder names to ignore (skip entire folder)
IGNORED_FOLDERS = {".git"}

# 2) File names/extensions to ignore
# You can add names OR extensions
IGNORED_FILES = {
    "Transfer.txt",
    "Source.docx",
    "Sources.docx",
    ".gitattributes",
    "desktop.ini",
    "Guide To Save.docx",
    "Intro to Science Collection.docx"
    # Add more if needed:
    # "example.txt",
    # "notes.docx",
}

# ------------------------
# FUNCTIONS
# ------------------------

def choose_folder():
    root = tk.Tk()
    root.withdraw()
    return filedialog.askdirectory(title="Select a folder")

def count_files_recursive(folder):
    total_files = 0
    folder_details = {}

    for root, dirs, files in os.walk(folder):

        # --- 1) Remove ignored folders from traversal ---
        dirs[:] = [d for d in dirs if d not in IGNORED_FOLDERS]

        # --- 2) Count files excluding ignored ones ---
        filtered_files = [f for f in files if f not in IGNORED_FILES]

        file_count = len(filtered_files)
        total_files += file_count
        folder_details[root] = file_count

    return total_files, folder_details


# ------------------------
# MAIN PROGRAM
# ------------------------

folder = choose_folder()

if folder:
    total, details = count_files_recursive(folder)

    print(f"Selected folder:\n{folder}\n")
    print(f"Total files (excluding .git and ignored files): {total}\n")

    print("Files per folder:")
    for path, count in details.items():
        print(f"{path} : {count}")
else:
    print("No folder selected.")
