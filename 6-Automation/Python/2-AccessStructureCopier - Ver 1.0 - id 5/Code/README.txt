Access Structure Copier

Overview
This script copies Microsoft Access database files (.accdb and .mdb) from a selected source folder into a target folder and clears the data from each copied database while attempting to reset AutoNumber IDs.

Features
- Recursively scans a source folder for Access database files
- Copies each Access file into the target folder preserving relative folder structure
- Connects to each database using the Microsoft Access ODBC driver
- Prompts for a password if the database is password-protected
- Clears all table data in each copied database
- Attempts to reset AutoNumber IDs after deletion

Requirements
- Python 3
- Microsoft Access Database Engine / ODBC driver for Access databases
- pyodbc package
- Windows environment with Microsoft Access driver support

Install dependencies
pip install pyodbc

How to run
1. Open a terminal in this folder.
2. Run:
   python access_structure_copier.py
3. Select the folder containing the original Access databases.
4. Select the folder where the copied databases should be saved.
5. The script processes each database automatically.

Notes
- This tool is intended for creating empty database copies with the same structure.
- It does not back up or modify the source database files.
- The script only resets AutoNumber IDs when the table contains an ID field named "ID" and the database supports the ALTER TABLE operation.
- If a database is password-protected, you will be prompted for the password.

File
- access_structure_copier.py
