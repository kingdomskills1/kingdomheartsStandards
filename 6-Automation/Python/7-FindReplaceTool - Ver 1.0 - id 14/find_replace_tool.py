import tkinter as tk
from tkinter import ttk
from tabs.find_tab import FindTab  # Import the FindTab class from the other file

# Create main window
root = tk.Tk()
root.title("FindReplaceTool")
root.geometry("600x400")

# Create a tab control
tab_control = ttk.Notebook(root)

## Start Find tab_control ##
# Tab 1 (Find tab using the class)
tab1 = ttk.Frame(tab_control)
tab_control.add(tab1, text="Find/replace")
# Initialize FindTab GUI in tab1
find_tab_gui = FindTab(tab1)
## end Find tab_control##

# Pack the tab control
tab_control.pack(expand=1, fill="both")

# Run the app
root.mainloop()
