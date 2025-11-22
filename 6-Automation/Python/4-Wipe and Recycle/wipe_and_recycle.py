import os
import time
from tkinter import Tk, filedialog
from send2trash import send2trash

def choose_folder():
    root = Tk()
    root.withdraw()
    folder_path = filedialog.askdirectory(title="Select a folder")
    root.destroy()
    return folder_path

def collect_files_and_folders(root_folder):
    all_files = []
    all_folders = []

    # Walk bottom-up so subfolders get processed before parent folders
    for dirpath, dirnames, filenames in os.walk(root_folder, topdown=False):
        for filename in filenames:
            all_files.append(os.path.abspath(os.path.join(dirpath, filename)))
        for dirname in dirnames:
            all_folders.append(os.path.abspath(os.path.join(dirpath, dirname)))

    return all_files, all_folders

def force_delete_file(file_path, retries=3):
    for attempt in range(retries):
        try:
            if os.path.exists(file_path):
                os.chmod(file_path, 0o777)  # remove read-only restrictions
                open(file_path, "w").close()  # wipe content
                send2trash(file_path)
            return True
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            print(f"Failed to delete {file_path}: {e}")
            return False
    # Final fallback: force remove
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        return True
    except Exception as e:
        print(f"Final removal failed for {file_path}: {e}")
        return False

def force_delete_folder(folder_path, retries=3):
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
    # Final fallback: force remove
    try:
        if os.path.exists(folder_path):
            os.rmdir(folder_path)
        return True
    except Exception as e:
        print(f"Final folder removal failed for {folder_path}: {e}")
        return False

def wipe_and_recycle(root_folder):
    if not root_folder:
        print("No folder selected.")
        return

    print("Scanning...")
    files, folders = collect_files_and_folders(root_folder)
    print(f"Found {len(files)} files and {len(folders)} folders.\n")

    temp_file_paths = []

    # ============================
    # 1. Rename files safely
    # ============================
    print("Renaming files...")
    for index, file_path in enumerate(files, start=1):
        folder = os.path.dirname(file_path)
        new_name = f"temp_delete_file_{index}"
        new_path = os.path.abspath(os.path.join(folder, new_name))

        try:
            os.rename(file_path, new_path)
            temp_file_paths.append(new_path)
        except Exception as e:
            print(f"Rename failed for {file_path}: {e}")

    time.sleep(0.1)

    # ============================
    # 2. Wipe & delete files
    # ============================
    print("\nDeleting files...")
    for file_path in temp_file_paths:
        if not os.path.exists(file_path):
            continue
        if force_delete_file(file_path):
            print(f"Deleted: {file_path}")
        else:
            print(f"Failed to delete: {file_path}")

    time.sleep(0.1)

    # ============================
    # 3. Rename folders safely
    # ============================
    temp_folder_paths = []
    print("\nRenaming folders...")
    for index, folder_path in enumerate(folders, start=1):
        if folder_path == root_folder:
            continue  # don't rename root folder
        parent = os.path.dirname(folder_path)
        new_name = f"temp_delete_folder_{index}"
        new_path = os.path.abspath(os.path.join(parent, new_name))

        try:
            os.rename(folder_path, new_path)
            temp_folder_paths.append(new_path)
        except Exception as e:
            print(f"Folder rename failed for {folder_path}: {e}")

    time.sleep(0.1)

    # ============================
    # 4. Delete folders (bottom-up)
    # ============================
    print("\nDeleting folders...")
    for folder_path in sorted(temp_folder_paths, key=lambda x: x.count(os.sep), reverse=True):
        if not os.path.exists(folder_path):
            continue
        if force_delete_folder(folder_path):
            print(f"Deleted folder: {folder_path}")
        else:
            print(f"Failed to delete folder: {folder_path}")

    print("\nDone! All files wiped and all subfolders recycled.")

if __name__ == "__main__":
    folder = choose_folder()
    wipe_and_recycle(folder)
