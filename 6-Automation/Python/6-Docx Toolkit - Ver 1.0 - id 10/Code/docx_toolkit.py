"""GUI for selecting a folder or file, previewing numbered headings, and copying them.

Simple Tkinter-based UI that uses the functions from `docx_toolkit_core.py`.
"""
from pathlib import Path
import sys
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from docx_toolkit_core import (
    _numbered_heading_indices,
    extract_headings_from_docx,
    extract_headings_with_sources_from_docx,
    format_source_summary,
    format_sources,
    number_headings,
    save_heading_level_changes,
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
        self.title("DOCX Toolkit")
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
            text="Resize DOCX",
            command=self.open_docx_shrinker
        ).pack(side="left", padx=4, pady=4)

        preview_panes = ttk.Panedwindow(right_frame, orient=tk.VERTICAL)
        preview_panes.pack(fill="both", expand=True)

        headings_frame = ttk.Frame(preview_panes)
        sources_frame = ttk.Frame(preview_panes)
        preview_panes.add(headings_frame, weight=3)
        preview_panes.add(sources_frame, weight=2)

        headings_title = ttk.Frame(headings_frame)
        headings_title.pack(fill="x")
        ttk.Label(headings_title, text="Headings").pack(side="left")
        ttk.Button(
            headings_title,
            text="Up",
            width=6,
            command=self.scroll_headings_upper
        ).pack(side="left", padx=(8, 4))
        ttk.Button(
            headings_title,
            text="Down",
            width=6,
            command=self.scroll_headings_lower
        ).pack(side="left")
        self.txt_preview = tk.Text(headings_frame, wrap="word", height=12)
        self.txt_preview.pack(fill="both", expand=True)
        self.txt_preview.tag_configure("selected", background="#fff2cc")
        self.txt_preview.bind("<Double-Button-1>", self.on_heading_double_click)
        self.txt_preview.bind("<Button-3>", self.show_heading_context_menu)

        self.preview_context_menu = tk.Menu(self.txt_preview, tearoff=False)
        self.preview_context_menu.add_command(
            label="Copy Selected",
            command=self.copy_selected_preview_text
        )
        self.preview_context_menu.add_command(
            label="Copy All",
            command=self.copy_preview_for_selected_file
        )

        heading_buttons = ttk.Frame(headings_frame)
        heading_buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(heading_buttons, text="Copy", command=self.copy_preview_for_selected_file).pack(side="left", padx=4)
        ttk.Button(heading_buttons, text="Promote", command=self.promote_selected_heading).pack(side="left", padx=(0, 4))
        ttk.Button(heading_buttons, text="Demote", command=self.demote_selected_heading).pack(side="left", padx=4)
        ttk.Button(heading_buttons, text="Save Changes", command=self.save_heading_changes).pack(side="left", padx=4)

        ttk.Label(heading_buttons, text="View:").pack(side="left", padx=(12, 4))
        self.view_selection = tk.StringVar(value="Knowledge View")
        self.btn_view = ttk.Menubutton(
            heading_buttons,
            textvariable=self.view_selection,
            width=18
        )
        self.btn_view.pack(side="left")

        self.view_menu = tk.Menu(self.btn_view, tearoff=False)
        self.btn_view.configure(menu=self.view_menu)
        self.view_menu.add_command(
            label="Knowledge View",
            command=lambda: self.select_view("Knowledge View")
        )

        headings_menu = tk.Menu(self.view_menu, tearoff=False)
        self.view_menu.add_cascade(label="Headings", menu=headings_menu)
        headings_menu.add_command(
            label="All Headings",
            command=lambda: self.select_view("All Headings")
        )
        for level in range(1, 10):
            headings_menu.add_command(
                label=f"H{level} View",
                command=lambda selected_level=level: self.select_view(
                    f"H{selected_level} View"
                )
            )

        sub_headings_menu = tk.Menu(self.view_menu, tearoff=False)
        self.view_menu.add_cascade(label="Sub Headings", menu=sub_headings_menu)
        for level in range(1, 10):
            sub_headings_menu.add_command(
                label=f"H{level} and Sub Headings",
                command=lambda selected_level=level: self.select_view(
                    f"H{selected_level} and Sub Headings"
                )
            )

        heading_level_menu = tk.Menu(self.view_menu, tearoff=False)
        self.view_menu.add_cascade(label="Heading Level", menu=heading_level_menu)
        for start_level in range(1, 10):
            start_menu = tk.Menu(heading_level_menu, tearoff=False)
            heading_level_menu.add_cascade(
                label=f"H{start_level}",
                menu=start_menu
            )
            for end_level in range(start_level, 10):
                start_menu.add_command(
                    label=f"H{start_level} to H{end_level}",
                    command=lambda start=start_level, end=end_level: self.select_view(
                        f"H{start} to H{end}"
                    )
                )

        self.lbl_selected_heading = ttk.Label(heading_buttons, text="Double-click a heading to select it")
        self.lbl_selected_heading.pack(side="left", padx=8)

        ttk.Separator(sources_frame, orient=tk.HORIZONTAL).pack(
            fill="x",
            padx=2,
            pady=(6, 6)
        )

        sources_title = ttk.Frame(sources_frame)
        sources_title.pack(fill="x")
        ttk.Label(sources_title, text="Sources").pack(side="left")
        ttk.Button(
            sources_title,
            text="Up",
            width=6,
            command=self.scroll_sources_upper
        ).pack(side="left", padx=(8, 4))
        ttk.Button(
            sources_title,
            text="Down",
            width=6,
            command=self.scroll_sources_lower
        ).pack(side="left")
        self.txt_sources = tk.Text(sources_frame, wrap="word", height=8)
        self.txt_sources.pack(fill="both", expand=True)
        self.txt_sources.bind("<Button-3>", self.show_sources_context_menu)

        self.sources_context_menu = tk.Menu(self.txt_sources, tearoff=False)
        self.sources_context_menu.add_command(
            label="Copy Selected",
            command=self.copy_selected_sources_text
        )
        self.sources_context_menu.add_command(
            label="Copy All",
            command=self.copy_sources
        )

        sources_view_buttons = ttk.Frame(sources_frame)
        sources_view_buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(
            sources_view_buttons,
            text="Copy",
            command=self.copy_sources
        ).pack(side="left", padx=(0, 8))
        ttk.Label(sources_view_buttons, text="View:").pack(side="left", padx=(0, 4))
        self.sources_view_selection = tk.StringVar(value="Sources")
        self.btn_sources_view = ttk.Menubutton(
            sources_view_buttons,
            textvariable=self.sources_view_selection,
            width=18
        )
        self.btn_sources_view.pack(side="left")

        self.sources_view_menu = tk.Menu(self.btn_sources_view, tearoff=False)
        self.btn_sources_view.configure(menu=self.sources_view_menu)
        self.sources_view_menu.add_command(
            label="Sources",
            command=lambda: self.select_sources_view("Sources")
        )
        self.sources_view_menu.add_command(
            label="Sources Summary",
            command=lambda: self.select_sources_view("Sources Summary")
        )

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

    def open_docx_shrinker(self):
        try:
            from shrink_docx import run_gui
        except ImportError as error:
            messagebox.showerror(
                "DOCX resizer unavailable",
                "Could not load the DOCX resizer. Install its dependency with "
                "'pip install Pillow'.\n\n{}".format(error),
                parent=self,
            )
            return

        selected = self.lst_files.curselection()
        initial_path = self.files[selected[0]] if selected else self.folder_path
        run_gui(self, initial_path)

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
        self.current_entries = extract_headings_with_sources_from_docx(path)
        self.original_heading_levels = [
            entry["level"] for entry in self.current_entries
        ]
        self.heading_edits = {}
        self.selected_heading_index = None
        entries = extract_headings_with_sources_from_docx(path)
        self.current_sources = [
            source for entry in entries for source in entry["sources"]
        ]
        self.txt_sources.delete("1.0", tk.END)
        self.refresh_heading_preview()
        self.lbl_selected_heading.config(text="Double-click a heading to select it")
        self.refresh_sources_view()

    def refresh_heading_preview(self):
        self.txt_preview.delete("1.0", tk.END)
        raw_headings = [
            (
                self.heading_edits.get(index, entry["level"]),
                entry["text"]
            )
            for index, entry in enumerate(self.current_entries)
        ]
        def renumber_visible(visible_indices, base_level):
            counters = [0] * 9
            visible_headings = []
            for heading_index in sorted(visible_indices):
                heading_level, text = raw_headings[heading_index]
                relative_level = max(1, heading_level - base_level + 1)

                counters[relative_level - 1] += 1
                for index in range(relative_level, 9):
                    counters[index] = 0

                num = ".".join(
                    str(counters[index])
                    for index in range(relative_level)
                )
                visible_headings.append(
                    (heading_index, heading_level, num, text)
                )
            return visible_headings

        selected_level = None
        view_name = self.view_selection.get()
        subtree_level = None
        range_start_level = None
        range_end_level = None
        if " to " in view_name:
            range_parts = view_name.replace("H", "").split(" to ")
            if len(range_parts) == 2:
                range_start_level = int(range_parts[0])
                range_end_level = int(range_parts[1])
        elif view_name.startswith("H") and view_name.endswith(" and Sub Headings"):
            subtree_level = int(view_name[1:].removesuffix(" and Sub Headings"))
        elif view_name.startswith("H") and view_name.endswith(" View"):
            selected_level = int(view_name[1:].removesuffix(" View"))

        if view_name == "All Headings":
            visible_indices = set(range(len(raw_headings)))
            visible_headings = renumber_visible(visible_indices, 1)
            self.current_numbered = [
                (level, num, text)
                for _, level, num, text in visible_headings
            ]
        elif view_name == "Knowledge View":
            numbered = number_headings(raw_headings)
            numbered_indices = _numbered_heading_indices(raw_headings)
            visible_headings = [
                (
                    numbered_indices[line_index],
                    level,
                    num,
                    text
                )
                for line_index, (level, num, text) in enumerate(numbered)
            ]
            self.current_numbered = numbered
        else:
            visible_indices = set()

            if selected_level is not None:
                visible_indices = {
                    heading_index
                    for heading_index, (heading_level, _) in enumerate(raw_headings)
                    if heading_level == selected_level
                }

            elif subtree_level is not None:
                for heading_index, (heading_level, _) in enumerate(raw_headings):
                    if heading_level != subtree_level:
                        continue

                    visible_indices.add(heading_index)
                    for descendant_index in range(
                        heading_index + 1,
                        len(raw_headings)
                    ):
                        descendant_level = raw_headings[descendant_index][0]
                        if descendant_level <= subtree_level:
                            break
                        visible_indices.add(descendant_index)

            elif range_start_level is not None and range_end_level is not None:
                visible_indices = {
                    heading_index
                    for heading_index, (heading_level, _) in enumerate(raw_headings)
                    if range_start_level <= heading_level <= range_end_level
                }

            base_level = 1
            if range_start_level is not None:
                base_level = range_start_level
            elif subtree_level is not None:
                base_level = subtree_level
            elif selected_level is not None:
                base_level = selected_level

            visible_headings = renumber_visible(visible_indices, base_level)
            self.current_numbered = [
                (level, num, text)
                for _, level, num, text in visible_headings
            ]

        self.preview_heading_indices = [
            heading_index for heading_index, _, _, _ in visible_headings
        ]

        for line_index, (heading_index, level, num, text) in enumerate(
            visible_headings
        ):
            line = self.format_heading_for_view(level, num, text)
            start = f"{line_index + 1}.0"
            self.txt_preview.insert(tk.END, f"{line}\n")
            end = f"{line_index + 1}.end"
            if heading_index == self.selected_heading_index:
                self.txt_preview.tag_add("selected", start, end)

    def format_heading_for_view(self, level, number, text):
        view_name = self.view_selection.get()
        if view_name.endswith(" and Sub Headings"):
            subtree_level = int(view_name[1:].removesuffix(" and Sub Headings"))
            relative_level = max(0, level - subtree_level)
            indent = "   " * relative_level
            clean_text = re.sub(r"[ \t]+", " ", text).strip()
            clean_text = re.sub(r"\s+", " ", clean_text).strip()
            return f"{indent}{number}-{clean_text}"
        if " to " in view_name:
            range_parts = view_name.replace("H", "").split(" to ")
            if len(range_parts) == 2:
                range_start = int(range_parts[0])
                relative_level = max(0, level - range_start)
                indent = "   " * relative_level
                clean_text = re.sub(r"[ \t]+", " ", text).strip()
                clean_text = re.sub(r"\s+", " ", clean_text).strip()
                return f"{indent}{number}-{clean_text}"
        if (
            view_name == "Knowledge View"
            or view_name == "All Headings"
        ):
            indent = "   " * (level - 1)
            return f"{indent}{number}-{text}"
        return f"{number}-{text}"

    def select_view(self, view_name):
        self.view_selection.set(view_name)
        if hasattr(self, "current_entries"):
            self.refresh_heading_preview()

    def show_heading_context_menu(self, event=None):
        self.txt_preview.focus_set()
        if event is not None:
            try:
                self.preview_context_menu.tk_popup(
                    event.x_root,
                    event.y_root
                )
            finally:
                self.preview_context_menu.grab_release()

    def copy_selected_preview_text(self):
        text = ""
        try:
            text = self.txt_preview.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
        except tk.TclError:
            selected_ranges = self.txt_preview.tag_ranges("selected")
            if selected_ranges:
                text = self.txt_preview.get(
                    selected_ranges[0],
                    selected_ranges[1]
                ).strip()

        if text:
            self.clipboard_clear()
            self.clipboard_append(text)

    def on_heading_double_click(self, event=None):
        if not hasattr(self, "preview_heading_indices"):
            return
        click_index = self.txt_preview.index("@%d,%d" % (event.x, event.y))
        line_index = int(click_index.split(".", 1)[0]) - 1
        if line_index < 0 or line_index >= len(self.preview_heading_indices):
            return

        self.selected_heading_index = self.preview_heading_indices[line_index]
        entry = self.current_entries[self.selected_heading_index]
        level = self.heading_edits.get(
            self.selected_heading_index,
            entry["level"]
        )
        self.lbl_selected_heading.config(
            text=f"Selected: Heading {level} - {entry['text']}"
        )
        self.refresh_heading_preview()

    def change_selected_heading_level(self, amount: int):
        if self.selected_heading_index is None:
            messagebox.showinfo("No Heading Selected", "Double-click a heading first.")
            return

        entry = self.current_entries[self.selected_heading_index]
        level = self.heading_edits.get(
            self.selected_heading_index,
            self.original_heading_levels[self.selected_heading_index]
        )
        selected_original_level = self.original_heading_levels[
            self.selected_heading_index
        ]

        changed = False
        for heading_index, original_level in enumerate(
            self.original_heading_levels
        ):
            if heading_index < self.selected_heading_index:
                continue
            if heading_index > self.selected_heading_index:
                if original_level <= selected_original_level:
                    break

            current_level = self.heading_edits.get(
                heading_index,
                original_level
            )
            new_level = max(1, min(9, current_level + amount))
            if new_level != current_level:
                self.heading_edits[heading_index] = new_level
                changed = True

        if not changed:
            return

        new_level = self.heading_edits.get(
            self.selected_heading_index,
            selected_original_level
        )
        self.lbl_selected_heading.config(
            text=f"Selected: Heading {new_level} - {entry['text']}"
        )
        self.refresh_heading_preview()

    def promote_selected_heading(self):
        self.change_selected_heading_level(-1)

    def demote_selected_heading(self):
        self.change_selected_heading_level(1)

    def save_heading_changes(self):
        if not hasattr(self, "heading_edits") or not self.heading_edits:
            messagebox.showinfo("Nothing to Save", "Promote or demote a heading first.")
            return

        sel = self.lst_files.curselection()
        if not sel:
            return

        source = self.files[sel[0]]
        out_file = filedialog.asksaveasfilename(
            title="Save Heading Changes",
            initialdir=str(source.parent),
            initialfile=f"{source.stem}_edited.docx",
            defaultextension=".docx",
            filetypes=[("Word documents", "*.docx")]
        )
        if not out_file:
            return

        save_heading_level_changes(source, Path(out_file), self.heading_edits)
        messagebox.showinfo("Saved", f"Heading changes saved to:\n{out_file}")

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

    def scroll_headings_upper(self):
        self.txt_preview.see("1.0")
        self.txt_preview.mark_set("insert", "1.0")

    def scroll_headings_lower(self):
        self.txt_preview.see(tk.END)
        self.txt_preview.mark_set("insert", tk.END)

    def scroll_sources_upper(self):
        self.txt_sources.see("1.0")
        self.txt_sources.mark_set("insert", "1.0")

    def scroll_sources_lower(self):
        self.txt_sources.see(tk.END)
        self.txt_sources.mark_set("insert", tk.END)

    def select_sources_view(self, view_name):
        self.sources_view_selection.set(view_name)
        self.refresh_sources_view()

    def refresh_sources_view(self):
        if not hasattr(self, "current_sources"):
            return

        self.txt_sources.delete("1.0", tk.END)
        if self.sources_view_selection.get() == "Sources Summary":
            text = format_source_summary(self.current_sources)
        else:
            text = format_sources(self.current_sources)
        self.txt_sources.insert(tk.END, text)

    def show_sources_context_menu(self, event=None):
        self.txt_sources.focus_set()
        if event is not None:
            try:
                self.sources_context_menu.tk_popup(
                    event.x_root,
                    event.y_root
                )
            finally:
                self.sources_context_menu.grab_release()

    def copy_selected_sources_text(self):
        try:
            text = self.txt_sources.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
        except tk.TclError:
            text = ""

        if text:
            self.clipboard_clear()
            self.clipboard_append(text)

    def copy_sources(self):
        if not hasattr(self, "current_sources"):
            return

        text = self.txt_sources.get("1.0", tk.END).strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copied", "Sources view copied")

    def copy_source_summary(self):
        if not hasattr(self, "current_sources"):
            return

        self.clipboard_clear()
        self.clipboard_append(format_source_summary(self.current_sources))
        messagebox.showinfo("Copied", "Source summary copied")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli_main()
    else:
        HeadingGUI().mainloop()
