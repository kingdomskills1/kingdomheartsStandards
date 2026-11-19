"""
Word Copy & Paste Manager
Windows desktop utility for copying complete Word documents or selected content
while preserving Word formatting through Microsoft Word COM automation.

Requirements:
    Windows
    Microsoft Word (desktop)
    Python 3.10+
    pywin32  (install with: py -m pip install pywin32)

Run:
    py word_copy_paste_manager.py
"""

import os
import time
import uuid
import zipfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from xml.dom import minidom
import pythoncom
import pywintypes
import win32com.client


WD_COLLAPSE_END = 0
WD_COLLAPSE_START = 1
WD_ALERTS_NONE = 0
RPC_E_CALL_REJECTED = -2147418111


class WordCopyPasteManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Word Copy & Paste Manager")
        self.root.geometry("690x530")
        self.root.minsize(630, 490)

        self.source_path = tk.StringVar()
        self.destination_path = tk.StringVar()
        self.insert_position = tk.StringVar(value="end")
        self.status = tk.StringVar(value="Ready. Open the source and destination documents in Microsoft Word.")

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Word Copy & Paste Manager",
                  font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(
            main,
            text="Transfer complete documents or selected Word content using Microsoft Word's own formatting engine.",
            wraplength=640
        ).pack(anchor="w", pady=(4, 14))

        files = ttk.LabelFrame(main, text="Document paths (used for whole-document copying)", padding=10)
        files.pack(fill="x", pady=(0, 12))

        self._file_row(files, "Source document:", self.source_path, self._browse_source)
        self._file_row(files, "Destination:", self.destination_path, self._browse_destination)

        placement = ttk.LabelFrame(main, text="Where to insert copied content", padding=10)
        placement.pack(fill="x", pady=(0, 12))
        ttk.Radiobutton(placement, text="At the end of the destination document",
                        variable=self.insert_position, value="end").pack(anchor="w")
        ttk.Radiobutton(placement, text="At the current cursor in the destination document (if already open)",
                        variable=self.insert_position, value="cursor").pack(anchor="w")

        whole = ttk.LabelFrame(main, text="1. Copy an entire document", padding=10)
        whole.pack(fill="x", pady=(0, 12))
        ttk.Label(
            whole,
            text="Inserts the complete source file, including its paragraphs, headings, lists, tables and pictures."
        ).pack(anchor="w")
        ttk.Button(whole, text="Copy Entire Document", command=self.copy_entire_document).pack(anchor="w", pady=(8, 0))

        selected = ttk.LabelFrame(main, text="2. Copy selected content", padding=10)
        selected.pack(fill="x", pady=(0, 12))
        ttk.Label(
            selected,
            text="In Word, select the text/paragraphs (including the list items), then click this button. "
                 "The selection is copied with its Word formatting."
        ).pack(anchor="w")
        ttk.Button(selected, text="Copy Current Word Selection to Destination",
                   command=self.copy_selection).pack(anchor="w", pady=(8, 0))

        notes = (
            "Important:\n"
            "• Keep Microsoft Word open while using this program.\n"
            "• For selected content, select it in the source document in Word before clicking the button.\n"
            "• The destination document is saved after a successful transfer.\n"
            "• Whole-document copies preserve numbered-list restart points in .docx and .docm files.\n"
            "• The program does not overwrite the source document."
        )
        ttk.Label(main, text=notes, justify="left", foreground="#444",
                  wraplength=640).pack(anchor="w", pady=(0, 10))

        status_frame = ttk.Frame(main)
        status_frame.pack(fill="x", side="bottom")
        ttk.Separator(status_frame).pack(fill="x", pady=(4, 8))
        ttk.Label(status_frame, textvariable=self.status, wraplength=640,
                  foreground="#145a32").pack(anchor="w")

    def _file_row(self, parent, label, variable, command):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=18).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse…", command=command).pack(side="left")

    def _browse_source(self):
        path = filedialog.askopenfilename(
            title="Select source Word document",
            filetypes=[("Word documents", "*.docx;*.doc;*.docm"), ("All files", "*.*")]
        )
        if path:
            self.source_path.set(path)

    def _browse_destination(self):
        path = filedialog.askopenfilename(
            title="Select destination Word document",
            filetypes=[("Word documents", "*.docx;*.doc;*.docm"), ("All files", "*.*")]
        )
        if path:
            self.destination_path.set(path)

    def _get_word(self):
        pythoncom.CoInitialize()
        try:
            word = self._word_call(lambda: win32com.client.GetActiveObject("Word.Application"))
        except pywintypes.com_error as exc:
            if exc.hresult == RPC_E_CALL_REJECTED:
                raise
            word = self._word_call(lambda: win32com.client.Dispatch("Word.Application"))
        self._word_call(lambda: setattr(word, "Visible", True))
        self._word_call(lambda: setattr(word, "DisplayAlerts", WD_ALERTS_NONE))
        return word

    def _word_call(self, operation):
        for attempt in range(30):
            try:
                return operation()
            except pywintypes.com_error as exc:
                if exc.hresult != RPC_E_CALL_REJECTED or attempt == 29:
                    raise
                pythoncom.PumpWaitingMessages()
                time.sleep(min(0.2 * (attempt + 1), 1.0))

    def _open_doc(self, word, path):
        full = os.path.abspath(path)
        document_count = self._word_call(lambda: word.Documents.Count)
        for index in range(1, document_count + 1):
            doc = self._word_call(lambda: word.Documents(index))
            try:
                if os.path.abspath(self._word_call(lambda: doc.FullName)).lower() == full.lower():
                    return doc
            except pywintypes.com_error as exc:
                if exc.hresult == RPC_E_CALL_REJECTED:
                    raise
            except (AttributeError, OSError):
                pass
        return self._word_call(lambda: word.Documents.Open(full))

    def _destination_range(self, doc):
        if (self.insert_position.get() == "cursor"
                and doc == self._word_call(lambda: self._word.ActiveDocument)):
            return self._word_call(lambda: self._word.Selection.Range)
        rng = self._word_call(lambda: doc.Content)
        self._word_call(lambda: rng.Collapse(WD_COLLAPSE_END))
        return rng

    def _preserve_inserted_fonts(self, source_doc, destination_doc, insertion_start):
        source_count = self._word_call(lambda: source_doc.Paragraphs.Count)
        destination_count = self._word_call(lambda: destination_doc.Paragraphs.Count)
        source_paragraphs = []
        destination_paragraphs = []

        for index in range(1, source_count + 1):
            paragraph = self._word_call(lambda: source_doc.Paragraphs(index))
            text = self._word_call(lambda: paragraph.Range.Text).rstrip("\r\x07").strip()
            font = self._word_call(lambda: paragraph.Range.Font.Name)
            source_paragraphs.append((text, font))

        for index in range(1, destination_count + 1):
            paragraph = self._word_call(lambda: destination_doc.Paragraphs(index))
            text = self._word_call(lambda: paragraph.Range.Text).rstrip("\r\x07").strip()
            start = self._word_call(lambda: paragraph.Range.Start)
            destination_paragraphs.append((text, start))

        source_texts = [text for text, _ in source_paragraphs]
        candidates = [
            index for index in range(destination_count - source_count + 1)
            if [text for text, _ in destination_paragraphs[index:index + source_count]] == source_texts
        ]
        if not candidates:
            raise RuntimeError("Could not locate the inserted source paragraphs to preserve their fonts.")

        first_destination_paragraph = min(
            candidates,
            key=lambda index: abs(destination_paragraphs[index][1] - insertion_start)
        )
        for offset, (_, source_font) in enumerate(source_paragraphs):
            if isinstance(source_font, str) and source_font:
                paragraph = destination_doc.Paragraphs(first_destination_paragraph + offset + 1)
                self._word_call(lambda: setattr(paragraph.Range.Font, "Name", source_font))

    def _repair_inserted_list_numbering(self, source_path, destination_path, marker):
        word_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

        def direct_children(node, local_name):
            return [
                child for child in node.childNodes
                if child.nodeType == child.ELEMENT_NODE
                and child.namespaceURI == word_ns
                and child.localName == local_name
            ]

        def attribute_value(node, local_name):
            attribute = node.getAttributeNodeNS(word_ns, local_name)
            return attribute.value if attribute is not None else None

        def set_attribute_value(node, local_name, value):
            attribute = node.getAttributeNodeNS(word_ns, local_name)
            if attribute is None:
                raise RuntimeError(f"Missing WordprocessingML attribute: {local_name}")
            node.setAttributeNS(word_ns, attribute.name, str(value))

        def paragraph_text(paragraph):
            return "".join(
                text_node.firstChild.data if text_node.firstChild else ""
                for text_node in paragraph.getElementsByTagNameNS(word_ns, "t")
            ).strip()

        def paragraph_num_id(paragraph):
            paragraph_properties = direct_children(paragraph, "pPr")
            if not paragraph_properties:
                return None
            num_properties = direct_children(paragraph_properties[0], "numPr")
            if not num_properties:
                return None
            num_ids = direct_children(num_properties[0], "numId")
            return attribute_value(num_ids[0], "val") if num_ids else None

        def abstract_num_id(num_definition):
            references = num_definition.getElementsByTagNameNS(word_ns, "abstractNumId")
            return attribute_value(references[0], "val") if references else None

        if not zipfile.is_zipfile(source_path) or not zipfile.is_zipfile(destination_path):
            raise RuntimeError("Numbering repair requires Open XML Word documents (.docx or .docm).")

        temporary_path = destination_path + "." + uuid.uuid4().hex + ".tmp"
        try:
            with zipfile.ZipFile(source_path, "r") as source_package:
                source_document = minidom.parseString(source_package.read("word/document.xml"))
                source_numbering_data = (
                    source_package.read("word/numbering.xml")
                    if "word/numbering.xml" in source_package.namelist()
                    else None
                )

            with zipfile.ZipFile(destination_path, "r") as destination_package:
                destination_document = minidom.parseString(destination_package.read("word/document.xml"))
                destination_numbering_data = (
                    destination_package.read("word/numbering.xml")
                    if "word/numbering.xml" in destination_package.namelist()
                    else None
                )

            source_paragraphs = list(source_document.getElementsByTagNameNS(word_ns, "p"))
            destination_paragraphs = list(destination_document.getElementsByTagNameNS(word_ns, "p"))
            source_list_items = [
                (index, paragraph, paragraph_num_id(paragraph))
                for index, paragraph in enumerate(source_paragraphs)
                if paragraph_num_id(paragraph) not in (None, "0")
            ]

            marker_text_nodes = [
                text_node
                for text_node in destination_document.getElementsByTagNameNS(word_ns, "t")
                if text_node.firstChild and marker in text_node.firstChild.data
            ]
            if len(marker_text_nodes) != 1:
                raise RuntimeError("Could not uniquely locate the temporary insertion marker.")

            marker_paragraph = marker_text_nodes[0]
            while (marker_paragraph is not None
                   and not (marker_paragraph.namespaceURI == word_ns
                            and marker_paragraph.localName == "p")):
                marker_paragraph = marker_paragraph.parentNode
            if marker_paragraph is None:
                raise RuntimeError("The insertion marker is not inside a Word paragraph.")

            marker_index = next(
                (index for index, paragraph in enumerate(destination_paragraphs)
                 if paragraph is marker_paragraph),
                None
            )
            if marker_index is None:
                raise RuntimeError("Could not locate the insertion marker paragraph.")

            source_num_ids = sorted(
                {num_id for _, _, num_id in source_list_items},
                key=int
            )
            if source_num_ids:
                if source_numbering_data is None or destination_numbering_data is None:
                    raise RuntimeError("A document with numbered paragraphs is missing its numbering definitions.")

                source_numbering = minidom.parseString(source_numbering_data)
                destination_numbering = minidom.parseString(destination_numbering_data)
                source_num_definitions = {
                    attribute_value(item, "numId"): item
                    for item in source_numbering.getElementsByTagNameNS(word_ns, "num")
                }
                source_abstract_definitions = {
                    attribute_value(item, "abstractNumId"): item
                    for item in source_numbering.getElementsByTagNameNS(word_ns, "abstractNum")
                }

                for index, source_paragraph, source_num_id in source_list_items:
                    destination_index = marker_index + index
                    if destination_index >= len(destination_paragraphs):
                        raise RuntimeError("Could not locate all copied numbered paragraphs.")
                    target = destination_paragraphs[destination_index]
                    if paragraph_text(source_paragraph) != paragraph_text(target):
                        raise RuntimeError("Copied paragraph text did not align for numbering repair.")
                    if paragraph_num_id(target) is None:
                        raise RuntimeError("A copied list paragraph has no numbering reference.")
                    if source_num_id not in source_num_definitions:
                        raise RuntimeError(f"Source numbering definition {source_num_id} is missing.")

                source_abstract_ids = sorted(
                    {
                        abstract_num_id(source_num_definitions[num_id])
                        for num_id in source_num_ids
                    },
                    key=int
                )
                if any(abstract_id not in source_abstract_definitions
                       for abstract_id in source_abstract_ids):
                    raise RuntimeError("A source abstract numbering definition is missing.")

                destination_num_definitions = list(
                    destination_numbering.getElementsByTagNameNS(word_ns, "num")
                )
                destination_abstract_definitions = list(
                    destination_numbering.getElementsByTagNameNS(word_ns, "abstractNum")
                )
                next_num_id = max(
                    (int(attribute_value(item, "numId")) for item in destination_num_definitions),
                    default=0
                ) + 1
                next_abstract_id = max(
                    (int(attribute_value(item, "abstractNumId"))
                     for item in destination_abstract_definitions),
                    default=-1
                ) + 1
                new_num_ids = {
                    old_id: str(next_num_id + offset)
                    for offset, old_id in enumerate(source_num_ids)
                }
                new_abstract_ids = {
                    old_id: str(next_abstract_id + offset)
                    for offset, old_id in enumerate(source_abstract_ids)
                }

                for index, _, source_num_id in source_list_items:
                    target = destination_paragraphs[marker_index + index]
                    num_id_element = direct_children(
                        direct_children(direct_children(target, "pPr")[0], "numPr")[0],
                        "numId"
                    )[0]
                    set_attribute_value(num_id_element, "val", new_num_ids[source_num_id])

                numbering_root = destination_numbering.documentElement
                existing_num_elements = destination_numbering.getElementsByTagNameNS(word_ns, "num")
                first_num = existing_num_elements[0] if existing_num_elements else None
                for old_id in source_abstract_ids:
                    definition = source_abstract_definitions[old_id].cloneNode(True)
                    set_attribute_value(definition, "abstractNumId", new_abstract_ids[old_id])
                    imported = destination_numbering.importNode(definition, True)
                    if first_num is not None:
                        numbering_root.insertBefore(imported, first_num)
                    else:
                        numbering_root.appendChild(imported)

                num_id_mac = destination_numbering.getElementsByTagNameNS(word_ns, "numIdMac")
                insert_before = num_id_mac[0] if num_id_mac else None
                for old_id in source_num_ids:
                    definition = source_num_definitions[old_id].cloneNode(True)
                    set_attribute_value(definition, "numId", new_num_ids[old_id])
                    abstract_ref = definition.getElementsByTagNameNS(word_ns, "abstractNumId")
                    if not abstract_ref:
                        raise RuntimeError(f"Source numbering definition {old_id} has no abstract reference.")
                    original_abstract_id = abstract_num_id(source_num_definitions[old_id])
                    set_attribute_value(abstract_ref[0], "val", new_abstract_ids[original_abstract_id])
                    imported = destination_numbering.importNode(definition, True)
                    if insert_before is not None:
                        numbering_root.insertBefore(imported, insert_before)
                    else:
                        numbering_root.appendChild(imported)

                destination_numbering_data = destination_numbering.toxml(encoding="UTF-8")

            marker_text_nodes[0].firstChild.data = marker_text_nodes[0].firstChild.data.replace(marker, "", 1)
            destination_document_data = destination_document.toxml(encoding="UTF-8")

            with zipfile.ZipFile(destination_path, "r") as original_package:
                with zipfile.ZipFile(temporary_path, "w") as repaired_package:
                    repaired_package.comment = original_package.comment
                    for item in original_package.infolist():
                        if item.filename == "word/document.xml":
                            content = destination_document_data
                        elif item.filename == "word/numbering.xml" and source_num_ids:
                            content = destination_numbering_data
                        else:
                            content = original_package.read(item.filename)
                        repaired_package.writestr(item, content)

            with zipfile.ZipFile(temporary_path, "r") as repaired_package:
                invalid_member = repaired_package.testzip()
                if invalid_member:
                    raise RuntimeError(f"Repaired Word document failed ZIP validation: {invalid_member}")
                repaired_document = minidom.parseString(repaired_package.read("word/document.xml"))
                if marker in repaired_package.read("word/document.xml").decode("utf-8"):
                    raise RuntimeError("The temporary insertion marker was not removed.")
                repaired_paragraphs = list(repaired_document.getElementsByTagNameNS(word_ns, "p"))
                for index, _, source_num_id in source_list_items:
                    target = repaired_paragraphs[marker_index + index]
                    if paragraph_num_id(target) != new_num_ids[source_num_id]:
                        raise RuntimeError("A repaired list reference failed validation.")

            os.replace(temporary_path, destination_path)
            return len(source_list_items)
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)

    def _remove_temporary_marker(self, document, marker):
        search_range = self._word_call(lambda: document.Content.Duplicate)
        find = self._word_call(lambda: search_range.Find)
        self._word_call(lambda: setattr(find, "Text", marker))
        self._word_call(lambda: setattr(find, "Forward", True))
        self._word_call(lambda: setattr(find, "Wrap", 0))
        if self._word_call(lambda: find.Execute()):
            self._word_call(lambda: setattr(search_range, "Text", ""))
            self._word_call(document.Save)

    def copy_entire_document(self):
        src = self.source_path.get().strip()
        dst = self.destination_path.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showerror("Source required", "Choose an existing source Word document.")
            return
        if not dst or not os.path.isfile(dst):
            messagebox.showerror("Destination required", "Choose an existing destination Word document.")
            return
        if os.path.abspath(src).lower() == os.path.abspath(dst).lower():
            messagebox.showerror("Same document", "Source and destination must be different documents.")
            return

        try:
            self._word = self._get_word()
            source_doc = self._open_doc(self._word, src)
            destination_doc = self._open_doc(self._word, dst)

            target = self._destination_range(destination_doc)
            insertion_start = self._word_call(lambda: target.Start)
            self._word_call(lambda: target.InsertFile(os.path.abspath(src)))
            self._preserve_inserted_fonts(source_doc, destination_doc, insertion_start)
            open_xml_documents = (
                os.path.splitext(src)[1].lower() in (".docx", ".docm")
                and os.path.splitext(dst)[1].lower() in (".docx", ".docm")
            )
            marker = None
            if open_xml_documents:
                marker = "WCPNUMFIX" + uuid.uuid4().hex
                marker_range = self._word_call(
                    lambda: destination_doc.Range(insertion_start, insertion_start)
                )
                self._word_call(lambda: setattr(marker_range, "Text", marker))
            self._word_call(destination_doc.Save)
            if marker:
                self._word_call(lambda: destination_doc.Close(False))
                try:
                    self._repair_inserted_list_numbering(src, dst, marker)
                except Exception as repair_error:
                    destination_doc = self._open_doc(self._word, dst)
                    try:
                        self._remove_temporary_marker(destination_doc, marker)
                    except Exception as cleanup_error:
                        raise RuntimeError(
                            f"{repair_error}; also failed to remove the temporary marker: {cleanup_error}"
                        ) from repair_error
                    raise
                destination_doc = self._open_doc(self._word, dst)
            self.status.set("Success: entire document inserted with its original fonts and saved.")
            messagebox.showinfo(
                "Completed",
                "The entire source document was inserted with its original fonts and formatting.\n\n"
                "Numbered lists restart like the source document. Review page breaks and section layout, "
                "especially if the documents use different page setups."
            )
            if not open_xml_documents:
                messagebox.showwarning(
                    "Numbering may differ",
                    "This copy used a legacy Word document. Automatic list-numbering repair is available "
                    "for .docx and .docm files; save both documents in one of those formats for reliable numbering."
                )
        except Exception as exc:
            self._show_error(exc)

    def copy_selection(self):
        dst = self.destination_path.get().strip()
        if not dst or not os.path.isfile(dst):
            messagebox.showerror("Destination required", "Choose an existing destination Word document.")
            return

        try:
            self._word = self._get_word()
            source_doc = self._word.ActiveDocument
            source_range = self._word.Selection.Range.Duplicate

            if source_range.Start == source_range.End:
                messagebox.showwarning(
                    "Nothing selected",
                    "Select the required text or paragraphs in the source document in Word, then try again."
                )
                return

            destination_doc = self._open_doc(self._word, dst)

            if self.insert_position.get() == "cursor":
                # When destination is already active, use its cursor. If opening it
                # changed the active document, fall back to the end to avoid inserting
                # into an unrelated selection.
                if os.path.abspath(destination_doc.FullName).lower() == os.path.abspath(dst).lower():
                    target = destination_doc.Application.Selection.Range
                else:
                    target = destination_doc.Content
                    target.Collapse(WD_COLLAPSE_END)
            else:
                target = destination_doc.Content
                target.Collapse(WD_COLLAPSE_END)

            # Prefer Word's original-formatting paste to keep paragraph and character
            # formatting, including the original font and style, from the source range.
            try:
                source_range.Copy()
                target.PasteAndFormat(16)  # wdFormatOriginalFormatting
            except Exception:
                # Fallback to direct range formatting if Word cannot use the paste
                # special route for the current selection.
                target.FormattedText = source_range.FormattedText
            destination_doc.Save()
            self.status.set("Success: selected Word content preserved with its original formatting.")
            messagebox.showinfo(
                "Completed",
                "The selected content was inserted while preserving the original Word font and paragraph formatting."
            )
        except Exception as exc:
            self._show_error(exc)

    def _show_error(self, exc):
        self.status.set("Operation failed. See the error message.")
        if isinstance(exc, pywintypes.com_error) and exc.hresult == RPC_E_CALL_REJECTED:
            messagebox.showerror(
                "Word is busy",
                "Microsoft Word kept rejecting automation calls after the program retried them.\n\n"
                "Wait for Word to finish processing, close any open Word dialog, then try again."
            )
            return
        messagebox.showerror(
            "Word operation failed",
            "Microsoft Word could not complete the operation.\n\n"
            f"Details: {exc}\n\n"
            "Make sure the documents are not protected, Word is responsive, and the destination file is writable."
        )


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    WordCopyPasteManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
