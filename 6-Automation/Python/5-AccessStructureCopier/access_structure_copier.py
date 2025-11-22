import os
import shutil
import pyodbc
from tkinter import Tk, filedialog

def choose_folder(title="Select Folder"):
    Tk().withdraw()
    folder_path = filedialog.askdirectory(title=title)
    return folder_path

def copy_access_file(source_file, target_file):
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    shutil.copy2(source_file, target_file)
    print(f"Copied: {source_file} -> {target_file}")
    return target_file

def clear_data_and_reset_ids(db_file):
    conn_str = f'DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={db_file};'
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    # Get all user tables (skip system tables)
    tables = [row.table_name for row in cursor.tables(tableType='TABLE') if not row.table_name.startswith('MSys')]

    for table in tables:
        print(f"Clearing table: {table} in {os.path.basename(db_file)}")
        cursor.execute(f"DELETE FROM [{table}]")
        conn.commit()

        # Attempt to reset AutoNumber (ID assumed)
        try:
            cursor.execute(f"ALTER TABLE [{table}] ALTER COLUMN ID COUNTER(1,1)")
            conn.commit()
        except Exception:
            pass  # Skip if no AutoNumber or different column name

    conn.close()
    print(f"Data cleared and IDs reset for: {os.path.basename(db_file)}")

def process_folder_recursive(source_folder, target_folder):
    for root, dirs, files in os.walk(source_folder):
        for file_name in files:
            if file_name.lower().endswith((".accdb", ".mdb")):
                source_file = os.path.join(root, file_name)
                # Maintain folder structure in target
                relative_path = os.path.relpath(root, source_folder)
                target_file = os.path.join(target_folder, relative_path, file_name)
                copied_file = copy_access_file(source_file, target_file)
                clear_data_and_reset_ids(copied_file)

def main():
    source_folder = choose_folder("Select Folder Containing Access Files")
    if not source_folder:
        print("No folder selected. Exiting.")
        return

    target_folder = choose_folder("Select Folder to Save Copies")
    if not target_folder:
        print("No folder selected. Exiting.")
        return

    process_folder_recursive(source_folder, target_folder)
    print("All files processed successfully!")

if __name__ == "__main__":
    main()
