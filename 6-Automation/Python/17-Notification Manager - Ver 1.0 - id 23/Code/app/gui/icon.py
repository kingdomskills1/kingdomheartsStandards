import sys
from pathlib import Path


ICON_FILENAME = "Notification Manager Icon.ico"


def get_icon_path():
    if getattr(sys, "_MEIPASS", None):
        bundled_icon = Path(sys._MEIPASS) / ICON_FILENAME
        if bundled_icon.is_file():
            return bundled_icon

    project_icon = Path(__file__).resolve().parents[2] / ICON_FILENAME
    if project_icon.is_file():
        return project_icon

    if getattr(sys, "frozen", False):
        executable_icon = Path(sys.executable).resolve().parent / ICON_FILENAME
        if executable_icon.is_file():
            return executable_icon

    return None
