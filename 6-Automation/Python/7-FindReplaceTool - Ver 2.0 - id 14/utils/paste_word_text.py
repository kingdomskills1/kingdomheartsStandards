import tkinter.font as tkFont
import win32com.client
from utils.inspect_word_selection import inspect_word_selection

# Word highlight index → name
HIGHLIGHT_MAP = {
    0: "None", 1: "Black", 2: "Blue", 3: "Turquoise",
    4: "Bright Green", 5: "Pink", 6: "Red", 7: "Yellow", 8: "White",
    9: "Dark Blue", 10: "Teal", 11: "Green", 12: "Violet",
    13: "Dark Red", 14: "Dark Yellow", 15: "Gray50", 16: "Gray25"
}

# Word highlight name → Tk color
WORD_TO_COLOR = {
    "Black": "#000000",  # Black highlight is rendered as black
    "Blue": "#0000FF", "Turquoise": "#00FFFF",
    "Bright Green": "#00FF00", "Pink": "#FFC0CB", "Red": "#FF0000",
    "Yellow": "#FFFF00", "White": "#FFFFFF", "Dark Blue": "#00008B",
    "Teal": "#008080", "Green": "#008000", "Violet": "#EE82EE",
    "Dark Red": "#8B0000", "Dark Yellow": "#9B870C",
    "Gray50": "#808080", "Gray25": "#C0C0C0"
}

def paste_word_selection_into_text(text_widget):
    try:
        inspect_word_selection()

        word = win32com.client.GetActiveObject("Word.Application")
        rng = word.Selection.Range

        # Clear previous content and reset defaults
        text_widget.delete("1.0", "end")
        text_widget.configure(background="white", foreground="black")

        # Tag to explicitly remove background for unhighlighted text
        text_widget.tag_config("no_bg", background="")

        font_cache = {}
        highlight_cache = {}

        for i in range(1, rng.Characters.Count + 1):
            char = rng.Characters(i)
            ch = char.Text
            is_paragraph = (ch == "\r")

            start = text_widget.index("insert")
            text_widget.insert("insert", ch)
            end = text_widget.index("insert")

            # -------------------
            # HIGHLIGHT
            # -------------------
            bg_color = None

            # 1️⃣ Modern Word highlight
            try:
                idx = char.HighlightColorIndex
                if idx and idx != 0:
                    name = HIGHLIGHT_MAP.get(idx)
                    bg_color = WORD_TO_COLOR.get(name)
            except Exception as e:
                print(f"Error reading modern highlight: {e}")

            # 2️⃣ Old-document shading
            if not bg_color:
                try:
                    shade = char.Shading.BackgroundPatternColor

                    # Ignore paragraph mark shading only
                    if is_paragraph:
                        shade = None

                    # Only apply shading if it's non-zero AND not "black default"
                    if shade and shade != 0 and shade != -16777216:
                        r = shade & 0xFF
                        g = (shade >> 8) & 0xFF
                        b = (shade >> 16) & 0xFF
                        bg_color = f"#{r:02X}{g:02X}{b:02X}"

                except Exception as e:
                    print(f"Error reading old shading: {e}")

            # -------------------
            # Apply highlight tag if present
            # -------------------
            if bg_color and not is_paragraph:
                tag = highlight_cache.get(bg_color)
                if not tag:
                    tag = f"highlight_{len(highlight_cache)}"
                    text_widget.tag_config(tag, background=bg_color)
                    highlight_cache[bg_color] = tag
                text_widget.tag_add(tag, start, end)


            # -------------------
            # Explicitly clear background for non-highlighted text
            # -------------------
            if not bg_color or is_paragraph:
                text_widget.tag_add("no_bg", start, end)

            # -------------------
            # FONT & TEXT COLOR
            # -------------------
            font_name = char.Font.Name or "Arial"
            font_size = int(char.Font.Size) if char.Font.Size else 12
            bold = bool(char.Font.Bold)
            italic = bool(char.Font.Italic)

            fg_color = None
            try:
                color = char.Font.Color  # OLE_COLOR from Word

                # Convert signed 32-bit to unsigned
                color = color & 0xFFFFFFFF

                # Word stores low 24 bits as BGR
                # Extract bytes
                b = (color >> 16) & 0xFF
                g = (color >> 8) & 0xFF
                r = color & 0xFF

                # Compose RGB hex string
                fg_color = f"#{r:02X}{g:02X}{b:02X}"

                # Optional: remap Word automatic colors if needed
                if fg_color in ("#FFFF00", "#00FFFF"):  # example for highlight-adapted white
                    fg_color = "#FFFFFF"

            except Exception as e:
                print(f"Error reading font color: {e}")




            font_key = (font_name, font_size, bold, italic, fg_color)
            tag = font_cache.get(font_key)

            if not tag:
                tag = f"font_{len(font_cache)}"
                tk_font = tkFont.Font(
                    family=font_name,
                    size=font_size,
                    weight="bold" if bold else "normal",
                    slant="italic" if italic else "roman"
                )
                if fg_color:
                    text_widget.tag_config(tag, font=tk_font, foreground=fg_color)
                else:
                    text_widget.tag_config(tag, font=tk_font, foreground="")  # reset to default
                font_cache[font_key] = tag

            text_widget.tag_add(tag, start, end)

    except Exception as e:
        print(f"Error in paste_word_selection_into_text: {e}")
