def remove_blank_line_at_matches(doc_or_text, matches_list, position):
    removed_total = 0

    # ===================== TXT =====================
    if isinstance(doc_or_text, str):
        lines = doc_or_text.splitlines(keepends=True)

        used_lines = set()

        for line_no, _, _ in matches_list:
            idx = line_no - 1
            if idx in used_lines:
                continue
            used_lines.add(idx)

            # 1️⃣ real blank line
            if position == "before" and idx > 0:
                if lines[idx - 1].strip() == "":
                    del lines[idx - 1]
                    removed_total += 1
                    continue

            if position == "after" and idx + 1 < len(lines):
                if lines[idx + 1].strip() == "":
                    del lines[idx + 1]
                    removed_total += 1
                    continue

            # 2️⃣ fallback: one '\n'
            if "\n" in lines[idx]:
                lines[idx] = lines[idx].replace("\n", "", 1)
                removed_total += 1

        return removed_total, "".join(lines)

    # ===================== DOCX =====================
    doc = doc_or_text
    paragraphs = doc.paragraphs

    processed_paragraph_ids = set()

    for _, match_text, _ in matches_list:
        match_text = match_text.strip()

        for i, p in enumerate(paragraphs):
            if match_text not in p.text:
                continue

            pid = id(p)
            if pid in processed_paragraph_ids:
                continue  # 🔒 already handled
            processed_paragraph_ids.add(pid)

            print(f"[DEBUG] Matched paragraph idx {i}")

            # ---------------------------
            # 1️⃣ REAL BLANK PARAGRAPH
            # ---------------------------
            if position == "before" and i > 0:
                prev_p = paragraphs[i - 1]
                parent = prev_p._element.getparent()
                if parent is not None and not prev_p.text.strip():
                    parent.remove(prev_p._element)
                    removed_total += 1
                    continue

            if position == "after" and i + 1 < len(paragraphs):
                next_p = paragraphs[i + 1]
                parent = next_p._element.getparent()
                if parent is not None and not next_p.text.strip():
                    parent.remove(next_p._element)
                    removed_total += 1
                    continue

            # ---------------------------
            # 2️⃣ FALLBACK: '\n' INSIDE SAME PARAGRAPH
            # ---------------------------
            for run in p.runs:
                if "\n" in run.text:
                    run.text = run.text.replace("\n", "", 1)
                    removed_total += 1
                    print("[DEBUG] Removed ONE '\\n' inside paragraph")
                    break

    return removed_total, doc

def remove_all_blank_lines_at_matches(doc_or_text, matches_list, position):
    removed_total = 0

    # ===================== TXT =====================
    if isinstance(doc_or_text, str):
        lines = doc_or_text.splitlines(keepends=True)
        used_lines = set()

        for line_no, _, _ in matches_list:
            idx = line_no - 1
            if idx in used_lines:
                continue
            used_lines.add(idx)

            # Remove all blank lines before/after
            if position == "before":
                while idx > 0 and lines[idx - 1].strip() == "":
                    del lines[idx - 1]
                    idx -= 1
                    removed_total += 1

            elif position == "after":
                while idx + 1 < len(lines) and lines[idx + 1].strip() == "":
                    del lines[idx + 1]
                    removed_total += 1

            # Remove all extra '\n' inside the line
            while "\n" in lines[idx]:
                lines[idx] = lines[idx].replace("\n", "", 1)
                removed_total += 1

        return removed_total, "".join(lines)

    # ===================== DOCX =====================
    doc = doc_or_text
    paragraphs = doc.paragraphs
    processed_paragraph_ids = set()

    for _, match_text, _ in matches_list:
        match_text = match_text.strip()

        for i, p in enumerate(paragraphs):
            if match_text not in p.text:
                continue

            pid = id(p)
            if pid in processed_paragraph_ids:
                continue
            processed_paragraph_ids.add(pid)

            print(f"[DEBUG] Matched paragraph idx {i}")

            # ---------------------------
            # Remove all real blank paragraphs
            # ---------------------------
            if position == "before" and i > 0:
                while i > 0:
                    prev_p = paragraphs[i - 1]
                    parent = prev_p._element.getparent()
                    if parent is not None and not prev_p.text.strip():
                        parent.remove(prev_p._element)
                        removed_total += 1
                        i -= 1
                    else:
                        break

            if position == "after" and i + 1 < len(paragraphs):
                while i + 1 < len(paragraphs):
                    next_p = paragraphs[i + 1]
                    parent = next_p._element.getparent()
                    if parent is not None and not next_p.text.strip():
                        parent.remove(next_p._element)
                        removed_total += 1
                    else:
                        break

            # ---------------------------
            # Remove all '\n' inside paragraph
            # ---------------------------
            for run in p.runs:
                while "\n" in run.text:
                    run.text = run.text.replace("\n", "", 1)
                    removed_total += 1
                    print("[DEBUG] Removed ONE '\\n' inside paragraph")

    return removed_total, doc
