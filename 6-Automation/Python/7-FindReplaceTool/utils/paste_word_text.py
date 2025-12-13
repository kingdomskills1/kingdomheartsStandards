# utils/paste_word_text.py
import tkinter.font as tkFont
import win32com.client
from utils.inspect_word_selection import inspect_word_selection

HIGHLIGHT_MAP = {
    0: "None", 1: "Black", 2: "Blue", 3: "Turquoise",
    4: "Bright Green", 5: "Pink", 6: "Red", 7: "Yellow", 8: "White",
    9: "Dark Blue", 10: "Teal", 11: "Green", 12: "Violet",
    13: "Dark Red", 14: "Dark Yellow", 15: "Gray50", 16: "Gray25"
}

WORD_TO_COLOR = {
    "Black": "#000000", "Blue": "#0000FF", "Turquoise": "#00FFFF",
    "Bright Green": "#00FF00", "Pink": "#FFC0CB", "Red": "#FF0000",
    "Yellow": "#FFFF00", "White": "#FFFFFF", "Dark Blue": "#00008B",
    "Teal": "#008080", "Green": "#008000", "Violet": "#EE82EE",
    "Dark Red": "#8B0000", "Dark Yellow": "#9B870C",
    "Gray50": "#808080", "Gray25": "#C0C0C0", "None": None
}


def paste_word_selection_into_text(text_widget):
    """
    Paste Word selection into a Tkinter Text widget with:
    - Highlight color
    - Font family
    - Font size
    - Bold / Italic
    """
    try:
        inspect_word_selection()
        
        word = win32com.client.Dispatch("Word.Application")
        rng = word.Selection.Range

        text_widget.delete("1.0", "end")

        for i in range(1, len(rng.Text) + 1):
            char = rng.Characters(i)
            ch = char.Text

            # Track insert position
            start = text_widget.index("insert")
            text_widget.insert("insert", ch)
            end = text_widget.index("insert")

            # -------------------
            # Highlight
            # -------------------
            try:
                idx = char.HighlightColorIndex
                highlight_name = HIGHLIGHT_MAP.get(idx, "None")
            except:
                highlight_name = "None"

            bg_color = WORD_TO_COLOR.get(highlight_name)
            if bg_color:
                tag_name = f"highlight_{i}"
                text_widget.tag_add(tag_name, start, end)
                text_widget.tag_config(tag_name, background=bg_color)

            # -------------------
            # Font family, size, style
            # -------------------
            font_name = char.Font.Name or "Arial"
            font_size = int(char.Font.Size) if char.Font.Size else 12
            bold = bool(char.Font.Bold)
            italic = bool(char.Font.Italic)

            font_tag = f"font_{i}"
            text_widget.tag_add(font_tag, start, end)
            tk_font = tkFont.Font(
                family=font_name,
                size=font_size,
                weight="bold" if bold else "normal",
                slant="italic" if italic else "roman"
            )
            text_widget.tag_config(font_tag, font=tk_font)

    except Exception as e:
        print(f"Error in paste_word_selection_into_text: {e}")
