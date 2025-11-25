import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def browse_folder():
    path = filedialog.askdirectory(title="Select a folder")
    folder_var.set(path)


def update_extensions():
    # Update extension list from user input
    raw = ext_entry.get().strip()
    if raw:
        exts = [e.strip().lower() for e in raw.split(',') if e.strip()]
        extensions_var.set(exts)
    else:
        extensions_var.set([])


def list_items():
    folder = folder_var.get()
    if not folder:
        messagebox.showerror("Error", "Please select a folder first.")
        return

    # Gather options
    selected_filter_mode = filter_mode_var.get()  # include / exclude
    list_files = list_files_var.get()
    list_folders = list_folders_var.get()
    recursive = recursive_var.get()
    extensions = extensions_var.get()

    results = []

    if recursive:
        for root, dirs, files in os.walk(folder):
            if list_files:
                for f in files:
                    path = os.path.join(root, f)
                    if filter_extension(f.lower(), extensions, selected_filter_mode):
                        results.append(path)

            if list_folders:
                for d in dirs:
                    path = os.path.join(root, d)
                    # Folders don't care about extension filtering
                    results.append(path)
    else:
        for item in os.listdir(folder):
            path = os.path.join(folder, item)
            if os.path.isfile(path) and list_files:
                if filter_extension(item.lower(), extensions, selected_filter_mode):
                    results.append(path)
            elif os.path.isdir(path) and list_folders:
                results.append(path)

    output_box.delete(1.0, tk.END)
    for r in results:
        output_box.insert(tk.END, r + "\n")


def filter_extension(filename, extensions, mode):
    if not extensions:
        return True
    ext = os.path.splitext(filename)[1].lower()
    if mode == "include":
        return ext in extensions
    else:  # exclude
        return ext not in extensions


# GUI Setup
root = tk.Tk()
root.title("Folder Listing Tool")
root.geometry("700x500")

folder_var = tk.StringVar()
extensions_var = tk.Variable(value=[])
filter_mode_var = tk.StringVar(value="include")
list_files_var = tk.BooleanVar(value=True)
list_folders_var = tk.BooleanVar(value=False)
recursive_var = tk.BooleanVar(value=False)

# Folder selector
frame = ttk.Frame(root)
frame.pack(pady=10, fill="x", padx=10)

ttk.Label(frame, text="Folder:").pack(side="left")
ttk.Entry(frame, textvariable=folder_var, width=50).pack(side="left", padx=5)
ttk.Button(frame, text="Browse", command=browse_folder).pack(side="left")

# File extension filter
ext_frame = ttk.LabelFrame(root, text="Extension Filter (comma-separated e.g. .jpg, .png)")
ext_frame.pack(fill="x", padx=10, pady=10)

ext_entry = ttk.Entry(ext_frame)
ext_entry.pack(side="left", padx=5, fill="x", expand=True)
ttk.Button(ext_frame, text="Apply", command=update_extensions).pack(side="left", padx=5)

# Include / Exclude mode
mode_frame = ttk.Frame(root)
mode_frame.pack(pady=5)

ttk.Label(mode_frame, text="Filter Mode:").pack(side="left")
ttk.Radiobutton(mode_frame, text="Include", variable=filter_mode_var, value="include").pack(side="left")
ttk.Radiobutton(mode_frame, text="Exclude", variable=filter_mode_var, value="exclude").pack(side="left")

# Options
options_frame = ttk.LabelFrame(root, text="Options")
options_frame.pack(fill="x", padx=10, pady=10)

ttk.Checkbutton(options_frame, text="List Files", variable=list_files_var).pack(anchor="w")
ttk.Checkbutton(options_frame, text="List Folders", variable=list_folders_var).pack(anchor="w")
ttk.Checkbutton(options_frame, text="Include Subfolders (Recursive)", variable=recursive_var).pack(anchor="w")

# List button
list_btn = ttk.Button(root, text="List Items", command=list_items)
list_btn.pack(pady=5)

# Copy button
copy_btn = ttk.Button(root, text="Copy Output", command=lambda: root.clipboard_clear() or root.clipboard_append(output_box.get(1.0, tk.END)))
copy_btn.pack(pady=5)

# Output box with scrollbars
output_frame = ttk.Frame(root)
output_frame.pack(fill="both", expand=True, padx=10, pady=10)

x_scroll = tk.Scrollbar(output_frame, orient="horizontal")
y_scroll = tk.Scrollbar(output_frame, orient="vertical")

output_box = tk.Text(
    output_frame,
    height=15,
    wrap="none",
    xscrollcommand=x_scroll.set,
    yscrollcommand=y_scroll.set
)

x_scroll.config(command=output_box.xview)
y_scroll.config(command=output_box.yview)

# Layout
output_box.grid(row=0, column=0, sticky="nsew")
y_scroll.grid(row=0, column=1, sticky="ns")
x_scroll.grid(row=1, column=0, sticky="ew")

output_frame.rowconfigure(0, weight=1)
output_frame.columnconfigure(0, weight=1)

root.mainloop()()
