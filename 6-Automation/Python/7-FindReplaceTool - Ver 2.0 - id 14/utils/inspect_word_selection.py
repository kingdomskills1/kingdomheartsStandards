# utils/inspect_word_selection.py
import win32com.client

HIGHLIGHT_MAP = {
    0: "None", 1: "Black", 2: "Blue", 3: "Turquoise",
    4: "Bright Green", 5: "Pink", 6: "Red", 7: "Yellow", 8: "White",
    9: "Dark Blue", 10: "Teal", 11: "Green", 12: "Violet",
    13: "Dark Red", 14: "Dark Yellow", 15: "Gray50", 16: "Gray25"
}

def inspect_word_selection():
    """
    Inspects each character in the current Word selection
    and prints Font, Size, Style, Highlight to CMD.
    """
    try:
        word = win32com.client.Dispatch("Word.Application")
        rng = word.Selection.Range

        text_content = rng.Text.strip()
        if not text_content:
            print("No text selected in Word.")
            return

        for i in range(1, len(rng.Text) + 1):
            char = rng.Characters(i)
            font = char.Font
            font_name = font.Name
            font_size = font.Size
            bold = "Bold" if font.Bold else ""
            italic = "Italic" if font.Italic else ""
            underline = "Underline" if font.Underline else ""


            # --- Text color ---
            try:
                color_rgb = font.Color  # OLE RGB (BGR order)
                # Convert to hex (Word uses BGR)
                r = color_rgb & 0xFF
                g = (color_rgb >> 8) & 0xFF
                b = (color_rgb >> 16) & 0xFF
                color_hex = f"#{r:02X}{g:02X}{b:02X}"
            except Exception:
                color_rgb = None
                color_hex = "Unknown"

            try:
                color_index = font.ColorIndex
            except Exception:
                color_index = "Unknown"

            # --- Highlight Color ---
            try:
                idx = char.HighlightColorIndex
                highlight = HIGHLIGHT_MAP.get(idx, f"Index {idx}")
            except Exception as e:
                highlight = "None"
                print(f"Highlight exception for char '{char.Text}' at position {i}: {e}")
                try:
                    idx = getattr(char, "HighlightColorIndex", None)
                    print(f"Raw HighlightColorIndex value: {idx}")
                except Exception as inner_e:
                    print(f"Could not get raw HighlightColorIndex: {inner_e}")

            info = (
                f"Char: '{char.Text}' | "
                f"Font: {font_name}, Size: {font_size}, "
                f"Style: {bold} {italic} {underline}, "
                f"TextColor: RGB={color_hex}, ColorIndex={color_index}, "                
                f"Highlight: {highlight}"
            )
            print(info)

    except Exception as e:
        print(f"Error inspecting Word selection: {e}")
