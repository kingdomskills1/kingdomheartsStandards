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
- Reads Word documents and finds Heading 1-9 styles and paragraphs marked with Word outline levels.
- Removes existing numbering prefixes from titles.
- Renumbers heading text in a clean hierarchical format like:
  1-Introduction
  1.1-Overview
  1.1.1-Goals
- Copies selected heading levels to the clipboard.
- Shows headings in the upper preview and source notes in a separate lower pane.
- Groups lower-pane sources by source type and removes repeated source entries.
- Copies a summary of unique sources, including the total and AI source count.
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
python copy_number_headings_core.py --src "C:\path\to\document.docx" --out "output" --with-sources

This reads the input .docx file, numbers headings, and (with --with-sources) writes a text file that includes the source notes placed right after each heading.

Notes
-----
- The project supports both built-in heading styles and directly assigned Word outline levels.
- It works best with headings marked as Heading 1 through Heading 9 or outline levels 1 through 9.
- Some cleanup is applied to remove generic numbering patterns and punctuation.
