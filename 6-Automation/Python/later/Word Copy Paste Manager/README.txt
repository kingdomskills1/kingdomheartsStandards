# Word Copy & Paste Manager

A Windows GUI utility that uses Microsoft Word desktop automation (COM) to transfer Word content while retaining formatting.

## Requirements
- Windows 10/11
- Microsoft Word desktop application installed
- Python 3.10 or newer
- `pywin32`

## Install
Open Command Prompt and run:

```bat
py -m pip install pywin32
```

## Run
Double-click `Run_Word_Copy_Paste_Manager.bat`, or run:

```bat
py word_copy_paste_manager.py
```

## Features
1. **Copy Entire Document** — inserts the source document into the destination using Word's `InsertFile` operation.
2. **Copy Current Word Selection** — select content in Word, then use the GUI to insert the selection with Word's `FormattedText` support.

For whole-document copies, separate numbered-list sequences are preserved in `.docx` and `.docm` files.

## Important usage notes
- Keep Microsoft Word open while using the program.
- For selected content, first select the required paragraphs in the source document in Word.
- Choose the destination file in the GUI.
- "At the end" is the safest insertion option.
- The program saves the destination document after a successful operation.
- It does not modify the source document.
- Complex section breaks, headers/footers, floating objects, linked objects, and page layout can behave differently when merging documents. Review the destination after insertion.
- For best results, use `.docx` files and ensure neither document is password-protected or read-only.
