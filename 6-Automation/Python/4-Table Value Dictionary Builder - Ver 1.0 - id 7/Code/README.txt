Table Value Dictionary Builder

Overview
This project contains a desktop Python GUI application for creating a Table Value Dictionary (TVD) from a Microsoft Access database table.

The tool allows you to:
- Select an Access .accdb or .mdb file
- View tables and columns in the database
- Choose which columns to include in the output
- Optionally assign a label column for each selected value
- Include row ranges for each distinct value
- Export the results as either a .txt file or a .docx Word document

Files
- table_value_dictionary_builder.py - Main application

Requirements
Install the following Python packages before running the app:
- pyodbc
- pandas
- python-docx

The app also uses the standard Tkinter library, which is included with most Python installations.

Run the application
1. Open a terminal or command prompt in this folder.
2. Run:
   python table_value_dictionary_builder.py
3. Use the GUI to select an Access database and build the TVD.

Typical workflow
1. Click Select Access File.
2. Choose the .accdb or .mdb file.
3. Double-click a table name to copy it to the clipboard if needed.
4. Select the columns to include.
5. Optionally choose a label column for a selected field.
6. Use the Include row_range checkbox when you want row numbers for matching values.
7. Click Create TVD File.
8. Save the output as either a .txt or .docx file.

Notes
- The application is designed for Microsoft Access database tables.
- Label matching is suggested automatically based on similar text fields.
- The generated output lists distinct values, labels, descriptions, and optional row ranges.

Project purpose
This tool is intended to support data dictionary documentation and table-value review tasks by converting database values into a readable, exportable format for business or technical documentation.
