import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel, Label, Checkbutton, IntVar
import os
import win32com.client as win32
import threading


class WordCopyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Word Copy with Formatting")
        self.root.geometry("560x360")
        self.root.resizable(False, False)

        self.source_path = ""
        self.dest_folder = ""
        self.include_subfolders = IntVar(value=1)

        tk.Label(root, text="Word Copy with Formatting", font=("Arial", 16, "bold")).pack(pady=10)

        tk.Button(root, text="Select File or Folder", width=48, command=self.select_file_or_folder).pack(pady=5)
        tk.Button(root, text="Select Destination Folder", width=48, command=self.select_folder).pack(pady=5)
        Checkbutton(root, text="Include subfolders (if folder selected)", variable=self.include_subfolders).pack(pady=5)
        tk.Button(root, text="Start Copy", width=48, command=self.start_copy_thread).pack(pady=15)

        self.status = tk.Label(root, text="Waiting...", fg="blue")
        self.status.pack()

    def select_file_or_folder(self):
        choice = messagebox.askquestion("Choice", "Yes = Folder\nNo = Single file")
        if choice == 'yes':
            path = filedialog.askdirectory(title="Select folder")
        else:
            path = filedialog.askopenfilename(
                title="Select Word file",
                filetypes=[("Word Documents", "*.docx *.doc")]
            )

        if path:
            self.source_path = os.path.abspath(path)
            self.status.config(text=f"Selected: {self.source_path}")

    def select_folder(self):
        path = filedialog.askdirectory(title="Select destination folder")
        if path:
            self.dest_folder = os.path.abspath(path)
            self.status.config(text=f"Destination: {self.dest_folder}")

    def start_copy_thread(self):
        threading.Thread(target=self.copy_word, daemon=True).start()

    def show_loading(self):
        self.loading_win = Toplevel(self.root)
        self.loading_win.title("Processing...")
        self.loading_win.geometry("420x120")
        self.loading_win.resizable(False, False)

        self.loading_label = Label(self.loading_win, text="", font=("Arial", 11))
        self.loading_label.pack(expand=True)

        self.loading_win.transient(self.root)
        self.loading_win.grab_set()
        self.root.update()

    def update_loading(self, text):
        if self.loading_win:
            self.loading_label.config(text=text)
            self.loading_win.update()

    def hide_loading(self):
        if self.loading_win:
            self.loading_win.destroy()
            self.loading_win = None

    # ✅ ONLY FIX IS HERE
    def copy_word_file(self, word, file_path, relative_path):
        doc = word.Documents.Open(file_path)

        new_doc = word.Documents.Add()

        # 🔥 CORRECT WAY — preserves REAL heading styles
        new_doc.Content.FormattedText = doc.Content.FormattedText

        dest_subfolder = os.path.join(self.dest_folder, relative_path)
        os.makedirs(dest_subfolder, exist_ok=True)

        file_name = os.path.basename(file_path)
        new_path = os.path.join(dest_subfolder, file_name)

        base, ext = os.path.splitext(new_path)
        i = 1
        while os.path.exists(new_path):
            new_path = f"{base}_copy{i}{ext}"
            i += 1

        new_doc.SaveAs(new_path)
        new_doc.Close()
        doc.Close()

    def copy_word(self):
        if not self.source_path or not self.dest_folder:
            messagebox.showerror("Error", "Please select source and destination")
            return

        try:
            files = []

            if os.path.isfile(self.source_path):
                files.append((self.source_path, ""))
            else:
                for root_dir, _, file_list in os.walk(self.source_path):
                    if not self.include_subfolders.get() and root_dir != self.source_path:
                        continue

                    for f in file_list:
                        if f.lower().endswith((".docx", ".doc")) and not f.startswith("~$"):
                            full = os.path.join(root_dir, f)
                            rel = os.path.relpath(root_dir, self.source_path)
                            if rel == ".":
                                rel = ""
                            files.append((full, rel))

            if not files:
                messagebox.showwarning("No files", "No valid Word files found.")
                return

            self.show_loading()

            word = win32.Dispatch("Word.Application")
            word.Visible = False

            total = len(files)
            for index, (file_path, rel_path) in enumerate(files, start=1):
                percent = int((index / total) * 100)
                display = os.path.join(rel_path, os.path.basename(file_path))
                self.update_loading(f"Copying:\n{display}\n\nProgress: {percent}%")

                self.copy_word_file(word, file_path, rel_path)

            word.Quit()
            self.hide_loading()
            messagebox.showinfo("Done", f"Successfully copied {total} file(s).")

        except Exception as e:
            self.hide_loading()
            messagebox.showerror("Error", str(e))


# Run app
root = tk.Tk()
app = WordCopyApp(root)
root.mainloop()
