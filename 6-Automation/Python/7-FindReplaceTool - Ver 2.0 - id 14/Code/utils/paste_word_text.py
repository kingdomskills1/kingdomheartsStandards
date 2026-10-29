import tkinter as tk
import tkinter.font as tkFont
import win32com.client

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


def _paste_clipboard_into_word_range():
    word = win32com.client.DispatchEx("Word.Application")
    document = None
    try:
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Add()
        document.Content.Paste()
        rng = document.Content

        # Exclude Word's required final paragraph mark, not a copied paragraph mark.
        if rng.Text.endswith("\r"):
            rng.MoveEnd(Unit=1, Count=-1)
        if not rng.Text:
            raise ValueError("The clipboard does not contain pasteable Word content.")
        return word, document, rng
    except Exception:
        if document is not None:
            try:
                document.Close(SaveChanges=0)
            except Exception as e:
                print(f"Error closing temporary Word document: {e}")
        try:
            word.Quit()
        except Exception as e:
            print(f"Error closing temporary Word instance: {e}")
        raise


def paste_word_selection_into_text(text_widget, progress_callback=None):
    def report_progress(percent, message):
        if progress_callback is not None:
            progress_callback(percent, message)

    report_progress(0, "Starting paste")
    rng = None
    temporary_word = None
    temporary_document = None
    try:
        report_progress(5, "Checking Word selection")
        word = win32com.client.GetActiveObject("Word.Application")
        selection = word.Selection
        if selection is not None:
            selected_range = selection.Range
            if selected_range.Text:
                rng = selected_range
    except Exception as e:
        print(f"Error reading active Word selection: {e}")

    if rng is None:
        try:
            report_progress(10, "Reading formatted clipboard")
            temporary_word, temporary_document, rng = _paste_clipboard_into_word_range()
        except Exception as e:
            print(f"Error reading formatted Word clipboard: {e}")
            try:
                clipboard_text = text_widget.clipboard_get()
            except tk.TclError as clipboard_error:
                print(f"Error reading clipboard text: {clipboard_error}")
                report_progress(100, "Paste failed")
                return

            text_widget.delete("1.0", "end")
            text_widget.configure(background="white", foreground="black")
            text_widget.insert("1.0", clipboard_text)
            report_progress(100, "Paste complete")
            return

    try:
        # Clear previous content and reset defaults
        text_widget.delete("1.0", "end")
        text_widget.configure(background="white", foreground="black")

        # Tag to explicitly remove background for unhighlighted text
        text_widget.tag_config("no_bg", background="")

        font_cache = {}
        highlight_cache = {}
        character_count = rng.Characters.Count
        last_reported_percent = 20
        report_progress(20, "Applying formatting")

        for i in range(1, character_count + 1):
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

            percent = 20 + int(i * 75 / character_count) if character_count else 95
            if percent > last_reported_percent:
                report_progress(percent, "Applying formatting")
                last_reported_percent = percent

        report_progress(100, "Paste complete")
    except Exception as e:
        print(f"Error in paste_word_selection_into_text: {e}")
        report_progress(100, "Paste failed")
    finally:
        if temporary_document is not None:
            try:
                temporary_document.Close(SaveChanges=0)
            except Exception as e:
                print(f"Error closing temporary Word document: {e}")
        if temporary_word is not None:
            try:
                temporary_word.Quit()
            except Exception as e:
                print(f"Error closing temporary Word instance: {e}")
