import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image
import threading
from proglog import ProgressBarLogger
import fitz  # PyMuPDF
from docx import Document
import os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from pdf2docx import Converter
import fitz  # PyMuPDF
import re

class TkLogger(ProgressBarLogger):

    def __init__(self, progress_callback):
        super().__init__()
        self.progress_callback = progress_callback

    def bars_callback(self, bar, attr, value, old_value=None):

        if bar != "t":
            return

        total = self.bars[bar]["total"]

        if not total:
            return

        percent = (value / total) * 100

        self.progress_callback(percent)

class ConverterTab:
    def __init__(self, root, notebook):

        self.root = root

        self.tab = ttk.Frame(notebook)
        notebook.add(self.tab, text="Media Converter")

        self.input_path = ""
        self.output_path = ""

        self.mode = tk.StringVar(value="image")
        self.target_format = tk.StringVar()

        self.build_ui()

    # ================= UI =================
    def build_ui(self):

        title = tk.Label(
            self.tab,
            text="Universal Converter",
            font=("Arial", 18, "bold")
        )
        title.pack(pady=10)

        frame = tk.Frame(self.tab)
        frame.pack(fill="x", padx=20)

        tk.Button(frame, text="Choose File", command=self.choose_file).grid(row=0, column=0)
        tk.Button(frame, text="Choose Folder", command=self.choose_folder).grid(row=0, column=1)
        tk.Button(frame, text="Output Folder", command=self.choose_output).grid(row=0, column=2)

        tk.Label(self.tab, text="Conversion Type").pack(pady=5)

        modes = [
            ("Images", "image"),
            ("Videos", "video"),
            ("Video → Audio", "audio"),
            ("Documents", "doc"),
        ]

        for text, value in modes:
            tk.Radiobutton(
                self.tab,
                text=text,
                variable=self.mode,
                value=value,
                command=self.update_formats
            ).pack()

        self.format_combo = ttk.Combobox(self.tab, textvariable=self.target_format)
        self.format_combo.pack(pady=10)

        self.update_formats()

        self.progress = ttk.Progressbar(self.tab, length=500, mode="determinate")
        self.progress.pack(pady=20)

        self.status = tk.Label(self.tab, text="")
        self.status.pack()

        tk.Button(
            self.tab,
            text="START CONVERT",
            font=("Arial", 14),
            bg="green",
            fg="white",
            command=self.start
        ).pack(pady=20)

    # ================= LOGIC =================
    def update_formats(self):

        formats = {
            "image": ["png", "jpg", "jpeg", "webp", "bmp", "tiff"],
            "video": ["mp4", "avi", "mkv", "mov", "webm"],
            "audio": ["mp3", "wav", "aac", "flac"],
            "doc": ["pdf", "txt", "docx", "html"]
        }

        values = formats[self.mode.get()]
        self.format_combo["values"] = values
        self.target_format.set(values[0])

    def choose_file(self):
        self.input_path = filedialog.askopenfilename()

    def choose_folder(self):
        self.input_path = filedialog.askdirectory()

    def choose_output(self):
        self.output_path = filedialog.askdirectory()

    def get_files(self):

        if os.path.isfile(self.input_path):
            return [self.input_path]

        files = []
        for root, _, names in os.walk(self.input_path):
            for n in names:
                files.append(os.path.join(root, n))

        return files

    # ================= CONVERT =================
    def convert_image(self, src):

        ext = self.target_format.get()

        try:
            img = Image.open(src)
            name = os.path.splitext(os.path.basename(src))[0]

            out = os.path.join(self.output_path, f"{name}.{ext}")

            if ext in ["jpg", "jpeg"]:
                img = img.convert("RGB")

            img.save(out)

        except Exception as e:
            print("Image error:", e)

    def convert_video(self, src):

        ext = self.target_format.get()

        try:

            name = os.path.splitext(
                os.path.basename(src)
            )[0]

            out = os.path.join(
                self.output_path,
                f"{name}.{ext}"
            )

            import subprocess
            import json

            # GET VIDEO DURATION
            probe_cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                src
            ]

            probe = subprocess.run(
                probe_cmd,
                capture_output=True,
                text=True
            )

            data = json.loads(probe.stdout)

            duration = float(
                data["format"]["duration"]
            )

            # FFMPEG COMMAND
            cmd = [
                "ffmpeg",
                "-i", src,
                "-progress", "-",
                "-y",
                out
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                universal_newlines=True
            )

            for line in process.stdout:

                if "out_time_ms=" in line:

                    value = line.strip().split("=")[1]

                    if value == "N/A":
                        continue

                    ms = int(value)

                    current = ms / 1_000_000

                    percent = (
                        current / duration
                    ) * 100

                    self.root.after(
                        0,
                        lambda p=percent:
                        self.progress.config(value=p)
                    )

            process.wait()

        except Exception as e:
            print("Video error:", e)

    def convert_audio(self, src):

        ext = self.target_format.get()

        try:

            import subprocess
            import json

            name = os.path.splitext(
                os.path.basename(src)
            )[0]

            out = os.path.join(
                self.output_path,
                f"{name}.{ext}"
            )

            # GET DURATION
            probe_cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                src
            ]

            probe = subprocess.run(
                probe_cmd,
                capture_output=True,
                text=True
            )

            data = json.loads(probe.stdout)
            duration = float(data["format"]["duration"])

            # FFMPEG AUDIO CONVERT
            cmd = [
                "ffmpeg",
                "-i", src,
                "-vn",
                "-y",
                out,
                "-progress", "-",
                "-nostats"
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                universal_newlines=True
            )

            for line in process.stdout:

                if "out_time_ms=" in line:

                    value = line.strip().split("=")[1]

                    if value == "N/A":
                        continue

                    ms = int(value)

                    current = ms / 1_000_000

                    percent = (current / duration) * 100

                    self.root.after(
                        0,
                        lambda p=percent: (
                            self.root.after(
                                0,
                                lambda p=p:
                                self.progress.config(value=p)
                            )
                        )
                    )

            process.wait()

        except Exception as e:
            print("Audio error:", e)

    # ================= START =================
    def start(self):

        threading.Thread(
            target=self.process_files,
            daemon=True
        ).start()

    def process_files(self):

        if not self.input_path:

            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Error",
                    "Choose input"
                )
            )
            return

        if not self.output_path:

            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Error",
                    "Choose output folder"
                )
            )
            return

        files = self.get_files()

        total = len(files)

        if total == 0:

            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Info",
                    "No files found"
                )
            )
            return

        for i, file in enumerate(files):

            self.root.after(
                0,
                lambda f=file:
                self.status.config(
                    text=os.path.basename(f)
                )
            )

            mode = self.mode.get()

            try:

                if mode == "image":
                    self.convert_image(file)

                elif mode == "video":
                    self.convert_video(file)

                elif mode == "audio":
                    self.convert_audio(file)

                elif mode == "doc":
                    self.convert_document(file)

            except Exception as e:
                print(f"Error converting {file}: {e}")

            overall = ((i + 1) / total) * 100

            self.root.after(
                0,
                lambda v=overall:
                self.progress.config(value=v)
            )

        self.root.after(
            0,
            lambda: messagebox.showinfo(
                "Done",
                "Conversion completed"
            )
        )

    def convert_document(self, src):

        import os
        import pythoncom
        import win32com.client
        import threading
        import time

        ext = self.target_format.get().lower()
        name = os.path.splitext(os.path.basename(src))[0]
        out = os.path.join(self.output_path, f"{name}.{ext}")

        try:

            # ================= DOCX → PDF =================
            if ext == "pdf" and src.lower().endswith(".docx"):

                def worker():

                    pythoncom.CoInitialize()

                    word = win32com.client.Dispatch("Word.Application")
                    word.Visible = False
                    word.DisplayAlerts = 0

                    doc = word.Documents.Open(os.path.abspath(src))

                    total_steps = 100
                    progress = 0

                    def fake_progress():
                        nonlocal progress

                        # smooth progress animation while Word works
                        while progress < 95:
                            progress += 1

                            self.root.after(
                                0,
                                lambda p=progress: self.progress.config(value=p)
                            )

                            time.sleep(0.08)  # speed control

                    import threading
                    t = threading.Thread(target=fake_progress, daemon=True)
                    t.start()

                    # REAL EXPORT (blocking)
                    doc.ExportAsFixedFormat(
                        OutputFileName=os.path.abspath(out),
                        ExportFormat=17,
                        CreateBookmarks=1,
                        OptimizeFor=0
                    )

                    progress = 100

                    doc.Close(False)
                    word.Quit()

                    self.root.after(
                        0,
                        lambda: self.progress.config(value=100)
                    )

                threading.Thread(target=worker, daemon=True).start()
                return

            # ================= PDF → DOCX =================
            elif ext == "docx" and src.lower().endswith(".pdf"):

                from pdf2docx import Converter
                import fitz
                from docx import Document

                def apply_pdf_bookmarks_to_docx(pdf_path, docx_path):

                    pdf = fitz.open(pdf_path)

                    # PDF bookmarks
                    toc = pdf.get_toc()

                    if not toc:
                        return

                    doc = Document(docx_path)

                    # Collect paragraphs once
                    paragraphs = list(doc.paragraphs)

                    for level, title, page in toc:

                        title_clean = title.strip()

                        for para in paragraphs:

                            text = para.text.strip()

                            # Match bookmark text to paragraph text
                            if text.lower() == title_clean.lower():

                                heading = min(level, 9)

                                try:
                                    para.style = f"Heading {heading}"
                                except:
                                    pass

                                break

                    doc.save(docx_path)
                    pdf.close()

                def worker():

                    try:

                        cv = Converter(src)

                        cv.convert(
                            out,
                            start=0,
                            end=None
                        )

                        cv.close()

                        # Apply headings after conversion
                        apply_pdf_bookmarks_to_docx(
                            src,
                            out
                        )

                        self.root.after(
                            0,
                            lambda: self.progress.config(value=100)
                        )

                    except Exception as e:
                        print("PDF→DOCX error:", e)

                threading.Thread(
                    target=worker,
                    daemon=True
                ).start()

                return

            # ================= TXT =================
            elif ext == "txt":

                with open(src, "rb") as f:
                    content = f.read().decode("utf-8", errors="ignore")

                with open(out, "w", encoding="utf-8") as f:
                    f.write(content)

            # ================= HTML =================
            elif ext == "html":

                with open(src, "rb") as f:
                    content = f.read().decode("utf-8", errors="ignore")

                html = f"<html><body><pre>{content}</pre></body></html>"

                with open(out, "w", encoding="utf-8") as f:
                    f.write(html)

            else:
                self.root.after(0, lambda: messagebox.showwarning(
                    "Warning",
                    "Unsupported conversion"
                ))

        except Exception as e:
            print("Document error:", e)

    def _inject_word_bookmarks(self, doc):

        def normalize(style_name):
            return style_name.lower().replace(" ", "").replace("_", "")

        def get_level(style_name):

            s = normalize(style_name)

            if "heading1" in s:
                return 1
            if "heading2" in s:
                return 2
            if "heading3" in s:
                return 3
            if "heading4" in s:
                return 4
            if "heading5" in s:
                return 5
            if "heading6" in s:
                return 6
            if "heading7" in s:
                return 7
            if "heading8" in s:
                return 8
            if "heading9" in s:
                return 9

            return None

        used_names = set()

        for para in doc.Paragraphs:

            text = para.Range.Text.strip()

            if not text:
                continue

            level = get_level(para.Style.NameLocal)

            if level is None:
                continue

            # avoid duplicate bookmark names (IMPORTANT FIX)
            safe_name = text[:40].replace(" ", "_")
            counter = 1

            original = safe_name
            while safe_name in used_names:
                safe_name = f"{original}_{counter}"
                counter += 1

            used_names.add(safe_name)

            try:
                para.Range.Bookmarks.Add(safe_name)
            except:
                pass