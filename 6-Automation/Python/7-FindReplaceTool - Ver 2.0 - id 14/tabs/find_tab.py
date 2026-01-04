from tkinter import filedialog
from gui.find_tab_gui import FindTabGUI
from utils.file_search import search_path, display_results, run_search_file_paths_only
from utils.insert_utils import insert_all_files
from utils.paste_word_text import paste_word_selection_into_text
from utils.file_replace import run_replace_process
import tkinter.font as tkFont
import tkinter.messagebox as messagebox

WORD_TO_COLOR = {
    "Black": "#000000", "Blue": "#0000FF", "Turquoise": "#00FFFF",
    "Bright Green": "#00FF00", "Pink": "#FFC0CB", "Red": "#FF0000",
    "Yellow": "#FFFF00", "White": "#FFFFFF", "Dark Blue": "#00008B",
    "Teal": "#008080", "Green": "#008000", "Violet": "#EE82EE",
    "Dark Red": "#8B0000", "Dark Yellow": "#9B870C",
    "Gray50": "#808080", "Gray25": "#C0C0C0", "None": None
}


class FindTab:
    def __init__(self, parent):
        self.parent = parent
        self.gui = FindTabGUI(
            parent,
            browse_callback=self.browse_path,
            run_callback=self.run_search,
            replace_callback=self.apply_replace,
            paste_callback=self.paste_text_to_replace,
            clear_callback=self.clear_results,
            matches_only_callback=self.run_search_matches_only,
            paths_only_callback=self.run_search_file_paths_only,
            insert_callback=self.apply_insert
        )
        
        self.selected_path_type = None

        # -------------------- Bind Ctrl+V / Shift+Insert to custom paste only --------------------
        replace_widget = self.gui.replace_text

        # Remove class-level Ctrl+V binding to prevent normal paste
        replace_widget.unbind_class("Text", "<Control-v>")

        # Bind at widget level
        replace_widget.bind("<Control-v>", self._custom_paste, add=True)
        replace_widget.bind("<Shift-Insert>", self._custom_paste, add=True)

        # Block OS-level default paste
        replace_widget.bind("<<Paste>>", lambda e: "break", add=True)


    def _custom_paste(self, event):
        self.paste_text_to_replace()
        return "break"  # Prevent normal paste


    # -------------------- Browse Path --------------------
    def browse_path(self):
        path_type = self.gui.selected_type.get()
        if path_type == "file":
            path = filedialog.askopenfilename(
                filetypes=[("All Files", "*.*"), ("Text files", "*.txt"), ("Word files", "*.docx")]
            )
        else:
            path = filedialog.askdirectory()

        if path:
            self.gui.entry_path.delete(0, "end")
            self.gui.entry_path.insert(0, path)

    # -------------------- Run Search --------------------
    def run_search(self):
        search_text = self.gui.entry_search_text.get()
        if not search_text:
            from tkinter import messagebox
            messagebox.showwarning("Empty Find Field", "The Find field is empty.")
            return

        results = search_path(
            path=self.gui.entry_path.get(),
            search_text=search_text,
            selected_type=self.gui.selected_type.get(),
            case_sensitive=self.gui.case_sensitive_var.get(),
            use_regex=self.gui.enable_regex_var.get(),
            search_subfolders=self.gui.subfolders_var.get(),
            txt_only=self.gui.txt_var.get(),
            doc_only=self.gui.doc_var.get(),
            pdf_only=self.gui.pdf_var.get(),
            content_type=self.gui.content_type_var.get()
        )

        display_results(self.gui, results)

    
    def run_search_matches_only(self):
        search_text = self.gui.entry_search_text.get()
        if not search_text:
            from tkinter import messagebox
            messagebox.showwarning("Empty Find Field", "The Find field is empty.")
            return

        # Run the search using the refactored function
        results = search_path(
            path=self.gui.entry_path.get(),
            search_text=search_text,
            selected_type=self.gui.selected_type.get(),
            case_sensitive=self.gui.case_sensitive_var.get(),
            use_regex=self.gui.enable_regex_var.get(),
            search_subfolders=self.gui.subfolders_var.get(),
            txt_only=self.gui.txt_var.get(),
            doc_only=self.gui.doc_var.get(),
            pdf_only=self.gui.pdf_var.get(),
            content_type=self.gui.content_type_var.get()
        )

        # Filter results to only include files with matches
        matches_only = [r for r in results if r["file_find_count"] > 0]

        # Display matches only
        display_results(self.gui, matches_only)



    # In your FindTab class
    def run_search_file_paths_only(self):
        run_search_file_paths_only(
            gui=self.gui,
            path=self.gui.entry_path.get(),
            search_text=self.gui.entry_search_text.get(),
            selected_type=self.gui.selected_type.get(),
            case_sensitive=self.gui.case_sensitive_var.get(),
            use_regex=self.gui.enable_regex_var.get(),
            search_subfolders=self.gui.subfolders_var.get(),
            txt_only=self.gui.txt_var.get(),
            doc_only=self.gui.doc_var.get(),
            pdf_only=self.gui.pdf_var.get()
        )

    def paste_text_to_replace(self):
        # Show loading message
        self.gui.replace_text.config(state="normal")
        self.gui.replace_text.delete("1.0", "end")
        self.gui.replace_text.insert("1.0", "Loading...")
        self.gui.replace_text.update_idletasks()  # Refresh the UI  
        """
        Paste Word selection into Replace Text field with formatting
        """
        paste_word_selection_into_text(self.gui.replace_text)

    # -------------------- Apply Replace --------------------
    def apply_replace(self):
        find_text = self.gui.entry_search_text.get()
        if find_text == "":
            messagebox.showwarning("Empty Find Field", "The Find field is empty.")
            return

        run_replace_process(
            gui=self.gui,
            path=self.gui.entry_path.get(),
            is_file=(self.gui.selected_type.get() == "file"),
            find_text=find_text,
            tk_replace_widget=self.gui.replace_text,
            case_sensitive=self.gui.case_sensitive_var.get(),
            regex=self.gui.enable_regex_var.get(),
            include_subfolders=self.gui.subfolders_var.get(),
            txt=self.gui.txt_var.get(),
            doc=self.gui.doc_var.get(),
            pdf=self.gui.pdf_var.get(),
            content_type=self.gui.content_type_var.get()
        )


    def clear_results(self):
        self.gui.text_results.config(state="normal")
        self.gui.text_results.delete("1.0", "end")
        self.gui.text_results.config(state="disabled")
        self.gui.status_label.config(text="")

    def apply_insert(self):
        gui = self.gui

        total, per_file = insert_all_files(gui)

        gui.text_results.config(state="normal")
        gui.text_results.delete("1.0", "end")  # clear previous results
        for file_path, count in per_file:
            gui.text_results.insert("end", f"{file_path} ({count} insertions)\n")
        gui.text_results.config(state="disabled")

        gui.status_label.config(text=f"Insert complete ({total} insertions)", fg="green")
