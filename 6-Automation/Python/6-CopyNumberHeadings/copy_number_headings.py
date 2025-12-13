"""GUI for selecting a folder or file, previewing numbered headings, and copying them.

Simple Tkinter-based UI that uses the functions from `copy_number_headings.py`.
"""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from copy_number_headings_core import (
    extract_headings_from_docx,
    number_headings,
    write_numbered_docx,
    process_path,
    main as cli_main,
)


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

        btn_select = ttk.Button(frm_top, text="Select Folder", command=self.select_folder)
        btn_select.pack(side="left")

        self.lbl_folder = ttk.Label(frm_top, text="No folder selected")
        self.lbl_folder.pack(side="left", padx=8)

        btn_refresh = ttk.Button(frm_top, text="Refresh", command=self.refresh_file_list)
        btn_refresh.pack(side="right")

        # Main pane: file list on left, headings preview on right
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        left_frame = ttk.Frame(paned)
        right_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        paned.add(right_frame, weight=3)

        lbl_files = ttk.Label(left_frame, text=".docx files")
        lbl_files.pack(anchor="w")

        self.lst_files = tk.Listbox(left_frame, exportselection=False)
        self.lst_files.pack(fill="both", expand=True)
        self.lst_files.bind("<<ListboxSelect>>", self.on_file_select)

        # Buttons under file list
        frm_left_buttons = ttk.Frame(left_frame)
        frm_left_buttons.pack(fill="x")
        btn_copy_all = ttk.Button(frm_left_buttons, text="Copy All Headings", command=self.copy_all)
        btn_copy_all.pack(side="left", padx=4, pady=4)

        btn_export = ttk.Button(frm_left_buttons, text="Export All to File", command=self.export_all)
        btn_export.pack(side="left", padx=4, pady=4)

        # Right: headings preview
        lbl_preview = ttk.Label(right_frame, text="Headings Preview")
        lbl_preview.pack(anchor="w")

        self.txt_preview = tk.Text(right_frame, wrap="word")
        self.txt_preview.pack(fill="both", expand=True)

        frm_right_buttons = ttk.Frame(right_frame)
        frm_right_buttons.pack(fill="x")

        btn_copy_selected = ttk.Button(frm_right_buttons, text="Copy Selected", command=self.copy_selected)
        btn_copy_selected.pack(side="left", padx=4, pady=4)

        self.chk_write_docx_var = tk.BooleanVar(value=False)
        chk_write = ttk.Checkbutton(frm_right_buttons, text="Write numbered .docx when exporting", variable=self.chk_write_docx_var)
        chk_write.pack(side="left", padx=8)

        btn_write_numbered = ttk.Button(frm_right_buttons, text="Write Numbered Docx", command=self.write_numbered_for_current)
        btn_write_numbered.pack(side="right", padx=4, pady=4)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.folder_path = Path(folder)
        self.lbl_folder.config(text=str(self.folder_path))
        self.refresh_file_list()

    def refresh_file_list(self):
        self.lst_files.delete(0, tk.END)
        self.files = []
        if not self.folder_path:
            return
        for p in sorted(self.folder_path.glob("*.docx")):
            self.files.append(p)
            self.lst_files.insert(tk.END, p.name)

    def on_file_select(self, event=None):
        sel = self.lst_files.curselection()
        if not sel:
            return
        idx = sel[0]
        path = self.files[idx]
        try:
            headings = extract_headings_from_docx(path)
            numbered = number_headings(headings)
            self.current_numbered = numbered
            self.txt_preview.delete("1.0", tk.END)
            for num, text in numbered:
                self.txt_preview.insert(tk.END, f"{num} {text}\n")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to extract headings: {e}")

    def copy_selected(self):
        try:
            sel = self.txt_preview.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            # no selection: copy current line
            idx = self.txt_preview.index("insert linestart")
            sel = self.txt_preview.get(idx, f"{idx} lineend")
        self.clipboard_clear()
        self.clipboard_append(sel)
        messagebox.showinfo("Copied", "Selected heading copied to clipboard")

    def copy_all(self):
        all_text = self.txt_preview.get("1.0", tk.END).strip()
        if not all_text:
            messagebox.showinfo("No headings", "No headings to copy")
            return
        self.clipboard_clear()
        self.clipboard_append(all_text)
        messagebox.showinfo("Copied", "All headings copied to clipboard")

    def export_all(self):
        if not hasattr(self, "current_numbered") or not self.current_numbered:
            messagebox.showinfo("No headings", "No headings to export")
            return
        out_file = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if not out_file:
            return
        out_path = Path(out_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for num, text in self.current_numbered:
                f.write(f"{num} {text}\n")
        messagebox.showinfo("Exported", f"Headings exported to {out_path}")
        # optionally write numbered docx
        if self.chk_write_docx_var.get():
            try:
                # write numbered .docx beside the text file
                # find the current selected file
                sel = self.lst_files.curselection()
                if not sel:
                    return
                idx = sel[0]
                path = self.files[idx]
                docx_out = out_path.with_suffix("_numbered.docx")
                write_numbered_docx(path, docx_out, self.current_numbered)
                messagebox.showinfo("Docx written", f"Numbered docx written to {docx_out}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to write numbered docx: {e}")

    def write_numbered_for_current(self):
        sel = self.lst_files.curselection()
        if not sel:
            messagebox.showinfo("No file", "Select a .docx file first")
            return
        idx = sel[0]
        path = self.files[idx]
        if not hasattr(self, "current_numbered") or not self.current_numbered:
            messagebox.showinfo("No headings", "No headings for selected file")
            return
        out_dir = filedialog.askdirectory(title="Select output folder for numbered docx")
        if not out_dir:
            return
        out_path = Path(out_dir) / (path.stem + "_numbered.docx")
        try:
            write_numbered_docx(path, out_path, self.current_numbered)
            messagebox.showinfo("Written", f"Numbered docx written to {out_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to write numbered docx: {e}")


if __name__ == "__main__":
    # If CLI arguments are provided, run the CLI entrypoint from the core module.
    # Otherwise launch the GUI.
    if len(sys.argv) > 1:
        cli_main()
    else:
        app = HeadingGUI()
        app.mainloop()
