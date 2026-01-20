"""GUI for selecting a folder or file, previewing numbered headings, and copying them.

Simple Tkinter-based UI that uses the functions from `copy_number_headings_core.py`.
"""
from pathlib import Path
import sys
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from copy_number_headings_core import (
    extract_headings_from_docx,
    number_headings,
    write_numbered_docx,
    main as cli_main,
)


def natural_sort_key(path: Path):
    """Sort strings with numbers in human order (2 < 10)."""
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r'(\d+)', path.name)
    ]


def clean_name(text: str) -> str:
    """Remove leading numbers and dash."""
    return re.sub(r'^\s*\d+(?:\.\d+)*\s*-\s*', '', text).strip()


class HeadingGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Copy & Number Headings")
        self.geometry("900x600")

        self.folder_path = None
        self.files = []

        self.create_widgets()

    def create_widgets(self):
        frm_top = ttk.Frame(self)
        frm_top.pack(fill="x", padx=8, pady=8)

        ttk.Button(frm_top, text="Select Folder", command=self.select_folder).pack(side="left")

        self.lbl_folder = ttk.Label(frm_top, text="No folder selected")
        self.lbl_folder.pack(side="left", padx=8)

        ttk.Button(frm_top, text="Refresh", command=self.refresh_file_list).pack(side="right")

        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        left_frame = ttk.Frame(paned)
        right_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        paned.add(right_frame, weight=3)

        ttk.Label(left_frame, text=".docx files").pack(anchor="w")

        self.lst_files = tk.Listbox(left_frame, exportselection=False)
        self.lst_files.pack(fill="both", expand=True)
        self.lst_files.bind("<<ListboxSelect>>", self.on_file_select)

        frm_left_buttons = ttk.Frame(left_frame)
        frm_left_buttons.pack(fill="x")

        ttk.Button(
            frm_left_buttons,
            text="Copy Clean File Name",
            command=self.copy_clean_filename
        ).pack(side="left", padx=4, pady=4)

        ttk.Button(
            frm_left_buttons,
            text="Copy Clean Folder Name",
            command=self.copy_clean_folder_name
        ).pack(side="left", padx=4, pady=4)

        ttk.Button(
            frm_left_buttons,
            text="Copy All Headings",
            command=self.copy_all
        ).pack(side="left", padx=4, pady=4)

        ttk.Button(
            frm_left_buttons,
            text="Export All to File",
            command=self.export_all
        ).pack(side="left", padx=4, pady=4)

        ttk.Label(right_frame, text="Headings Preview").pack(anchor="w")

        self.txt_preview = tk.Text(right_frame, wrap="word")
        self.txt_preview.pack(fill="both", expand=True)

        frm_right_buttons = ttk.Frame(right_frame)
        frm_right_buttons.pack(fill="x")

        ttk.Button(frm_right_buttons, text="Copy H1 Only", command=self.copy_h1_only).pack(side="left", padx=4)
        ttk.Button(frm_right_buttons, text="Copy H1 + H2", command=self.copy_h1_h2).pack(side="left", padx=4)
        ttk.Button(frm_right_buttons, text="Copy H1 + H2 + H3", command=self.copy_h1_h2_h3).pack(side="left", padx=4)
        ttk.Button(frm_right_buttons, text="Copy Preview", command=self.copy_preview_for_selected_file).pack(side="left", padx=4)

        self.chk_write_docx_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frm_right_buttons,
            text="Write numbered .docx when exporting",
            variable=self.chk_write_docx_var
        ).pack(side="left", padx=8)

        ttk.Button(
            frm_right_buttons,
            text="Write Numbered Docx",
            command=self.write_numbered_for_current
        ).pack(side="right", padx=4)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path = Path(folder)
            self.lbl_folder.config(text=str(self.folder_path))
            self.refresh_file_list()

    def copy_clean_folder_name(self):
        if not self.folder_path:
            return
        clean = clean_name(self.folder_path.name)
        self.clipboard_clear()
        self.clipboard_append(clean)
        messagebox.showinfo("Copied", "Clean folder name copied")

    def refresh_file_list(self):
        self.lst_files.delete(0, tk.END)
        self.files.clear()
        if not self.folder_path:
            return

        for p in sorted(self.folder_path.glob("*.docx"), key=natural_sort_key):
            if not p.name.startswith("~$"):
                self.files.append(p)
                self.lst_files.insert(tk.END, p.name)

    def on_file_select(self, event=None):
        sel = self.lst_files.curselection()
        if not sel:
            return
        path = self.files[sel[0]]
        headings = extract_headings_from_docx(path)
        self.current_numbered = number_headings(headings)

        self.txt_preview.delete("1.0", tk.END)
        for level, num, text in self.current_numbered:
            indent = "   " * (level - 1)
            self.txt_preview.insert(tk.END, f"{indent}{num}-{text}\n")

    def copy_clean_filename(self):
        sel = self.lst_files.curselection()
        if not sel:
            return
        name = clean_name(self.files[sel[0]].stem)
        self.clipboard_clear()
        self.clipboard_append(name)

    def copy_preview_for_selected_file(self):
        text = self.txt_preview.get("1.0", tk.END).strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)

    def copy_h1_only(self):
        self._copy_by_max_level(1, "Heading-1 copied")

    def copy_h1_h2(self):
        self._copy_by_max_level(2, "Heading-1 & Heading-2 copied")

    def copy_h1_h2_h3(self):
        self._copy_by_max_level(3, "Heading-1, Heading-2 & Heading-3 copied")

    def _copy_by_max_level(self, max_level: int, msg: str):
        if not hasattr(self, "current_numbered"):
            return

        lines = []
        for level, num, text in self.current_numbered:
            if level <= max_level:
                indent = "   " * (level - 1)
                lines.append(f"{indent}{num}-{text}")

        if not lines:
            return

        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        messagebox.showinfo("Copied", msg)

    def copy_all(self):
        self.copy_preview_for_selected_file()

    def export_all(self):
        if not hasattr(self, "current_numbered"):
            return

        out_file = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")]
        )
        if not out_file:
            return

        with open(out_file, "w", encoding="utf-8") as f:
            for level, num, text in self.current_numbered:
                indent = "   " * (level - 1)
                f.write(f"{indent}{num}-{text}\n")

        if self.chk_write_docx_var.get():
            idx = self.lst_files.curselection()[0]
            write_numbered_docx(
                self.files[idx],
                Path(out_file).with_suffix("_numbered.docx"),
                self.current_numbered
            )

    def write_numbered_for_current(self):
        sel = self.lst_files.curselection()
        if not sel:
            return
        out_dir = filedialog.askdirectory()
        if not out_dir:
            return
        path = self.files[sel[0]]
        out_path = Path(out_dir) / f"{path.stem}_numbered.docx"
        write_numbered_docx(path, out_path, self.current_numbered)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli_main()
    else:
        HeadingGUI().mainloop()
