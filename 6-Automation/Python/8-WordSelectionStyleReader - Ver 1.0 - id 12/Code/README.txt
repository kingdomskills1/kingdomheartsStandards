Word Selection Style Reader

Overview
This utility reads the currently selected text in Microsoft Word and displays per-character formatting details in a Tkinter window. It reports:
- Character text
- Font name
- Font size
- Bold / Italic / Underline status
- Highlight color

Files
- word_selection_style_reader.py: main script

Requirements
- Windows operating system
- Microsoft Word installed
- Python 3
- pywin32 package (pythoncom / win32com)

Install dependencies:
    pip install pywin32

How to use
1. Open Microsoft Word.
2. Select one or more characters or words.
3. Run the script:
       python word_selection_style_reader.py
4. Click the Paste button in the window.
5. The selected text and formatting metadata will be displayed.

Notes
- The script uses Word's COM automation to access the current selection.
- If no text is selected, the tool shows a message indicating that no text was selected.
- The application is intended for Windows-based Word automation workflows.
