import tkinter as tk
from tkinter import scrolledtext
import win32com.client

HIGHLIGHT_MAP = {
    0: "None", 1: "Black", 2: "Blue", 3: "Turquoise",
    4: "Bright Green", 5: "Pink", 6: "Red", 7: "Yellow", 8: "White",
    9: "Dark Blue", 10: "Teal", 11: "Green", 12: "Violet",
    13: "Dark Red", 14: "Dark Yellow", 15: "Gray50", 16: "Gray25"
}



def paste_from_word_selection():
    try:
        word = win32com.client.Dispatch("Word.Application")
        rng = word.Selection.Range

        text_area.delete(1.0, tk.END)

        text_content = rng.Text.strip()
        if not text_content:
            text_area.insert(tk.END, "No text selected in Word.\n")
            return

        for i in range(1, len(rng.Text)+1):
            char = rng.Characters(i)
            font = char.Font
            font_name = font.Name
            font_size = font.Size
            bold = "Bold" if font.Bold else ""
            italic = "Italic" if font.Italic else ""
            underline = "Underline" if font.Underline else ""
            
            try:
                idx = char.HighlightColorIndex
                highlight = HIGHLIGHT_MAP.get(idx, f"Index {idx}")
            except Exception as e:
                highlight = "None"
                print(f"Highlight exception for char '{char.Text}' at position {i}: {e}")
                try:
                    # Try printing the raw value anyway
                    idx = getattr(char, "HighlightColorIndex", None)
                    print(f"Raw HighlightColorIndex value: {idx}")
                except Exception as inner_e:
                    print(f"Could not get raw HighlightColorIndex: {inner_e}")

            info = (
                f"Char: '{char.Text}' | "
                f"Font: {font_name}, Size: {font_size}, "
                f"Style: {bold} {italic} {underline}, "
                f"Highlight: {highlight}\n"
            )
            text_area.insert(tk.END, info)

    except Exception as e:
        text_area.insert(tk.END, f"Error: {e}\n")

root = tk.Tk()
root.title("Word Selection Paste Tool - Letter Info")

paste_button = tk.Button(root, text="Paste", command=paste_from_word_selection)
paste_button.pack(pady=10)

text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=100, height=25)
text_area.pack(padx=10, pady=10)

root.mainloop()
