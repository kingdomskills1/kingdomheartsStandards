"""
Core functions for extracting and numbering headings from .docx files.
Supports Heading 1 through Heading 9.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import List, Optional, Tuple
import argparse
import re
from docx import Document
from docx.oxml.ns import qn

MAX_LEVEL = 9


def _heading_level(paragraph) -> Optional[int]:
    style = paragraph.style
    name = getattr(style, "name", "") if style is not None else ""

    if name.startswith("Heading"):
        parts = name.split()
        level = int(parts[-1]) if len(parts) >= 2 and parts[-1].isdigit() else 1
        return level if 1 <= level <= MAX_LEVEL else None

    ppr = paragraph._p.pPr
    outline_level = ppr.find(qn("w:outlineLvl")) if ppr is not None else None
    if outline_level is not None:
        value = outline_level.get(qn("w:val"))
        if value is not None and value.isdigit():
            level = int(value) + 1
            return level if 1 <= level <= MAX_LEVEL else None

    return None


def _copy_outline_level(source, target) -> None:
    source_ppr = source._p.pPr
    outline_level = source_ppr.find(qn("w:outlineLvl")) if source_ppr is not None else None
    if outline_level is not None:
        target._p.get_or_add_pPr().append(deepcopy(outline_level))


def extract_headings_from_docx(path: Path) -> List[Tuple[int, str]]:
    doc = Document(path)
    headings: List[Tuple[int, str]] = []

    for p in doc.paragraphs:
        level = _heading_level(p)
        if level is not None:
            headings.append((level, p.text.strip()))

    return headings


def is_source_paragraph(text: str) -> bool:
    cleaned = text.strip()
    return bool(re.match(r'^(?:#\s*)?Source\s*:', cleaned, flags=re.IGNORECASE))


def clean_source_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def unique_sources(sources):
    seen_sources = set()
    for source in sources:
        source = clean_source_text(source)
        source_key = source.casefold()
        if source and source_key not in seen_sources:
            seen_sources.add(source_key)
            yield source


def source_category(source: str) -> str:
    match = re.match(
        r'^\s*#?\s*Source\s*:\s*(.+?)\s*:',
        source,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else "Other source"


def extract_headings_with_sources_from_docx(path: Path):
    doc = Document(path)
    entries = []
    current_index = None

    for p in doc.paragraphs:
        level = _heading_level(p)
        if level is not None:
            entries.append({"level": level, "text": p.text.strip(), "sources": []})
            current_index = len(entries) - 1
            continue

        if current_index is not None:
            text = p.text.strip()
            if text and is_source_paragraph(text):
                entries[current_index]["sources"].append(clean_source_text(text))

    return entries


def clean_heading_text(text: str) -> str:
    text = re.sub(r'^\s*\d+(?:\.\d+)*\s*-\s*', '', text)
    text = re.sub(r'[^\w\s\/\?\:\-\(\)#\.]', '', text)  # keep # and .
    text = re.sub(r':\s*$', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def _numbered_heading_indices(headings: List[Tuple[int, str]]) -> List[int]:
    level1_count = sum(1 for level, _ in headings if level == 1)
    has_h3_or_more = any(level >= 3 for level, _ in headings)

    if level1_count == 1 and has_h3_or_more:
        return [i for i, (level, _) in enumerate(headings) if level != 1]
    if level1_count == 1:
        matching = [i for i, (level, _) in enumerate(headings) if level == 2]
        if matching:
            return matching
        return [i for i, (level, _) in enumerate(headings) if level == 1]
    return list(range(len(headings)))


def number_headings(
    headings: List[Tuple[int, str]]
) -> List[Tuple[int, str, str]]:
    cleaned = [(lvl, clean_heading_text(text)) for lvl, text in headings]

    level1_count = sum(1 for lvl, _ in cleaned if lvl == 1)
    has_h3_or_more = any(lvl >= 3 for lvl, _ in cleaned)

    numbered: List[Tuple[int, str, str]] = []

    # Case: single H1 with deeper hierarchy → shift levels up
    if level1_count == 1 and has_h3_or_more:
        counters = [0] * MAX_LEVEL

        for lvl, text in cleaned:
            if lvl == 1:
                continue

            new_lvl = lvl - 1
            if new_lvl > MAX_LEVEL:
                continue

            counters[new_lvl - 1] += 1
            for i in range(new_lvl, MAX_LEVEL):
                counters[i] = 0

            num = ".".join(str(counters[i]) for i in range(new_lvl))
            numbered.append((new_lvl, num, text))

        return numbered

    # Case: single H1 with only H2 children
    if level1_count == 1:
        subs = [text for lvl, text in cleaned if lvl == 2]
        if not subs:
            top = next(text for lvl, text in cleaned if lvl == 1)
            return [(1, "1", top)]

        return [(1, str(i), text) for i, text in enumerate(subs, 1)]

    # Normal hierarchical numbering (H1–H9)
    counters = [0] * MAX_LEVEL

    for lvl, text in cleaned:
        if lvl > MAX_LEVEL:
            continue

        counters[lvl - 1] += 1
        for i in range(lvl, MAX_LEVEL):
            counters[i] = 0

        num = ".".join(str(counters[i]) for i in range(lvl))
        numbered.append((lvl, num, text))

    return numbered


def number_headings_with_sources(entries):
    raw_headings = [(entry["level"], entry["text"]) for entry in entries]
    numbered = number_headings(raw_headings)
    matching_entries = [entries[i] for i in _numbered_heading_indices(raw_headings)]

    result = []
    for (level, num, text), entry in zip(numbered, matching_entries):
        result.append((level, num, text, entry["sources"]))

    return result


def format_headings_with_sources(headings_with_sources):
    lines = []
    for level, num, text, sources in headings_with_sources:
        indent = "   " * (level - 1)
        lines.append(f"{indent}{num}-{text}")
        for source in sources:
            lines.append(source)

    return "\n".join(lines)


def format_sources(sources):
    grouped_sources = {}
    for source in unique_sources(sources):
        category = source_category(source)
        grouped_sources.setdefault(category, []).append(source)

    lines = []
    for category, category_sources in grouped_sources.items():
        lines.append(f"- {category}:")
        lines.extend(f"   * {source}" for source in category_sources)

    return "\n".join(lines)


def format_source_summary(sources):
    unique = list(unique_sources(sources))
    category_counts = {}
    category_labels = {}
    ai_categories = {"ai", "ai source", "ai sources"}

    for source in unique:
        category = source_category(source)
        category_key = category.casefold()
        if category_key in ai_categories:
            category_key = "ai sources"
            category_labels[category_key] = "AI Sources"
        else:
            label = category.strip()
            if label.casefold().endswith("source"):
                label = f"{label[:-6].rstrip()} Sources"
            elif not label.casefold().endswith("sources"):
                label = f"{label} Sources"
            category_labels.setdefault(category_key, label)

        category_counts[category_key] = category_counts.get(category_key, 0) + 1

    lines = [
        "- Source Summary:",
        f"   * Total Sources: {len(unique)}",
        f"   * AI Sources Number: {category_counts.get('ai sources', 0)}",
    ]
    for category_key, count in category_counts.items():
        if category_key != "ai sources":
            lines.append(f"   * {category_labels[category_key]} Number: {count}")

    return "\n".join(lines)


def write_numbered_docx(original: Path, out_path: Path, numbered):
    doc = Document(original)
    new_doc = Document()

    heading_paragraphs = []
    for i, paragraph in enumerate(doc.paragraphs):
        level = _heading_level(paragraph)
        if level is not None:
            heading_paragraphs.append((i, level, paragraph))
    heading_values = [
        (level, paragraph.text.strip())
        for _, level, paragraph in heading_paragraphs
    ]
    numbered_by_index = dict(
        zip(_numbered_heading_indices(heading_values), numbered)
    )
    paragraph_heading_indices = {
        paragraph_index: heading_index
        for heading_index, (paragraph_index, _, _) in enumerate(heading_paragraphs)
    }

    for paragraph_index, p in enumerate(doc.paragraphs):
        name = getattr(p.style, "name", "")
        level = _heading_level(p)
        heading_index = paragraph_heading_indices.get(paragraph_index)
        if heading_index is not None:
            numbered_heading = numbered_by_index.get(heading_index)
            if numbered_heading is not None:
                numbered_level, num, text = numbered_heading
                indent = "   " * (numbered_level - 1)
                new_paragraph = new_doc.add_paragraph(f"{indent}{num}-{text}", style=name)
                _copy_outline_level(p, new_paragraph)
                continue

            new_paragraph = new_doc.add_paragraph(p.text, style=name if name else None)
            if level is not None:
                _copy_outline_level(p, new_paragraph)
            continue

        new_doc.add_paragraph(p.text, style=name if name else None)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    new_doc.save(out_path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True)
    parser.add_argument("--out", default="output")
    parser.add_argument("--write-docx", action="store_true")
    parser.add_argument("--with-sources", action="store_true")
    args = parser.parse_args(argv)

    src = Path(args.src)
    out = Path(args.out)
    out.mkdir(exist_ok=True)

    headings = extract_headings_from_docx(src)
    numbered = number_headings(headings)

    if args.with_sources:
        entries = extract_headings_with_sources_from_docx(src)
        numbered_with_sources = number_headings_with_sources(entries)
        output_path = out / f"{src.stem}_with_sources.txt"
        output_path.write_text(format_headings_with_sources(numbered_with_sources), encoding="utf-8")
        print(output_path)

    if args.write_docx:
        write_numbered_docx(
            src,
            out / f"{src.stem}_numbered.docx",
            numbered
        )
