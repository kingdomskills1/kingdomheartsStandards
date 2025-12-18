"""Core functions for extracting and numbering headings from .docx files.

This module is separate so GUI and CLI can both import it without circular imports.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
import argparse
import re
from docx import Document
from pathlib import Path
from typing import List, Tuple
from docx import Document


def extract_headings_from_docx(path: Path) -> List[Tuple[int, str]]:
    doc = Document(path)
    headings: List[Tuple[int, str]] = []
    for p in doc.paragraphs:
        style = p.style
        if style is None:
            continue
        name = getattr(style, "name", "")
        if not name:
            continue
        if name.startswith("Heading"):
            parts = name.split()
            level = 1
            if len(parts) >= 2 and parts[-1].isdigit():
                try:
                    level = int(parts[-1])
                except Exception:
                    level = 1
            headings.append((level, p.text.strip()))
    return headings


def clean_heading_text(text: str) -> str:
    # Remove emojis and icons but KEEP ?, :, (), -
    text = re.sub(r'[^\w\s\-:\?\(\)]', '', text)

    # Remove leading numbers like "1-", "1.2-", "22-"
    text = re.sub(r'^\s*\d+(\.\d+)*\s*-\s*', '', text)

    # Remove trailing colon ONLY (keep ?)
    text = re.sub(r':\s*$', '', text)

    return text.strip()


def number_headings(headings: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    """
    Custom numbering rules:

    CASE A:
    - Exactly ONE Heading-1
    - Heading-3+ EXISTS
    → DROP Heading-1
    → Promote Heading-2 to top-level (1,2,3…)
    → Heading-3 becomes X.1, X.2…

    CASE B:
    - Exactly ONE Heading-1
    - Only Heading-2
    → Drop Heading-1, flat numbering

    CASE C:
    - Multiple Heading-1
    → Normal hierarchy
    """

    cleaned = [(lvl, clean_heading_text(text)) for lvl, text in headings]

    level1_count = sum(1 for lvl, _ in cleaned if lvl == 1)
    has_h3 = any(lvl >= 3 for lvl, _ in cleaned)

    numbered: list[tuple[int, str, str]] = []

    # ✅ CASE A: ONE H1 + H3 exists → RE-ROOT AT H2
    if level1_count == 1 and has_h3:
        top_counter = 0
        sub_counter = 0

        for lvl, text in cleaned:
            if lvl == 2:
                top_counter += 1
                sub_counter = 0
                numbered.append((1, str(top_counter), text))
            elif lvl == 3:
                sub_counter += 1
                numbered.append((2, f"{top_counter}.{sub_counter}", text))

        return numbered

    # ✅ CASE B: ONE H1 + ONLY H2
    if level1_count == 1:
        subs = [text for lvl, text in cleaned if lvl == 2]

        if not subs:
            top = next(text for lvl, text in cleaned if lvl == 1)
            return [(1, "1", top)]

        for i, text in enumerate(subs, 1):
            numbered.append((1, str(i), text))
        return numbered

    # ✅ CASE C: MULTIPLE H1 → NORMAL HIERARCHY
    counters = [0, 0, 0, 0]  # H1–H4

    for lvl, text in cleaned:
        if lvl > 4:
            continue

        counters[lvl - 1] += 1
        for i in range(lvl, 4):
            counters[i] = 0

        num = ".".join(str(counters[i]) for i in range(lvl))
        numbered.append((lvl, num, text))

    return numbered


def write_headings_text(out_path: Path, numbered: List[Tuple[str, str]]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for num, text in numbered:
            f.write(f"{num} {text}\n")

def write_numbered_docx(
    original: Path,
    out_path: Path,
    numbered: list[tuple[int, str, str]]
) -> None:
    from docx import Document

    doc = Document(original)
    new_doc = Document()

    # Build queues by heading level
    queues: dict[int, list[tuple[str, str]]] = {}
    for lvl, num, text in numbered:
        queues.setdefault(lvl, []).append((num, text))

    for p in doc.paragraphs:
        style = getattr(p, "style", None)
        name = getattr(style, "name", "") if style else ""

        if name.startswith("Heading"):
            try:
                lvl = int(name.split()[-1])
            except Exception:
                lvl = 1

            if lvl in queues and queues[lvl]:
                num, text = queues[lvl].pop(0)
                indent = "   " * (lvl - 1)
                new_doc.add_paragraph(f"{indent}{num}-{text}", style=name)
                continue

        new_doc.add_paragraph(p.text, style=name if name else None)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    new_doc.save(out_path)


def process_file(path: Path, out_dir: Path, write_docx: bool) -> None:
    headings = extract_headings_from_docx(path)
    numbered = number_headings(headings)
    base = path.stem
    text_out = out_dir / (base + "_headings.txt")
    write_headings_text(text_out, numbered)
    if write_docx:
        docx_out = out_dir / (base + "_numbered.docx")
        write_numbered_docx(path, docx_out, numbered)


def process_path(src: Path, out_dir: Path, recursive: bool, pattern: str, write_docx: bool) -> None:
    if src.is_file():
        if not src.name.startswith("~$"):
            process_file(src, out_dir, write_docx)
        return

    if recursive:
        matches = src.rglob(pattern)
    else:
        matches = src.glob(pattern)

    for p in matches:
        if p.is_file() and not p.name.startswith("~$"):
            process_file(p, out_dir / p.parent.relative_to(src), write_docx)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Copy and number heading names from .docx files")
    parser.add_argument("--src", required=True, help="Source .docx file or directory")
    parser.add_argument("--out", default="output", help="Output directory")
    parser.add_argument("--recursive", action="store_true", help="Search directories recursively")
    parser.add_argument("--pattern", default="*.docx", help="Glob pattern for files")
    parser.add_argument("--write-docx", action="store_true", help="Also write a numbered .docx copy")
    args = parser.parse_args(argv)

    src = Path(args.src)
    out = Path(args.out)
    if not src.exists():
        raise SystemExit(f"Source not found: {src}")
    process_path(src, out, args.recursive, args.pattern, args.write_docx)


if __name__ == "__main__":
    main()
