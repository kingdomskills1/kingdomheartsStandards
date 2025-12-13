from tkinter import filedialog
from gui.find_tab_gui import FindTabGUI
from utils.file_search import run_search_in_path
import tkinter.font as tkFont
from utils.paste_word_text import paste_word_selection_into_text
from utils.file_replace import run_replace_process

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
            paste_callback=self.paste_text_to_replace
        )
        self.selected_path_type = None

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
        try:
            run_search_in_path(
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
        except Exception as e:
            self.gui.text_results.config(state="normal")
            self.gui.text_results.insert("end", f"Error during search: {e}\n")
            self.gui.text_results.config(state="disabled")

    def paste_text_to_replace(self):
        """
        Paste Word selection into Replace Text field with formatting
        """
        paste_word_selection_into_text(self.gui.replace_text)

    # -------------------- Apply Replace --------------------
    def apply_replace(self):
        run_replace_process(
            gui=self.gui,
            path=self.gui.entry_path.get(),
            is_file=(self.gui.selected_type.get() == "file"),
            find_text=self.gui.entry_search_text.get(),
            tk_replace_widget=self.gui.replace_text,
            case_sensitive=self.gui.case_sensitive_var.get(),
            regex=self.gui.enable_regex_var.get(),
            include_subfolders=self.gui.subfolders_var.get(),
            txt=self.gui.txt_var.get(),
            doc=self.gui.doc_var.get(),
            pdf=self.gui.pdf_var.get()
        )
