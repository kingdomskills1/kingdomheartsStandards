import os
from tkinter import Tk, filedialog

# Hide the main tkinter window
root = Tk()
root.withdraw()

# Ask user to select a folder
folder_path = filedialog.askdirectory(title="Select a folder")

if folder_path:
    print(f"Selected folder: {folder_path}\n")

    # List files with extensions
    for file in os.listdir(folder_path):
        if os.path.isfile(os.path.join(folder_path, file)):
            print(file)
else:
    print("No folder selected")
