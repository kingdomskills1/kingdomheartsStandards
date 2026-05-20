import os
import re
import tkinter as tk

from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox


class PrintTreeTab:

    def __init__(self, root, notebook):

        self.root = root
        self.notebook = notebook

        self.current_folder = ""

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

        self.IGNORED_FILES = set()
        self.IGNORED_FOLDERS = set()
        self.IGNORED_EXTENSIONS = []

        self.create_tab()

    # -------------------
    # CREATE TAB
    # -------------------
    def create_tab(self):

        self.pprint_tab = ttk.Frame(self.notebook)

        self.notebook.add(
            self.pprint_tab,
            text="Print Folder & File Tree"
        )

        # ---------------- FOLDER FRAME ----------------
        folder_frame = ttk.Frame(self.pprint_tab)

        folder_frame.pack(
            padx=10,
            pady=5,
            fill="x"
        )

        ttk.Label(
            folder_frame,
            text="Folder:"
        ).pack(side="left")

        ttk.Button(
            folder_frame,
            text="Choose Folder",
            command=self.choose_print_folder
        ).pack(side="left", padx=5)

        # ---------------- IGNORE FRAME ----------------
        ignored_frame = ttk.Frame(self.pprint_tab)

        ignored_frame.pack(
            padx=10,
            pady=5,
            fill="x"
        )

        ttk.Label(
            ignored_frame,
            text="Ignored Files:"
        ).pack(side="left")

        self.ignored_files_entry = ttk.Entry(
            ignored_frame,
            width=40
        )

        self.ignored_files_entry.pack(
            side="left",
            padx=5
        )

        ttk.Label(
            ignored_frame,
            text="Ignored Folders:"
        ).pack(side="left")

        self.ignored_folders_entry = ttk.Entry(
            ignored_frame,
            width=40
        )

        self.ignored_folders_entry.pack(
            side="left",
            padx=5
        )

        ttk.Label(
            ignored_frame,
            text="Ignored Extensions:"
        ).pack(side="left")

        self.ignored_extensions_entry = ttk.Entry(
            ignored_frame,
            width=40
        )

        self.ignored_extensions_entry.pack(
            side="left",
            padx=5
        )

        ttk.Button(
            self.pprint_tab,
            text="Update Ignored",
            command=self.update_ignored_files
        ).pack(pady=5)

        # ---------------- TREE TEXT ----------------
        tree_text_frame = ttk.Frame(self.pprint_tab)

        tree_text_frame.pack(
            padx=10,
            pady=5,
            fill="both",
            expand=True
        )

        self.tree_text = tk.Text(
            tree_text_frame,
            wrap="none",
            height=15
        )

        self.tree_text.pack(
            side="left",
            fill="both",
            expand=True,
            padx=5,
            pady=5
        )

        # ---------------- SCROLLBARS ----------------
        scroll_y = ttk.Scrollbar(
            tree_text_frame,
            orient="vertical",
            command=self.tree_text.yview
        )

        scroll_y.pack(
            side="right",
            fill="y"
        )

        scrollbar_frame = ttk.Frame(self.pprint_tab)

        scrollbar_frame.pack(
            padx=10,
            pady=5,
            fill="x"
        )

        scroll_x = ttk.Scrollbar(
            scrollbar_frame,
            orient="horizontal",
            command=self.tree_text.xview
        )

        scroll_x.pack(
            side="bottom",
            fill="x"
        )

        self.tree_text.config(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set
        )

        # ---------------- BUTTONS ----------------
        ttk.Button(
            self.pprint_tab,
            text="Copy Tree to Clipboard",
            command=self.copy_tree_to_clipboard
        ).pack(pady=10)

        ttk.Button(
            self.pprint_tab,
            text="Print Tree Content",
            command=self.print_tree_content
        ).pack(pady=10)

    # -------------------
    # NUMERIC SORT
    # -------------------
    def numerical_sort(self, value):

        parts = re.split(r'(\d+)', value)

        return [
            int(p) if p.isdigit()
            else p.lower()
            for p in parts
        ]

    # -------------------
    # CHOOSE FOLDER
    # -------------------
    def choose_folder(self):

        return filedialog.askdirectory(
            title="Select a folder"
        )

    # -------------------
    # CHOOSE PRINT FOLDER
    # -------------------
    def choose_print_folder(self):

        folder = self.choose_folder()

        if folder:

            self.current_folder = folder

            print(
                "Folder selected:",
                self.current_folder
            )

    # -------------------
    # UPDATE IGNORED
    # -------------------
    def update_ignored_files(self):

        ignored_files_str = (
            self.ignored_files_entry.get().strip()
        )

        ignored_folders_str = (
            self.ignored_folders_entry.get().strip()
        )

        ignored_extensions_str = (
            self.ignored_extensions_entry.get().strip()
        )

        self.IGNORED_FILES = set(
            ignored_files_str.split(",")
        )

        self.IGNORED_FOLDERS = set(
            ignored_folders_str.split(",")
        )

        self.IGNORED_EXTENSIONS = [
            ext.strip().lstrip(".")
            for ext in ignored_extensions_str.split(",")
            if ext.strip()
        ]

        print("Updated ignored items.")

    # -------------------
    # COPY TO CLIPBOARD
    # -------------------
    def copy_tree_to_clipboard(self):

        tree_content = self.tree_text.get(
            "1.0",
            tk.END
        ).strip()

        if tree_content:

            self.root.clipboard_clear()

            self.root.clipboard_append(
                tree_content
            )

            messagebox.showinfo(
                "Success",
                "Tree copied to clipboard."
            )

        else:

            messagebox.showwarning(
                "No content",
                "No content to copy."
            )

    # -------------------
    # PRINT TREE CONTENT
    # -------------------
    def print_tree_content(self):

        if not self.current_folder:

            messagebox.showwarning(
                "No folder selected",
                "Please choose a folder first."
            )

            return

        self.tree_text.delete(
            1.0,
            tk.END
        )

        root_name = os.path.basename(
            self.current_folder.rstrip("/\\")
        )

        self.tree_text.insert(
            tk.END,
            root_name + "/\n"
        )

        self.print_tree(self.current_folder)

    # -------------------
    # PRINT TREE
    # -------------------
    def print_tree(self, path, prefix=""):

        try:

            items = sorted(
                os.listdir(path),
                key=self.numerical_sort
            )

        except PermissionError:
            return

        items = [
            i for i in items
            if i not in self.IGNORED_FILES
            and i not in self.IGNORED_FOLDERS
            and not i.startswith(".")
        ]

        items = [
            i for i in items
            if not any(
                i.endswith(ext)
                for ext in self.IGNORED_EXTENSIONS
            )
        ]

        files = [
            i for i in items
            if os.path.isfile(
                os.path.join(path, i)
            )
        ]

        folders = [
            i for i in items
            if os.path.isdir(
                os.path.join(path, i)
            )
        ]

        # ---------------- FILES ----------------
        for i, file_name in enumerate(files):

            is_last_file = (
                i == len(files) - 1
                and not folders
            )

            connector = (
                "└── "
                if is_last_file
                else "├── "
            )

            self.tree_text.insert(
                tk.END,
                prefix
                + connector
                + file_name.replace("\\", "/")
                + "\n"
            )

        # ---------------- FOLDERS ----------------
        for idx, folder_name in enumerate(folders):

            folder_path = os.path.join(
                path,
                folder_name
            )

            if idx > 0 or files:

                self.tree_text.insert(
                    tk.END,
                    prefix + "│\n"
                )

            self.tree_text.insert(
                tk.END,
                prefix
                + (
                    "└── "
                    if idx == len(folders) - 1
                    else "├── "
                )
                + folder_name.replace("\\", "/")
                + "/\n"
            )

            new_prefix = prefix + (
                "    "
                if idx == len(folders) - 1
                else "│   "
            )

            self.print_tree(
                folder_path,
                new_prefix
            )