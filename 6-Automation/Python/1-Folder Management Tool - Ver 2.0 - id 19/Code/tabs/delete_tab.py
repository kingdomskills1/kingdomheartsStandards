import os
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from send2trash import send2trash

# ---------------- DELETE CLASS ----------------
class DeleteTab:
    def __init__(self, root, parent_tab):
        self.root = root
        self.parent_tab = parent_tab

        # Variables
        self.delete_folder_var = tk.StringVar()

        # UI
        self.create_ui()

    # ---------------- UI ----------------
    def create_ui(self):

        # Clear old widgets
        for widget in self.parent_tab.winfo_children():
            widget.destroy()

        # ---------------- TITLE ----------------
        ttk.Label(
            self.parent_tab,
            text="Select folder to delete & wipe:"
        ).pack(anchor="w", padx=10, pady=5)

        # ---------------- FOLDER ENTRY ----------------
        ttk.Entry(
            self.parent_tab,
            textvariable=self.delete_folder_var,
            width=50
        ).pack(anchor="w", padx=10, pady=5)

        # ---------------- BROWSE BUTTON ----------------
        ttk.Button(
            self.parent_tab,
            text="Browse Folder",
            command=self.choose_delete_folder
        ).pack(anchor="w", padx=10, pady=5)

        # ---------------- DELETE BUTTON ----------------
        ttk.Button(
            self.parent_tab,
            text="Start Delete & Wipe",
            command=self.start_delete
        ).pack(anchor="w", padx=10, pady=5)

        # ---------------- PROGRESS LABEL ----------------
        self.progress_label = ttk.Label(
            self.parent_tab,
            text="Progress: 0%"
        )

        self.progress_label.pack(
            anchor="w",
            padx=10,
            pady=(15, 5)
        )

        # ---------------- PROGRESS BAR ----------------
        self.progress_bar = ttk.Progressbar(
            self.parent_tab,
            orient="horizontal",
            length=400,
            mode="determinate"
        )

        self.progress_bar.pack(
            anchor="w",
            padx=10,
            pady=5
        )


    # ---------------- CHOOSE FOLDER ----------------
    def choose_delete_folder(self):
        path = filedialog.askdirectory(title="Select Folder to Delete")
        if path:
            self.delete_folder_var.set(path)

    # ---------------- START DELETE ----------------
    def start_delete(self):

        folder = self.delete_folder_var.get()

        if not folder:
            messagebox.showerror(
                "Error",
                "Please select a folder first."
            )
            return

        # ---------------- RESET PROGRESS ----------------
        self.progress_bar.stop()

        self.progress_bar["value"] = 0

        self.progress_label.config(
            text="Progress: 0%"
        )

        self.root.update_idletasks()

        # ---------------- CONFIRM ----------------
        if messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete and wipe:\n{folder}?"
        ):

            self.wipe_and_recycle(folder)

            # Final clean update
            self.progress_bar["value"] = 100

            self.progress_label.config(
                text="Progress: 100%"
            )

            self.root.update_idletasks()

            messagebox.showinfo(
                "Done",
                f"Folder wiped and deleted:\n{folder}"
            )

    # ---------------- COLLECT FILES/FOLDERS ----------------
    def collect_files_and_folders(self, root_folder):
        all_files = []
        all_folders = []

        for dirpath, dirnames, filenames in os.walk(root_folder, topdown=False):

            for filename in filenames:
                all_files.append(
                    os.path.abspath(os.path.join(dirpath, filename))
                )

            for dirname in dirnames:
                all_folders.append(
                    os.path.abspath(os.path.join(dirpath, dirname))
                )

        return all_files, all_folders

    # ---------------- FORCE DELETE FILE ----------------
    def force_delete_file(self, file_path, retries=3):
        for attempt in range(retries):
            try:
                if os.path.exists(file_path):
                    os.chmod(file_path, 0o777)

                    open(file_path, "w").close()

                    send2trash(file_path)

                return True

            except PermissionError:
                time.sleep(0.1)

            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")
                return False

        try:
            if os.path.exists(file_path):
                os.remove(file_path)

            return True

        except Exception as e:
            print(f"Final removal failed for {file_path}: {e}")
            return False

    # ---------------- FORCE DELETE FOLDER ----------------
    def force_delete_folder(self, folder_path, retries=3):
        for attempt in range(retries):
            try:
                if os.path.exists(folder_path):
                    os.chmod(folder_path, 0o777)

                    send2trash(folder_path)

                return True

            except PermissionError:
                time.sleep(0.1)

            except Exception as e:
                print(f"Failed to delete folder {folder_path}: {e}")
                return False

        try:
            if os.path.exists(folder_path):
                os.rmdir(folder_path)

            return True

        except Exception as e:
            print(f"Final folder removal failed for {folder_path}: {e}")
            return False

    # ---------------- WIPE AND RECYCLE ----------------
    def wipe_and_recycle(self, root_folder):

        if not root_folder:
            print("No folder selected.")
            return

        files, folders = self.collect_files_and_folders(
            root_folder
        )

        total_operations = (
            len(files) +
            len(folders) +
            1
        )

        completed = 0

        self.progress_bar["value"] = 0
        self.progress_label.config(text="Progress: 0%")

        # ---------------- RENAME FILES ----------------
        temp_file_paths = []

        for index, file_path in enumerate(files, start=1):

            folder = os.path.dirname(file_path)

            new_name = f"temp_delete_file_{index}"

            new_path = os.path.abspath(
                os.path.join(folder, new_name)
            )

            try:

                os.rename(file_path, new_path)

                temp_file_paths.append(new_path)

            except Exception as e:

                print(f"Rename failed for {file_path}: {e}")

        # ---------------- DELETE FILES ----------------
        for file_path in temp_file_paths:

            if os.path.exists(file_path):

                self.force_delete_file(file_path)

            completed += 1

            self.update_progress(
                completed,
                total_operations
            )

        # ---------------- RENAME FOLDERS ----------------
        temp_folder_paths = []

        for index, folder_path in enumerate(
            folders,
            start=1
        ):

            if folder_path == root_folder:
                continue

            parent = os.path.dirname(folder_path)

            new_name = f"temp_delete_folder_{index}"

            new_path = os.path.abspath(
                os.path.join(parent, new_name)
            )

            try:

                os.rename(folder_path, new_path)

                temp_folder_paths.append(new_path)

            except Exception as e:

                print(f"Folder rename failed for {folder_path}: {e}")

        # ---------------- DELETE FOLDERS ----------------
        for folder_path in sorted(
            temp_folder_paths,
            key=lambda x: x.count(os.sep),
            reverse=True
        ):

            if os.path.exists(folder_path):

                self.force_delete_folder(folder_path)

            completed += 1

            self.update_progress(
                completed,
                total_operations
            )

        # ---------------- DELETE ROOT FOLDER ----------------
        if os.path.exists(root_folder):

            self.force_delete_folder(root_folder)

        completed += 1

        self.update_progress(
            completed,
            total_operations
        )

    # ---------------- UPDATE PROGRESS ----------------
    def update_progress(self, current, total):

        if total <= 0:
            percent = 0
        else:
            percent = int((current / total) * 100)

        # Reset first
        self.progress_bar["value"] = percent

        # IMPORTANT: only one %
        self.progress_label.config(
            text=f"Progress: {percent}%"
        )

        self.root.update_idletasks()