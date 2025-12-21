import tkinter as tk
from tkinter import colorchooser, font

class FindTabGUI:
    """
    Handles building the Find tab GUI with scrollable full-width layout.
    Uses tk.Text with tags for rich-text Replace box.
    """

    def __init__(self, parent, browse_callback=None, run_callback=None,
                 replace_callback=None, paste_callback=None, clear_callback=None, matches_only_callback=None, paths_only_callback=None):
        self.parent = parent
        self.browse_callback = browse_callback
        self.run_callback = run_callback
        self.replace_callback = replace_callback
        self.paste_callback = paste_callback
        self.clear_callback = clear_callback
        self.matches_only_callback = matches_only_callback
        self.paths_only_callback = paths_only_callback
    

        # Variables
        self.selected_type = tk.StringVar(value="file")
        self.previous_type = self.selected_type.get()
        self.case_sensitive_var = tk.BooleanVar()
        self.subfolders_var = tk.BooleanVar()
        self.enable_regex_var = tk.BooleanVar()
        self.doc_var = tk.BooleanVar()
        self.txt_var = tk.BooleanVar()
        self.pdf_var = tk.BooleanVar()

        # Replace formatting variables
        self.font_family_var = tk.StringVar(value="Arial")
        self.font_size_var = tk.IntVar(value=12)
        self.bold_var = tk.BooleanVar()
        self.italic_var = tk.BooleanVar()
        self.font_color = tk.StringVar(value="black")
        self.highlight_color = tk.StringVar(value="yellow")

        self.build_gui()

    # ----------------- GUI BUILD -----------------
    def build_gui(self):
        # --- Scrollable canvas setup ---
        self.canvas = tk.Canvas(self.parent)
        self.scrollbar = tk.Scrollbar(self.parent, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        # Frame inside canvas
        self.frame = tk.Frame(self.canvas)
        self.frame_window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")

        # Scroll region
        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        # Expand columns
        for col in range(4):
            self.frame.columnconfigure(col, weight=1)

        parent = self.frame

        # --- Section 1: Select Type ---
        tk.Label(parent, text="1. Select Type", font=("Arial", 12, "bold")).grid(
            row=0, column=0, columnspan=3, padx=10, pady=(10,5), sticky="w")
        tk.Radiobutton(parent, text="File", variable=self.selected_type, value="file",
                    command=self.update_attributes_state).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        tk.Radiobutton(parent, text="Folder", variable=self.selected_type, value="folder",
                    command=self.update_attributes_state).grid(row=1, column=1, padx=10, pady=5, sticky="w")

        # --- Section 2: Choose Path ---
        tk.Label(parent, text="2. Choose Path", font=("Arial", 12, "bold")).grid(
            row=2, column=0, columnspan=4, padx=10, pady=(20,5), sticky="w")
        self.entry_path = tk.Entry(parent)
        self.entry_path.grid(row=3, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        self.button_browse = tk.Button(parent, text="Browse", command=self.browse_callback)
        self.button_browse.grid(row=3, column=3, padx=10, pady=5, sticky="w")

        # --- Section 3: Attributes ---
        tk.Label(parent, text="3. Select Attributes", font=("Arial", 12, "bold")).grid(
            row=4, column=0, columnspan=4, padx=10, pady=(20,5), sticky="w")
        self.checkbox_case = tk.Checkbutton(parent, text="Case Sensitive", variable=self.case_sensitive_var)
        self.checkbox_case.grid(row=5, column=0, padx=10, pady=5, sticky="w")
        self.checkbox_subfolders = tk.Checkbutton(parent, text="Search Subfolders", variable=self.subfolders_var)
        self.checkbox_subfolders.grid(row=5, column=1, padx=10, pady=5, sticky="w")
        self.checkbox_regex = tk.Checkbutton(parent, text="Enable Regex", variable=self.enable_regex_var)
        self.checkbox_regex.grid(row=5, column=2, padx=10, pady=5, sticky="w")

        # --- Section 4: File Types ---
        tk.Label(parent, text="4. Select File Types (for folders)", font=("Arial", 12, "bold")).grid(
            row=6, column=0, columnspan=4, padx=10, pady=(20,5), sticky="w")
        self.checkbox_doc = tk.Checkbutton(parent, text=".doc", variable=self.doc_var)
        self.checkbox_doc.grid(row=7, column=0, padx=10, pady=5, sticky="w")
        self.checkbox_txt = tk.Checkbutton(parent, text=".txt", variable=self.txt_var)
        self.checkbox_txt.grid(row=7, column=1, padx=10, pady=5, sticky="w")
        self.checkbox_pdf = tk.Checkbutton(parent, text=".pdf", variable=self.pdf_var)
        self.checkbox_pdf.grid(row=7, column=2, padx=10, pady=5, sticky="w")

        self.update_attributes_state()

        # --- Section 5: Text to Find ---
        tk.Label(parent, text="5. Enter Text to Find", font=("Arial", 12, "bold")).grid(
            row=8, column=0, columnspan=4, padx=10, pady=(20,5), sticky="w")
        self.entry_search_text = tk.Entry(parent)
        self.entry_search_text.grid(row=9, column=0, columnspan=4, padx=10, pady=5, sticky="ew")

        # --- Section 6: Replace Text ---
        tk.Label(parent, text="6. Replace Text (Formatting Options)", font=("Arial", 12, "bold")).grid(
            row=10, column=0, columnspan=4, padx=10, pady=(20,5), sticky="w")
        self.replace_text = tk.Text(parent, height=10, wrap="word")
        self.replace_text.grid(row=11, column=0, columnspan=4, padx=10, pady=5, sticky="nsew")
        self.frame.rowconfigure(11, weight=1)

        self.replace_text.tag_configure("bold", font=("Arial", 12, "bold"))
        self.replace_text.tag_configure("italic", font=("Arial", 12, "italic"))
        self.replace_text.tag_configure("highlight", background=self.highlight_color.get())
        self.replace_text.tag_configure("color", foreground=self.font_color.get())

        # Buttons frame for Replace and Paste
        self.replace_buttons_frame = tk.Frame(parent)
        self.replace_buttons_frame.grid(row=12, column=0, columnspan=4, padx=10, pady=5, sticky="w")
        self.button_replace = tk.Button(self.replace_buttons_frame, text="Apply Replace", command=self.replace_callback)
        self.button_replace.pack(side="left", padx=(0,10))
        self.button_paste = tk.Button(self.replace_buttons_frame, text="Paste", command=self.paste_callback)
        self.button_paste.pack(side="left")

        # --- Section 7: Results ---
        tk.Label(parent, text="7. Results", font=("Arial", 12, "bold")).grid(
            row=13, column=0, columnspan=4, padx=10, pady=(20,5), sticky="w")
        self.text_results = tk.Text(parent, height=15, state="disabled", wrap="none")
        self.text_results.grid(row=14, column=0, columnspan=4, padx=10, pady=5, sticky="nsew")
        self.frame.rowconfigure(14, weight=2)

        self.scrollbar_results = tk.Scrollbar(parent, command=self.text_results.yview)
        self.scrollbar_results.grid(row=14, column=4, sticky="ns", pady=5)
        self.text_results.config(yscrollcommand=self.scrollbar_results.set)

        self.scrollbar_h = tk.Scrollbar(parent, orient="horizontal", command=self.text_results.xview)
        self.scrollbar_h.grid(row=15, column=0, columnspan=4, sticky="ew", padx=10)
        self.text_results.config(xscrollcommand=self.scrollbar_h.set)

        # --- Section 8: Search Buttons ---
        self.buttons_frame = tk.Frame(parent)
        self.buttons_frame.grid(row=16, column=0, columnspan=4, padx=10, pady=5, sticky="w")

        self.button_run = tk.Button(self.buttons_frame, text="Run Search", command=self.run_callback)
        self.button_run.pack(side="left", padx=(0,5))

        self.button_matches_only = tk.Button(self.buttons_frame, text="Search (Matches Only)", command=self.matches_only_callback)
        self.button_matches_only.pack(side="left", padx=(0,5))

        self.button_search_file_paths = tk.Button(
            self.buttons_frame,
            text="Search File Paths Only",
            command=self.paths_only_callback
        )
        self.button_search_file_paths.pack(side="left", padx=(0,5))

        self.button_clear = tk.Button(self.buttons_frame, text="Clear Results", command=self.clear_callback)
        self.button_clear.pack(side="left", padx=(10,0))

        # Status Label
        self.status_label = tk.Label(parent, text="", fg="blue")
        self.status_label.grid(row=17, column=0, columnspan=4, padx=10, pady=10, sticky="w")

    # ----------------- SCROLL ADJUST -----------------
    def on_canvas_resize(self, event):
        self.canvas.itemconfig(self.frame_window, width=event.width)

    # ----------------- ATTRIBUTE STATE -----------------
    def update_attributes_state(self):
        selected = self.selected_type.get()
        if selected != self.previous_type:
            self.entry_path.delete(0, "end")
            self.previous_type = selected

        if selected == "folder":
            self.checkbox_subfolders.config(state="normal")
        else:
            self.checkbox_subfolders.config(state="disabled")
            self.subfolders_var.set(False)

        state = "normal" if selected == "folder" else "disabled"
        if state == "disabled":
            self.doc_var.set(False)
            self.txt_var.set(False)
            self.pdf_var.set(False)

        self.checkbox_doc.config(state=state)
        self.checkbox_txt.config(state=state)
        self.checkbox_pdf.config(state=state)

    def update_filetypes_state(self):
        if self.selected_type.get() == "folder":
            state = "normal"
        else:
            state = "disabled"
            self.doc_var.set(False)
            self.txt_var.set(False)
            self.pdf_var.set(False)

        self.checkbox_doc.config(state=state)
        self.checkbox_txt.config(state=state)
        self.checkbox_pdf.config(state=state)
