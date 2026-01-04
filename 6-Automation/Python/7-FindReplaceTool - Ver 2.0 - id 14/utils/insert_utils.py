# insert_utils.py
import os
import re
from docx import Document
from docx.shared import Pt
from .file_search import search_path  # <-- fixed import

def insert_at_matches(doc_or_text, pattern, insert_type, content="", repeat=1,
                      position="after", reference_position="0",
                      content_type_scope="all"):
    """
    Insert content at matches in TXT or DOCX files with line offset and debug prints.
    """
    total_insertions = 0
    is_docx = isinstance(doc_or_text, Document)

    # Determine insertion text
    if insert_type == "space":
        insert_text = " "
    elif insert_type == "newline":
        insert_text = "\n"
    else:  # content
        insert_text = content
    insert_text *= repeat

    # Convert reference_position to int
    try:
        line_offset = int(reference_position)
        if line_offset < 0:
            line_offset = 0
    except:
        line_offset = 0

    if is_docx:
        # DOCX processing
        for para_idx, para in enumerate(doc_or_text.paragraphs):
            lines = para.text.splitlines() or [""]  # ensure at least one line
            new_lines = lines.copy()
            for idx, line in enumerate(lines):
                if re.search(pattern, line):
                    # Determine target line index
                    target_idx = idx + line_offset if position == "after" else idx - line_offset
                    target_idx = max(0, min(target_idx, len(new_lines)-1))

                    # Debug print
                    print(f"[DOCX] Match at para {para_idx}, line {idx}, target_idx {target_idx}, "
                          f"position={position}, insert='{insert_text}'")

                    # Perform insertion
                    if insert_type == "newline":
                        insert_line = insert_text.rstrip("\n")
                        if position == "after":
                            new_lines.insert(target_idx + 1, insert_line)
                        else:
                            new_lines.insert(target_idx, insert_line)
                    else:
                        if position == "after":
                            new_lines[target_idx] += insert_text
                        else:
                            new_lines[target_idx] = insert_text + new_lines[target_idx]

                    total_insertions += 1

            para.text = "\n".join(new_lines)
        return total_insertions
    else:
        # TXT processing
        lines = doc_or_text.splitlines() or [""]
        new_lines = lines.copy()
        for idx, line in enumerate(lines):
            if re.search(pattern, line):
                target_idx = idx + line_offset if position == "after" else idx - line_offset
                target_idx = max(0, min(target_idx, len(new_lines)-1))

                print(f"[TXT] Match at line {idx}, target_idx {target_idx}, "
                      f"position={position}, insert='{insert_text}'")

                if insert_type == "newline":
                    insert_line = insert_text.rstrip("\n")
                    if position == "after":
                        new_lines.insert(target_idx + 1, insert_line)
                    else:
                        new_lines.insert(target_idx, insert_line)
                else:
                    if position == "after":
                        new_lines[target_idx] += insert_text
                    else:
                        new_lines[target_idx] = insert_text + new_lines[target_idx]

                total_insertions += 1

        return total_insertions, "\n".join(new_lines)

# -----------------------------
# Insert all files function
# -----------------------------
def insert_all_files(gui):
    """
    Searches files and applies insert_at_matches based on GUI settings.
    Allows per-file/folder selection of which insert fields to apply.
    """
    total_insertions = 0
    per_file_insertions = []

    # Search files using GUI parameters
    files = search_path(
        path=gui.entry_path.get(),
        search_text=gui.entry_search_text.get(),
        selected_type=gui.selected_type.get(),
        case_sensitive=gui.case_sensitive_var.get(),
        use_regex=gui.enable_regex_var.get(),
        search_subfolders=gui.subfolders_var.get(),
        txt_only=gui.txt_var.get(),
        doc_only=gui.doc_var.get(),
        pdf_only=gui.pdf_var.get(),
        content_type=gui.content_type_var.get()
    )

    if not files:
        return total_insertions, per_file_insertions

    for f in files:
        count = 0
        try:
            ext = os.path.splitext(f)[1].lower()
            
            # Determine which fields to apply based on GUI checkboxes
            # Example: gui.apply_position_var, gui.apply_repeat_var, gui.apply_content_var, etc.
            apply_position = gui.apply_position_var.get()
            apply_repeat = gui.apply_repeat_var.get()
            apply_content = gui.apply_content_var.get()

            # Extract GUI values only if allowed
            position = gui.insert_position_var.get() if apply_position else "after"
            repeat = int(gui.insert_repeat_var.get()) if apply_repeat else 1
            insert_type = gui.insert_content_type_var.get()
            content = gui.insert_content_text_var.get() if apply_content else ""

            if ext == ".docx":
                doc = Document(f)
                count = insert_at_matches(
                    doc,
                    pattern=gui.entry_search_text.get(),
                    insert_type=insert_type,
                    content=content,
                    repeat=repeat,
                    position=position,
                    reference_position=gui.insert_reference_var.get(),
                    content_type_scope=gui.content_type_var.get()
                )
                if count > 0:
                    doc.save(f)

            elif ext == ".txt":
                with open(f, "r", encoding="utf-8") as file:
                    text = file.read()
                count, new_text = insert_at_matches(
                    text,
                    pattern=gui.entry_search_text.get(),
                    insert_type=insert_type,
                    content=content,
                    repeat=repeat,
                    position=position,
                    reference_position=gui.insert_reference_var.get(),
                    content_type_scope=gui.content_type_var.get()
                )
                if count > 0:
                    with open(f, "w", encoding="utf-8") as file:
                        file.write(new_text)

        except Exception:
            continue  # skip problematic files

        if count > 0:
            total_insertions += count
            per_file_insertions.append((f, count))

    return total_insertions, per_file_insertions
