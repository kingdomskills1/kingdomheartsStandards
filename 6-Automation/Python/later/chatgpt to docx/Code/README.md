# ChatGPT to Word

A small Windows desktop app that exports the latest assistant reply from a
public ChatGPT shared-conversation link to a Microsoft Word `.docx` file.

## Run

1. Install Python 3.10 or newer.
2. Open Command Prompt in this folder and install the dependencies:

   ```text
   python -m pip install -r requirements.txt
   ```

3. Double-click `run.bat`.
4. The app minimizes to the system tray when you close the window; right-click
   the tray icon to restore it or exit the program.
5. In ChatGPT, use the conversation's **Share** option to create a public
   link. Add a row for each conversation, enter its
   `https://chatgpt.com/share/...` or `https://chatgpt.com/s/...` link, and
   optionally enter a Word output path. Double-click a link or path cell to
   edit it, or select a cell and start typing. Click **Convert** at the end of
   a row to run just that job. Use that row's **Cancel** button to stop it, or
   select **Convert all rows** to run all entered links concurrently. Each row
   shows its status and live elapsed time; rows that are not running remain
   editable while other jobs are processing. You can add rows during processing and
   remove selected rows that are not running; active rows cannot be removed
   until they finish or are cancelled. A Windows notification is sent when a
   job finishes if notifications are enabled. A relative output name such as
   `Lower Arc` is expanded to a `.docx` path on the Desktop.
   If an output path is left blank, the document is saved to the Desktop using
   its main heading as the filename. Job statuses are saved and restored; jobs
   that were still running when the app closed are restored as **Cancelled**.
   Set an optional default destination Word document below the formatted-text
   area, or edit a row's destination directly. The destination must already
   exist. After conversion succeeds, **Copy** uses Microsoft Word to insert the
   complete converted document at the destination's end, preserving Word
   formatting and repairing numbered-list restarts for `.docx`/`.docm` files,
   using Word's document insertion engine. Copying requires desktop Microsoft Word,
   `pywin32`, and the included
   `word_document_insertion/word_document_inserter.py`.
   Any Word documents opened by the app are closed when the copy finishes;
   documents that were already open are left open. Legacy `.doc` destinations
   are supported but may not preserve list numbering.

The app only supports public share links. It does not sign in to ChatGPT or
access private conversations. The latest reply is fetched from the shared page,
so links that require access or that no longer exist cannot be converted.
The Word document contains the answer without an added title or source line;
formatting, visible link text, lists, Markdown tables, and inline/display
equations, including boxed formulas and degree-circle notation, are preserved.
When a visible table is present in the ChatGPT share page, the app captures the
actual rendered table image from that page and inserts it immediately before the
Word table block. A generated PNG remains only as a fallback when a live page table
is not available.
Numbered subsection titles such as `4.1. Example` are recognized and formatted
at the matching heading level, including when written as `### 4.1. Example`;
the numbering is omitted from the displayed heading.
Bare variable symbols and simple formulas in Markdown table cells are formatted
as Word equations. LaTeX expressions in table cells, including inline,
display-style, and dollar-delimited forms, are converted to Word equations.
Equations mixed with descriptive text in table cells remain inline, with the
description kept as regular text. Standalone table equations are left-aligned.
Internal ChatGPT layout tags such as `<box>`, `<row>`, and
`<divider>` are omitted from exported text.
ChatGPT's embedded images, including image groups,
are downloaded and placed with their answer content; images in layout rows
follow the row's text. Citation markers and interactive follow-up suggestions
are omitted. Classification breadcrumbs
are omitted from the title when the answer includes a recommended
classification path. Documents are saved in the current Microsoft Word format
to avoid Compatibility Mode. They use the reference layout's one-inch margins,
Roboto Mono body font, blue heading hierarchy, and compact borderless table
formatting. The app includes a formatted-text field: paste copied content with
Ctrl+V to preview its colors, bold, italics, and highlighting; the pasted text
is inserted after a heading unless its next content is a subheading. Text,
images, and tables between a heading and a later subheading do not prevent
insertion after that heading. Leading conversation images appear after the
pasted text beneath the main heading. An animated progress bar appears while
the latest reply is fetched and converted. After saving, the result appears in
the status bar; warning details remain available in a non-modal window so the
app can still be used without closing it.
If no save location is entered, the document is saved to the
Desktop using the main heading as its filename, or `chatgpt-response.docx`
when no main heading is present.

For table screenshots from a live webpage, paste a page URL into the new
"Page URL to capture a table screenshot from" field and click "Take screenshot".
The app opens the page in Chrome headlessly, finds the first `<table>`, and saves
a PNG image of that table for reuse.
