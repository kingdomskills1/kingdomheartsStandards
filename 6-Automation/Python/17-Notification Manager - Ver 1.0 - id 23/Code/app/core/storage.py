import json
import os
import shutil
import sys
from pathlib import Path

from app.core.models import Notification


class NotificationStorage:
    """
    Handles saving and loading notifications.

    Source runs use the project data directory. Frozen builds use
    the user's roaming AppData directory so one-file extraction cleanup
    cannot remove saved notifications.
    """

    def __init__(self, filename=None):

        if filename is None:
            if getattr(sys, "frozen", False):
                app_data = Path(
                    os.environ.get(
                        "APPDATA",
                        Path.home() / "AppData" / "Roaming",
                    )
                )
                filename = (
                    app_data
                    / "Notification Manager"
                    / "notifications.json"
                )
                self._migrate_frozen_data(filename)
            else:
                base_dir = Path(__file__).resolve().parents[2]
                filename = (
                    base_dir
                    / "data"
                    / "notifications.json"
                )

        self.filename = Path(filename)

        # Make sure the data directory exists.
        self.filename.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def _migrate_frozen_data(filename):
        if filename.exists():
            return

        bundle_dir = Path(
            getattr(sys, "_MEIPASS", Path(sys.executable).parent)
        )
        executable_dir = Path(sys.executable).resolve().parent

        for legacy_file in (
            bundle_dir / "data" / "notifications.json",
            executable_dir / "data" / "notifications.json",
        ):
            if legacy_file.is_file():
                filename.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy_file, filename)
                return

    # ---------------------------------------------------------
    # LOAD
    # ---------------------------------------------------------

    def load(self):
        """
        Load notifications from JSON.

        Returns:
            list[Notification]
        """

        if not self.filename.exists():
            return []

        try:
            with self.filename.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

        except json.JSONDecodeError as exc:
            print(
                "[Storage] Invalid JSON file: "
                f"{exc}"
            )

            return []

        except OSError as exc:
            print(
                "[Storage] Could not read "
                f"{self.filename}: {exc}"
            )

            return []

        if not isinstance(data, list):
            print(
                "[Storage] Expected a list of "
                "notifications."
            )

            return []

        notifications = []

        for item in data:

            if not isinstance(item, dict):
                continue

            try:
                item = self._migrate_old_format(
                    item
                )

                notifications.append(
                    Notification.from_dict(item)
                )

            except Exception as exc:
                print(
                    "[Storage] Could not load "
                    f"notification: {exc}"
                )

        return notifications

    # ---------------------------------------------------------
    # SAVE
    # ---------------------------------------------------------

    def save(self, notifications):
        """
        Save notifications to JSON.
        """

        self.filename.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = [
            notification.to_dict()
            for notification in notifications
        ]

        temporary_file = self.filename.with_suffix(
            ".tmp"
        )

        try:

            with temporary_file.open(
                "w",
                encoding="utf-8",
            ) as file:

                json.dump(
                    data,
                    file,
                    indent=4,
                    ensure_ascii=False,
                )

            # Replace the old file atomically.
            temporary_file.replace(
                self.filename
            )

        except OSError as exc:

            print(
                "[Storage] Could not save "
                f"{self.filename}: {exc}"
            )

            try:
                if temporary_file.exists():
                    temporary_file.unlink()
            except OSError:
                pass

    # ---------------------------------------------------------
    # MIGRATION
    # ---------------------------------------------------------

    def _migrate_old_format(self, item):
        """
        Convert notifications from the older format.

        Older versions stored Date & Time information like:

            {
                "notify_at": "...",
                "repeat_seconds": 60
            }

        The modular system stores it inside:

            "settings": {
                "date": "...",
                "time": "...",
                "repeat_seconds": 60
            }

        This allows existing notifications to continue working.
        """

        # Already using the new format.
        if "settings" in item:
            return item

        # Old Date & Time format.
        if "notify_at" in item:

            from datetime import datetime

            notify_at = item.get(
                "notify_at"
            )

            date_value = ""
            time_value = ""

            if notify_at:

                try:
                    dt = datetime.fromisoformat(
                        notify_at
                    )

                    date_value = dt.strftime(
                        "%Y-%m-%d"
                    )

                    time_value = dt.strftime(
                        "%H:%M:%S"
                    )

                except ValueError:
                    print(
                        "[Storage] Could not migrate "
                        f"date: {notify_at}"
                    )

            migrated = dict(item)

            migrated["type"] = (
                item.get(
                    "type",
                    "date_time",
                )
            )

            migrated["settings"] = {
                "date": date_value,
                "time": time_value,
                "repeat_seconds": item.get(
                    "repeat_seconds",
                    0,
                ),
            }

            migrated.pop(
                "notify_at",
                None,
            )

            migrated.pop(
                "repeat_seconds",
                None,
            )

            return migrated

        # Unknown old format.
        return item