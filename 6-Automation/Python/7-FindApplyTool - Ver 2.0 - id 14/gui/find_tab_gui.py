import tkinter as tk
from tkinter import colorchooser, font

class FindTabGUI:
    """
    Handles building the Find tab GUI with scrollable full-width layout.
    Uses tk.Text with tags for rich-text Replace box.
    """
    def __init__(self, parent,
                browse_callback=None,
                run_callback=None,
                replace_callback=None,
                paste_callback=None,
                clear_callback=None,
                matches_only_callback=None,
                paths_only_callback=None,
                insert_callback=None,
                remove_line_callback=None,
                remove_all_line_callback=None):
        
        self.parent = parent
        self.browse_callback = browse_callback
        self.run_callback = run_callback
        self.replace_callback = replace_callback
        self.paste_callback = paste_callback
        self.clear_callback = clear_callback
        self.matches_only_callback = matches_only_callback
        self.paths_only_callback = paths_only_callback
        self.insert_callback = insert_callback
        self.remove_line_callback = remove_line_callback
        self.remove_all_line_callback = remove_all_line_callback


        # ------------------ Variables ------------------
        self.selected_type = tk.StringVar(value="file")
        self.previous_type = self.selected_type.get()
        self.case_sensitive_var = tk.BooleanVar()
        self.subfolders_var = tk.BooleanVar()
        self.enable_regex_var = tk.BooleanVar()
        self.doc_var = tk.BooleanVar()
        self.txt_var = tk.BooleanVar()
        self.pdf_var = tk.BooleanVar()

        # Replace formatting
        self.font_family_var = tk.StringVar(value="Arial")
        self.font_size_var = tk.IntVar(value=12)
        self.bold_var = tk.BooleanVar()
        self.italic_var = tk.BooleanVar()
        self.font_color = tk.StringVar(value="black")
        self.highlight_color = tk.StringVar(value="yellow")

        # Content Type
        self.content_type_var = tk.StringVar(value="all")
        self.apply_heading_format_var = tk.BooleanVar(value=False)

        # ---------------- Insert Section Variables ----------------
        self.insert_position_var = tk.StringVar(value="before")
        self.insert_line_offset_var = tk.IntVar(value=0)
        self.insert_content_type_var = tk.StringVar(value="space")
        self.insert_content_text_var = tk.StringVar()
        self.insert_repeat_var = tk.IntVar(value=1)
        self.insert_reference_var = tk.StringVar(value="matched_line")  # Matched line or offset line

        # ---------------- Removed Section Variables ----------------
        self.Remvoed_position_var = tk.StringVar(value="before")

        # Build GUI
        self.build_gui()

    # ----------------- GUI BUILD -----------------
    def build_gui(self):
        import tkinter as tk

        # --- Scrollable Canvas ---
        self.canvas = tk.Canvas(self.parent)
        self.scrollbar = tk.Scrollbar(self.parent, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.frame = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")

        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(1, width=e.width))

        # Make columns expandable
        for col in range(5):
            self.frame.columnconfigure(col, weight=1)

        parent = self.frame

        # ---------------- 1. Select Type ----------------
        tk.Label(parent, text="1. Select Type", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w", padx=10)
        tk.Radiobutton(parent, text="File", variable=self.selected_type, value="file").grid(row=1, column=0, sticky="w", padx=10)
        tk.Radiobutton(parent, text="Folder", variable=self.selected_type, value="folder").grid(row=1, column=1, sticky="w")

        # ---------------- 2. Path ----------------
        tk.Label(parent, text="2. Choose Path", font=("Arial", 12, "bold")).grid(row=2, column=0, sticky="w", padx=10)
        self.entry_path = tk.Entry(parent)
        self.entry_path.grid(row=3, column=0, columnspan=4, sticky="ew", padx=10)
        tk.Button(parent, text="Browse", command=self.browse_callback).grid(row=3, column=4)

        # ---------------- 3. Attributes ----------------
        tk.Label(parent, text="3. Attributes", font=("Arial", 12, "bold")).grid(row=4, column=0, sticky="w", padx=10)
        tk.Checkbutton(parent, text="Case Sensitive", variable=self.case_sensitive_var).grid(row=5, column=0, sticky="w", padx=10)
        tk.Checkbutton(parent, text="Search Subfolders", variable=self.subfolders_var).grid(row=5, column=1, sticky="w")
        tk.Checkbutton(parent, text="Enable Regex", variable=self.enable_regex_var).grid(row=5, column=2, sticky="w")
        tk.Checkbutton(parent, text="Apply Default Heading Format", variable=self.apply_heading_format_var).grid(row=5, column=3, sticky="w")

        # ---------------- 4. File Types ----------------
        tk.Label(parent, text="4. File Types", font=("Arial", 12, "bold")).grid(row=6, column=0, sticky="w", padx=10)
        tk.Checkbutton(parent, text=".docx", variable=self.doc_var).grid(row=7, column=0, sticky="w", padx=10)
        tk.Checkbutton(parent, text=".txt", variable=self.txt_var).grid(row=7, column=1, sticky="w")
        tk.Checkbutton(parent, text=".pdf", variable=self.pdf_var).grid(row=7, column=2, sticky="w")

        # ---------------- 5. Content Type ----------------
        tk.Label(parent, text="5. Content Type", font=("Arial", 12, "bold")).grid(row=8, column=0, sticky="w", padx=10)
        tk.Radiobutton(parent, text="All", variable=self.content_type_var, value="all").grid(row=9, column=0, sticky="w", padx=10)
        tk.Radiobutton(parent, text="Text", variable=self.content_type_var, value="text").grid(row=9, column=1, sticky="w")
        tk.Radiobutton(parent, text="Tables", variable=self.content_type_var, value="tables").grid(row=9, column=2, sticky="w")
        tk.Radiobutton(parent, text="Headings", variable=self.content_type_var, value="headings").grid(row=9, column=3, sticky="w")
        tk.Radiobutton(parent, text="Tables + Headings", variable=self.content_type_var, value="tables_headings").grid(row=9, column=4, sticky="w")

        # ---------------- 6. Find ----------------
        tk.Label(parent, text="6. Find", font=("Arial", 12, "bold")).grid(row=10, column=0, sticky="w", padx=10)
        self.entry_search_text = tk.Entry(parent)
        self.entry_search_text.grid(row=11, column=0, columnspan=5, sticky="ew", padx=10)

        # ---- Find Buttons ----
        find_buttons = tk.Frame(parent)
        find_buttons.grid(row=12, column=0, columnspan=5, sticky="w", padx=10, pady=(5, 10))
        tk.Button(find_buttons, text="Run Search", command=self.run_callback).pack(side="left")
        tk.Button(find_buttons, text="Matches Only", command=self.matches_only_callback).pack(side="left", padx=5)
        tk.Button(find_buttons, text="Paths Only", command=self.paths_only_callback).pack(side="left", padx=5)

        # ---------------- 7. Replace ----------------
        tk.Label(parent, text="7. Replace", font=("Arial", 12, "bold")).grid(row=13, column=0, sticky="w", padx=10)
        self.replace_text = tk.Text(parent, height=8)
        self.replace_text.grid(row=14, column=0, columnspan=5, sticky="nsew", padx=10)
        replace_buttons = tk.Frame(parent)
        replace_buttons.grid(row=15, column=0, columnspan=5, sticky="w", padx=10)
        tk.Button(replace_buttons, text="Apply Replace", command=self.replace_callback).pack(side="left")
        tk.Button(replace_buttons, text="Paste", command=self.paste_callback).pack(side="left", padx=5)

        # ---------------- 8. Insert ----------------
        tk.Label(parent, text="8. Insert Content (Applied to Found Matches)", font=("Arial", 12, "bold")).grid(
            row=16, column=0, columnspan=5, padx=10, pady=(20, 5), sticky="w"
        )

        # ---- Position (Before / After) ----
        tk.Label(parent, text="Position").grid(row=17, column=0, padx=10, sticky="w")
        tk.Radiobutton(parent, text="Before", variable=self.insert_position_var, value="before").grid(row=17, column=1, sticky="w")
        tk.Radiobutton(parent, text="After", variable=self.insert_position_var, value="after").grid(row=17, column=2, sticky="w")

        # ---- Reference Position ----
        tk.Label(parent, text="Reference Position").grid(row=18, column=0, padx=10, sticky="w")
        self.radio_matched_line = tk.Radiobutton(parent, text="Matched Line",
                                                variable=self.insert_reference_var, value="matched_line")
        self.radio_matched_line.grid(row=18, column=1, sticky="w")
        self.radio_offset_line = tk.Radiobutton(parent, text="Matched Content",
                                                variable=self.insert_reference_var, value="matched_content")
        self.radio_offset_line.grid(row=18, column=2, sticky="w")

        # Callback to enable/disable Reference Position
        def update_reference_position_state(*args):
            if self.insert_line_offset_var.get() == 0:
                state = "normal"
            else:
                state = "disabled"
                self.insert_reference_var.set("offset_line")  # auto-set
            self.radio_matched_line.config(state=state)
            self.radio_offset_line.config(state=state)

        # ---- Insert Content Type ----
        tk.Label(parent, text="Insert Type").grid(row=19, column=0, padx=10, sticky="w")
        tk.Radiobutton(parent, text="Space", variable=self.insert_content_type_var, value="space",
                    command=self.update_insert_content_state).grid(row=19, column=1, sticky="w")
        tk.Radiobutton(parent, text="New Line", variable=self.insert_content_type_var, value="newline",
                    command=self.update_insert_content_state).grid(row=19, column=2, sticky="w")
        tk.Radiobutton(parent, text="Custom Content", variable=self.insert_content_type_var, value="content",
                    command=self.update_insert_content_state).grid(row=19, column=3, sticky="w")

        # ---- Insert Text Field ----
        tk.Label(parent, text="Insert Text").grid(row=20, column=0, padx=10, sticky="w")
        self.entry_insert_content = tk.Entry(parent, textvariable=self.insert_content_text_var, state="disabled")
        self.entry_insert_content.grid(row=20, column=1, columnspan=3, padx=10, sticky="ew")

        # ---- Repeat Count ----
        tk.Label(parent, text="Repeat Count").grid(row=21, column=0, padx=10, sticky="w")
        tk.Spinbox(parent, from_=1, to=100, width=6, textvariable=self.insert_repeat_var).grid(row=21, column=1, sticky="w")

        # ---- Apply Insert Button ----
        self.button_insert = tk.Button(parent, text="Apply Insert", command=self.insert_callback)
        self.button_insert.grid(row=22, column=0, columnspan=4, padx=10, pady=10, sticky="w")

        # ---------------- 9. Remvoed ----------------
        # ---- Remvoed Content Type ----
        tk.Label(parent, text="9. Remvoed Content Type (Applied to Found Matches)", font=("Arial", 12, "bold")).grid(
            row=23, column=0, columnspan=5, padx=10, pady=(20, 5), sticky="w"
        )

        # ---- Position (Before / After) ----
        tk.Label(parent, text="Position").grid(row=24, column=0, padx=10, sticky="w")
        tk.Radiobutton(parent, text="Before", variable=self.Remvoed_position_var, value="before").grid(row=24, column=1, sticky="w")
        tk.Radiobutton(parent, text="After", variable=self.Remvoed_position_var, value="after").grid(row=24, column=2, sticky="w")

        # Make only columns 2,3,4 expandable, leave 0 and 1 fixed for buttons
        for col in range(5):
            if col in (0, 1):  # columns with buttons
                self.frame.columnconfigure(col, weight=0)
            else:
                self.frame.columnconfigure(col, weight=1)

        # ---- Remove / Remove All Line Buttons ----
        self.button_remove_one = tk.Button(
            parent, text="Apply Remove Line Space", command=self.remove_line_callback
        )
        self.button_remove_one.grid(row=25, column=0, padx=(10, 5), pady=10, sticky="w")

        self.button_remove_all = tk.Button(
            parent, text="Apply Remove All Line Space", command=self.remove_all_line_callback
        )
        self.button_remove_all.grid(row=25, column=1, padx=(5, 10), pady=10, sticky="w")



        # ---------------- 10. Results ----------------
        tk.Label(parent, text="1. Results", font=("Arial", 12, "bold")).grid(
            row=26, column=0, sticky="w", padx=10
        )

        results_frame = tk.Frame(parent)
        results_frame.grid(row=27, column=0, columnspan=5, sticky="nsew", padx=10, pady=(0, 10))

        self.results_label = tk.Label(results_frame, text="", anchor="w", justify="left")
        self.results_label.pack(fill="both", expand=True)


        # Vertical scrollbar
        self.results_vscroll = tk.Scrollbar(results_frame, orient="vertical")
        self.results_vscroll.pack(side="right", fill="y")

        # Horizontal scrollbar
        self.results_hscroll = tk.Scrollbar(results_frame, orient="horizontal")
        self.results_hscroll.pack(side="bottom", fill="x")

        # Text widget
        self.text_results = tk.Text(
            results_frame,
            height=12,
            state="disabled",
            yscrollcommand=self.results_vscroll.set,
            xscrollcommand=self.results_hscroll.set,
            wrap="none"
        )
        self.text_results.pack(side="left", fill="both", expand=True)

        # Connect scrollbars
        self.results_vscroll.config(command=self.text_results.yview)
        self.results_hscroll.config(command=self.text_results.xview)

        # ---- Clear Button ----
        tk.Button(parent, text="Clear Results", command=self.clear_callback).grid(row=28, column=0, columnspan=5, sticky="w", padx=10)

        # ---------------- Status ----------------
        self.status_label = tk.Label(parent, text="", fg="blue")
        self.status_label.grid(row=30, column=0, columnspan=5, sticky="w", padx=10)


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

    def on_replace_text_change(self, event):
        """
        Captures any change made in the Replace text field.
        """
        print(f"Replace text changed: {self.replace_text.get('1.0', 'end-1c')}")

    def update_insert_content_state(self):
        if self.insert_content_type_var.get() == "content":
            self.entry_insert_content.config(state="normal")
        else:
            self.entry_insert_content.config(state="disabled")
