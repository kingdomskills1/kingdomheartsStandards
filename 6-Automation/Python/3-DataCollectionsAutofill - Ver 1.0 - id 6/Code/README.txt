Data Collections Autofill
========================

Overview
--------
This project scans a main folder containing numbered subfolders, opens every Microsoft Access database (.mdb or .accdb) found inside those folders, reads table metadata, and creates a summary Word document listing each table with row and column counts.

Features
--------
- Select a main folder with a file dialog
- Reads all Access databases inside each numbered subfolder
- Ignores system tables and temporary tables
- Counts rows and columns for each table
- Saves a report as Data Collections.docx in the selected main folder
- Prompts for database passwords when required

Requirements
------------
- Python 3.x
- pyodbc
- python-docx
- Microsoft Access Database Engine driver installed on the machine so pyodbc can connect to .mdb and .accdb files

Install dependencies
--------------------
Use the following commands in a terminal:

pip install pyodbc python-docx

Usage
-----
1. Open the script in Python.
2. Run it with:
   python data_collections_autofill.py
3. When prompted, select the main folder that contains the database folders.
4. The script will scan each database and generate:
   Data Collections.docx

Notes
-----
- The script sorts folder names numerically when processing them.
- If a database is password-protected, a pop-up will ask for the password.
- If a password is not provided, the database is skipped.
- Output is saved in the selected main folder alongside the source data.

File structure
--------------
- data_collections_autofill.py  - Main application script
- README.txt                   - Project instructions
