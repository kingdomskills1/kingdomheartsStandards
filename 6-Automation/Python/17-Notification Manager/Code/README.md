# Notification Manager

A Windows desktop notification utility for scheduling reminders, time-based alerts, and battery-level notifications.

The app is built with PySide6 and uses a modular notification system so new notification types can be added without changing the scheduler or application shell.

## Features

- Create, edit, enable, disable, and delete scheduled notifications
- Supports recurring time-based notifications
- Supports battery threshold reminders for plug-in / unplug events
- Stores notifications in JSON for persistence between runs
- Displays Windows toast notifications and optional sound playback
- Runs in the system tray so it stays available while the main window is hidden

## Supported notification types

### Date & Time

Schedule one-time or recurring reminders such as:

- single date/time reminders
- repeating intervals
- weekly reminders
- yearly reminders

### Battery Level

Trigger when battery condition crosses a threshold, such as:

- plug in at or below a chosen percentage
- unplug at or above a chosen percentage
- repeated reminders at a configurable interval

## Project structure

```text
.
├── main.py
├── app/
│   ├── core/
│   │   ├── application.py
│   │   ├── models.py
│   │   ├── notification_engine.py
│   │   ├── scheduler.py
│   │   └── storage.py
│   ├── gui/
│   │   ├── main_window.py
│   │   ├── notification_dialog.py
│   │   └── tray.py
│   └── notification_types/
│       ├── __init__.py
│       ├── base.py
│       ├── battery/
│       │   ├── editor.py
│       │   └── handler.py
│       └── date_time/
│           ├── __init__.py
│           ├── editor.py
│           └── handler.py
├── data/
│   └── notifications.json
└── README.md
```

## Requirements

- Python 3.10+
- Windows 10 or newer
- PySide6
- winotify

## Setup

1. Open a terminal in the project directory.
2. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install PySide6 winotify
```

## Run the app

```powershell
python main.py
```

## Data persistence

Saved notifications are stored in:

```text
data\notifications.json
```

The app reads and writes this JSON file automatically when notifications are added, edited, or removed.

## Notes

- The scheduler runs in a background thread and recalculates when notifications change.
- Battery notifications rely on Windows system APIs and are intended for Windows environments.
- Toast notifications are handled through the Windows notification system, while sound playback is controlled separately.

## License

This project is provided as-is for personal or local use. Add a license file if you want to publish or distribute it more formally.
