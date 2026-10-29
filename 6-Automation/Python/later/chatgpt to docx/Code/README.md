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
4. In ChatGPT, use the conversation's **Share** option to create a public
   link. Paste the `https://chatgpt.com/share/...` or
   `https://chatgpt.com/s/...` link, choose where to save the document, and
   select **Convert latest reply**.

The app only supports public share links. It does not sign in to ChatGPT or
access private conversations. The latest reply is fetched from the shared page,
so links that require access or that no longer exist cannot be converted.
The Word document contains the answer without an added title or source line;
formatting, visible link text, lists, Markdown tables, and inline/display
equations, including boxed formulas and degree-circle notation, are preserved.
Numbered subsection titles such as `4.1. Example` are recognized and formatted
at the matching heading level, including when written as `### 4.1. Example`;
the numbering is omitted from the displayed heading.
Bare variable symbols and simple formulas in Markdown table cells are formatted
as Word equations. LaTeX expressions in table cells, including inline,
display-style, and dollar-delimited forms, are converted to Word equations and
left-aligned. Internal ChatGPT layout tags such as `<box>`, `<row>`, and
`<divider>` are omitted from exported text.
ChatGPT's embedded images, including image groups,
are downloaded and placed at their positions in the answer; citation markers
and interactive follow-up suggestions are omitted. Classification breadcrumbs
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
the latest reply is fetched and converted.
If no save location is entered, the document is saved to the
Desktop using the main heading as its filename, or `chatgpt-response.docx`
when no main heading is present.
