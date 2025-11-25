import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import pythoncom
import win32com.client
from docx import Document
import datetime

# Define the map_field_type function at the top of the script
def map_field_type(field_name, field_type, field_size):
    """
    Maps the field type from Python to the appropriate database type.
    It also uses field size to determine if it should be Long Text or Short Text.
    If the field name is exactly 'ID', it's treated as AutoNumber.
    """
    print(f"Field: {field_name}, Type: {field_type}, Size: {field_size}")
    
    # Handle Yes/No fields (Type 1)
    if field_type == 1:  # Yes/No (Boolean)
        return "Yes/No"
    
    # Handle Short Text (Type 10) fields
    if field_type == 10:  # Short Text
        if field_size > 255:
            return "Long Text"  # Long Text for larger fields
        else:
            return "Short Text"  # Short Text for smaller fields
    
    # Handle Long Text (Memo) fields (Type 12)
    elif field_type == 12:  # Memo (Long Text)
        return "Long Text"  # Always Long Text for Type 12
    
    # Handle Date/Time fields (Type 8)
    elif field_type == 8:  # Date/Time
        return "Date/Time"
    
    # Handle Number fields (Type 3, Long Integer)
    elif field_type == 3:  # Long Integer (Number)
        return "Number"
    
    # Handle AutoNumber fields (Type 4)
    elif field_type == 4:  # AutoNumber (unique identifier)
        # Special case for "ID" field
        if field_name == "ID":
            return "AutoNumber"  # AutoNumber for ID fields
        return "Number"
    
    # Handle other types (if any)
    else:
        return "Unknown Type"

class AccessReaderAppDAO:
    def __init__(self, root):
        self.root = root
        self.root.title("Access Table Structure Reader (with Descriptions)")

        self.file_path = ""
        self.db = None

        tk.Button(root, text="Select Access File", command=self.select_file,
                  width=30, height=2).pack(pady=20)

    def select_file(self):
        filepath = filedialog.askopenfilename(
            title="Select Access Database",
            filetypes=[("Access Files", "*.mdb *.accdb")]
        )
        if not filepath:
            return

        self.file_path = filepath

        # Try opening the database without a password first
        try:
            pythoncom.CoInitialize()
            dao = win32com.client.Dispatch("DAO.DBEngine.120")  # DAO 12.0 for Access 2007+
            self.db = dao.OpenDatabase(filepath, False, False)
            # If successful, continue to load the tables
        except Exception as e:
            # Check if the error is related to password protection
            if "Invalid password" in str(e) or "password" in str(e).lower():
                # Prompt for password if database requires it
                self.prompt_for_password(filepath, dao)
            else:
                messagebox.showerror("Error", f"Could not open database.\n{e}")
                return

        self.show_tables_window()

    def prompt_for_password(self, filepath, dao):
        # Ask for password if needed and retry opening the database
        while True:
            pwd = simpledialog.askstring("Password Required", 
                                         "Enter database password:", 
                                         show="*")
            if not pwd:  # If the user cancels or leaves the password empty
                messagebox.showerror("Error", "Database requires a password but none was provided.")
                return

            try:
                # Try opening the database with the provided password
                self.db = dao.OpenDatabase(filepath, False, False, f";PWD={pwd}")
                break  # If successful, break out of the loop
            except Exception as e:
                messagebox.showerror("Error", "Invalid password. Please try again.")

    def show_tables_window(self):
        tables_win = tk.Toplevel(self.root)
        tables_win.title("Select Table")

        tk.Label(tables_win, text="Select a Table:", font=("Arial", 12)).pack(pady=10)

        listbox = tk.Listbox(tables_win, width=40, height=15)
        listbox.pack()

        # Load all user tables (skip system tables)
        for t in self.db.TableDefs:
            if not t.Name.startswith("MSys"):
                listbox.insert(tk.END, t.Name)

        tk.Button(
            tables_win, text="Load Table Structure",
            command=lambda: self.load_structure(listbox.get(tk.ACTIVE)), width=30
        ).pack(pady=10)

    def load_structure(self, table_name):
        if not table_name:
            messagebox.showwarning("No Selection", "Please select a table.")
            return

        try:
            table = self.db.TableDefs[table_name]
        except Exception as e:
            messagebox.showerror("Error", f"Could not read table {table_name}.\n{e}")
            return

        output = []
        for field in table.Fields:
            field_name = field.Name
            field_type = self.get_field_type(field)
            
            # Read description if exists
            try:
                description = field.Properties["Description"]
            except:
                description = ""
            
            # Format the field info without extra line spaces
            if description:  # If description exists, include it
                formatted_line = f"- {field_name} → {field_type} → {description}"
            else:  # If no description, just omit the description part
                formatted_line = f"- {field_name} → {field_type}"

            # Append the formatted line to the output without adding extra empty lines
            output.append(formatted_line.strip())  # strip any leading/trailing spaces (if any)

        # Join the output list into a single string and ensure it has proper line breaks between items
        self.show_output_window("\n".join(output))  # Join the list into a single string with line breaks

    def get_field_type(self, field):
        t = field.Type
        field_name = field.Name
        field_size = field.Size if hasattr(field, 'Size') else None
        
        # Use the mapping function
        return map_field_type(field_name, t, field_size)

    def show_output_window(self, text):
        win = tk.Toplevel(self.root)
        win.title("Table Structure")

        text_box = tk.Text(win, width=100, height=25)
        text_box.pack(pady=10)
        text_box.insert(tk.END, text)

        # Copy button
        tk.Button(win, text="Copy to Clipboard",
                  command=lambda: self.copy_to_clipboard(text)).pack(pady=5)

        # Save button
        tk.Button(win, text="Save to File (TXT or DOC)",
                  command=lambda: self.save_output(text)).pack(pady=5)

    def copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copied", "Column structure copied to clipboard.")

    def save_output(self, text):
        file_path = filedialog.asksaveasfilename(
            title="Save File",
            defaultextension=".txt",
            filetypes=[("Text File", "*.txt"), ("Word Document", "*.docx")]
        )

        if not file_path:
            return

        if file_path.endswith(".txt"):
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            doc = Document()
            for line in text.split("\n"):
                doc.add_paragraph(line)
            doc.save(file_path)

        messagebox.showinfo("Saved", "File saved successfully.")


if __name__ == "__main__":
    root = tk.Tk()
    app = AccessReaderAppDAO(root)
    root.mainloop()
