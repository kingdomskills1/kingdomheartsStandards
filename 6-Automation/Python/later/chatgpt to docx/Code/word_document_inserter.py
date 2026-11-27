"""Word document insertion API used by the ChatGPT-to-Word app.

Requires Windows, desktop Microsoft Word, and pywin32.

Call ``WordDocumentInserter().copy_document_paths(source, destination)`` to
insert a complete source document at the end of an existing destination. Any
documents opened by the call are closed afterward; documents already open are
left open.
"""

import os
import time
import uuid
import zipfile
from xml.dom import minidom
import pythoncom
import pywintypes
import win32com.client


WD_COLLAPSE_END = 0
WD_ALERTS_NONE = 0
RPC_E_CALL_REJECTED = -2147418111


class WordDocumentInserter:
    """Insert complete Word documents while preserving Word formatting."""

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
                    return doc, False
            except pywintypes.com_error as exc:
                if exc.hresult == RPC_E_CALL_REJECTED:
                    raise
            except (AttributeError, OSError):
                pass
        return self._word_call(lambda: word.Documents.Open(full)), True

    def _destination_range(self, doc):
        paragraph_count = self._word_call(lambda: doc.Paragraphs.Count)
        last_paragraph = self._word_call(
            lambda: doc.Paragraphs(paragraph_count)
        )
        last_text = self._word_call(
            lambda: last_paragraph.Range.Text
        ).rstrip("\r\x07")

        rng = self._word_call(lambda: doc.Content)
        self._word_call(lambda: rng.Collapse(WD_COLLAPSE_END))
        if last_text and not last_text.endswith("\v"):
            self._word_call(lambda: rng.InsertBefore("\r"))
            self._word_call(lambda: rng.Collapse(WD_COLLAPSE_END))
        return rng

    def _preserve_inserted_fonts(self, source_doc, destination_doc, insertion_start):
        source_count = self._word_call(lambda: source_doc.Paragraphs.Count)
        destination_count = self._word_call(lambda: destination_doc.Paragraphs.Count)

        def paragraph_text(paragraph):
            return self._word_call(lambda: paragraph.Range.Text).rstrip("\r\x07").strip()

        destination_content = self._word_call(lambda: destination_doc.Content)
        destination_end = self._word_call(lambda: destination_content.End)
        inserted_range = self._word_call(
            lambda: destination_doc.Range(insertion_start, destination_end)
        )
        inserted_paragraphs = self._word_call(lambda: inserted_range.Paragraphs)
        inserted_count = self._word_call(lambda: inserted_paragraphs.Count)

        if source_count and inserted_count >= source_count:
            source_first = self._word_call(lambda: source_doc.Paragraphs(1))
            source_last = self._word_call(lambda: source_doc.Paragraphs(source_count))
            destination_first = self._word_call(lambda: inserted_paragraphs(1))
            destination_last = self._word_call(lambda: inserted_paragraphs(source_count))
            is_aligned = (
                self._word_call(lambda: destination_first.Range.Start) == insertion_start
                and paragraph_text(source_first) == paragraph_text(destination_first)
                and paragraph_text(source_last) == paragraph_text(destination_last)
            )
            if is_aligned:
                source_fonts = [
                    self._word_call(lambda: source_doc.Paragraphs(index).Range.Font.Name)
                    for index in range(1, source_count + 1)
                ]

                def set_font_range(first_index, last_index, font_name):
                    start = self._word_call(
                        lambda: inserted_paragraphs(first_index).Range.Start
                    )
                    end = self._word_call(
                        lambda: inserted_paragraphs(last_index).Range.End
                    )
                    self._word_call(
                        lambda: setattr(destination_doc.Range(start, end).Font,
                                        "Name", font_name)
                    )

                font_start = None
                previous_font = None
                for offset, source_font in enumerate(source_fonts, start=1):
                    if isinstance(source_font, str) and source_font:
                        if font_start is None:
                            font_start, previous_font = offset, source_font
                        elif source_font != previous_font:
                            set_font_range(font_start, offset - 1, previous_font)
                            font_start, previous_font = offset, source_font
                    elif font_start is not None:
                        set_font_range(font_start, offset - 1, previous_font)
                        font_start = previous_font = None

                if font_start is not None:
                    set_font_range(font_start, source_count, previous_font)
                return

        def word_text_length(text):
            return len(text.encode("utf-16-le", errors="surrogatepass")) // 2

        def split_paragraphs(text, start):
            paragraphs = []
            position = start
            text_index = 0
            while text_index < len(text):
                paragraph_end = text.find("\r", text_index)
                if paragraph_end == -1:
                    raw_text = text[text_index:]
                    end = position + word_text_length(raw_text)
                    paragraphs.append((raw_text.strip(), position, end))
                    break

                next_index = paragraph_end + 1
                if next_index < len(text) and text[next_index] == "\x07":
                    next_index += 1
                raw_text = text[text_index:next_index]
                end = position + word_text_length(raw_text)
                paragraphs.append((raw_text.rstrip("\r\x07").strip(), position, end))
                position = end
                text_index = next_index
            return paragraphs

        source_content = self._word_call(lambda: source_doc.Content)
        source_text = self._word_call(lambda: source_content.Text)
        source_start = self._word_call(lambda: source_content.Start)
        source_paragraphs = split_paragraphs(source_text, source_start)
        if len(source_paragraphs) != source_count:
            source_paragraphs = []
            for index in range(1, source_count + 1):
                paragraph = self._word_call(lambda: source_doc.Paragraphs(index))
                text = self._word_call(lambda: paragraph.Range.Text).rstrip("\r\x07").strip()
                source_paragraphs.append((text, 0, 0))

        source_fonts = [
            self._word_call(lambda: source_doc.Paragraphs(index).Range.Font.Name)
            for index in range(1, source_count + 1)
        ]
        source_texts = [text for text, _, _ in source_paragraphs]

        content_range = self._word_call(lambda: destination_doc.Content)
        content_text = self._word_call(lambda: content_range.Text)
        content_start = self._word_call(lambda: content_range.Start)
        bulk_destination = split_paragraphs(content_text, content_start)

        fast_destination = len(bulk_destination) == destination_count
        if fast_destination:
            candidates = [
                index for index in range(destination_count - source_count + 1)
                if [text for text, _, _ in bulk_destination[index:index + source_count]] == source_texts
            ]
            fast_destination = bool(candidates)

        if fast_destination:
            first_destination_paragraph = min(
                candidates,
                key=lambda index: abs(bulk_destination[index][1] - insertion_start)
            )
            actual_start = self._word_call(
                lambda: destination_doc.Paragraphs(first_destination_paragraph + 1).Range.Start
            )
            fast_destination = actual_start == bulk_destination[first_destination_paragraph][1]

        if fast_destination:
            font_start = None
            font_end = None
            previous_font = None
            for offset, source_font in enumerate(source_fonts):
                if isinstance(source_font, str) and source_font:
                    start, end = bulk_destination[first_destination_paragraph + offset][1:]
                    if font_start is None:
                        font_start, font_end, previous_font = start, end, source_font
                    elif source_font == previous_font:
                        font_end = end
                    else:
                        self._word_call(
                            lambda: setattr(destination_doc.Range(font_start, font_end).Font,
                                            "Name", previous_font)
                        )
                        font_start, font_end, previous_font = start, end, source_font
                elif font_start is not None:
                    self._word_call(
                        lambda: setattr(destination_doc.Range(font_start, font_end).Font,
                                        "Name", previous_font)
                    )
                    font_start = font_end = previous_font = None

            if font_start is not None:
                self._word_call(
                    lambda: setattr(destination_doc.Range(font_start, font_end).Font,
                                    "Name", previous_font)
                )
            return

        destination_paragraphs = []
        for index in range(1, destination_count + 1):
            paragraph = self._word_call(lambda: destination_doc.Paragraphs(index))
            text = self._word_call(lambda: paragraph.Range.Text).rstrip("\r\x07").strip()
            start = self._word_call(lambda: paragraph.Range.Start)
            destination_paragraphs.append((text, start))

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
        for offset, source_font in enumerate(source_fonts):
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

    def copy_document_paths(self, src, dst):
        """Insert a whole source document and close Word documents opened here."""
        if not src or not os.path.isfile(src):
            raise FileNotFoundError("Choose an existing source Word document.")
        if not dst or not os.path.isfile(dst):
            raise FileNotFoundError("Choose an existing destination Word document.")
        if os.path.abspath(src).lower() == os.path.abspath(dst).lower():
            raise ValueError("Source and destination must be different documents.")

        self._word = self._get_word()
        source_doc = None
        destination_doc = None
        source_opened = False
        destination_was_open = False
        destination_should_close = False
        try:
            source_doc, source_opened = self._open_doc(self._word, src)
            destination_doc, destination_opened = self._open_doc(self._word, dst)
            destination_was_open = not destination_opened
            destination_should_close = destination_opened

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
                destination_should_close = False
                try:
                    self._repair_inserted_list_numbering(src, dst, marker)
                except Exception as repair_error:
                    destination_doc, _ = self._open_doc(self._word, dst)
                    destination_should_close = not destination_was_open
                    try:
                        self._remove_temporary_marker(destination_doc, marker)
                    except Exception as cleanup_error:
                        raise RuntimeError(
                            f"{repair_error}; also failed to remove the temporary marker: {cleanup_error}"
                        ) from repair_error
                    raise
                destination_doc, _ = self._open_doc(self._word, dst)
                destination_should_close = not destination_was_open
            return open_xml_documents
        finally:
            try:
                if destination_should_close and destination_doc is not None:
                    self._word_call(lambda: destination_doc.Close(False))
            finally:
                if source_opened and source_doc is not None:
                    self._word_call(lambda: source_doc.Close(False))
