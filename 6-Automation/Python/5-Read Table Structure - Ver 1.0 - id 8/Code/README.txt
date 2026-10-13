Access Table Structure Reader

This project reads the structure of tables from a Microsoft Access database (.mdb or .accdb), including field names, field types, and any available field descriptions.

Files
- read_table_structure.py: Main application script.

What the script does
- Lets the user select an Access database file.
- Opens the database using DAO (Microsoft Access Database Engine / Access runtime support).
- Lists available tables.
- Displays each field in a selected table.
- Shows the mapped field type and description if one exists.
- Allows copying the output to the clipboard.
- Saves the output as a .txt file or .docx document.

Requirements
- Windows operating system
- Python 3.x
- Microsoft Access Database Engine / DAO support available on the machine
- The following Python packages:
  - pywin32
  - python-docx

Install dependencies
pip install pywin32 python-docx

Run the script
python read_table_structure.py

Usage
1. Start the program.
2. Click "Select Access File".
3. Choose a .mdb or .accdb database.
4. Select a table from the list.
5. View the field list and descriptions.
6. Copy or save the output.

Notes
- This program is designed for Windows-based Access database access.
- It depends on DAO and Windows COM support, so it may not work correctly on Linux or macOS.
- Some Access databases may require a password; the script will prompt for it.
- If the file is protected or the database engine is unavailable, make sure Microsoft Access Database Engine or Access is installed.

Example output format
- FieldName1 -> Short Text -> Description
- FieldName2 -> Number
- FieldName3 -> Date/Time

This tool is useful for documenting database table structures quickly and exporting them for reporting or implementation work.
