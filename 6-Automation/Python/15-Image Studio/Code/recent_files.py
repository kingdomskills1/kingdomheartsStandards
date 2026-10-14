import json
import os
from pathlib import Path


MAX_RECENT_FILES = 10


def recent_files_path():
    app_data = os.environ.get("APPDATA")
    data_directory = (
        Path(app_data) / "Image Viewer"
        if app_data
        else Path.home() / ".config" / "image-viewer"
    )
    return data_directory / "recent-files.json"


def load_recent_files():
    path = recent_files_path()
    try:
        with path.open(encoding="utf-8") as recent_file:
            saved_paths = json.load(recent_file)
    except FileNotFoundError:
        return []

    if not isinstance(saved_paths, list) or not all(
        isinstance(saved_path, str) for saved_path in saved_paths
    ):
        raise ValueError(f"Invalid recent files list in {path}")

    existing_paths = []
    seen_paths = set()
    for saved_path in saved_paths:
        file_path = Path(saved_path)
        normalized_path = os.path.normcase(str(file_path))
        if file_path.is_file() and normalized_path not in seen_paths:
            existing_paths.append(str(file_path))
            seen_paths.add(normalized_path)
        if len(existing_paths) == MAX_RECENT_FILES:
            break

    return existing_paths


def save_recent_files(paths):
    path = recent_files_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as recent_file:
        json.dump(paths[:MAX_RECENT_FILES], recent_file, indent=2)
    temporary_path.replace(path)


def add_recent_file(paths, filename):
    file_path = Path(filename).resolve()
    normalized_path = os.path.normcase(str(file_path))
    updated_paths = [str(file_path)]
    updated_paths.extend(
        saved_path
        for saved_path in paths
        if os.path.normcase(saved_path) != normalized_path
    )
    updated_paths = updated_paths[:MAX_RECENT_FILES]
    save_recent_files(updated_paths)
    return updated_paths
