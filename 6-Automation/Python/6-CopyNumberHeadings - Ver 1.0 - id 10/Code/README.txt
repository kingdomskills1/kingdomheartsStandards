Copy Number Headings
====================

This project helps you extract heading text from Microsoft Word .docx files, clean the titles, and copy or export numbered headings for use in documentation or content outlines.

Files in this folder
--------------------
- copy_number_headings.py
  GUI application for selecting folders, previewing headings, and copying export output.

- copy_number_headings_core.py
  Core logic for reading .docx files, extracting Heading 1-9 styles, numbering them, and writing numbered output.

What it does
------------
- Reads Word documents and finds paragraph styles such as Heading 1, Heading 2, etc.
- Removes existing numbering prefixes from titles.
- Renumbers heading text in a clean hierarchical format like:
  1-Introduction
  1.1-Overview
  1.1.1-Goals
- Copies selected heading levels to the clipboard.
- Exports the preview to a text file.
- Optionally writes a numbered .docx document.

How to run
----------
1. Install the required dependency:
   pip install python-docx

2. Run the GUI:
   python copy_number_headings.py

3. Select a folder containing .docx files.
4. Choose a file to preview its headings.
5. Use the buttons to copy heading levels or export the results.

Command-line usage
------------------
The core script supports a simple CLI flow:

python copy_number_headings_core.py --src "C:\path\to\document.docx" --out "output" --write-docx

This reads the input .docx file, numbers headings, and writes an output folder with the generated files.

Notes
-----
- The project is designed for heading styles built into Word documents.
- It works best with standard Heading 1 through Heading 9 styles.
- Some cleanup is applied to remove generic numbering patterns and punctuation.
