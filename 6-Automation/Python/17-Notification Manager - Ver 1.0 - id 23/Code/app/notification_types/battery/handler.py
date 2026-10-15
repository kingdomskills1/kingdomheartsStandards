import ctypes
from datetime import datetime, timedelta

from app.core.models import Notification
from app.notification_types.base import NotificationType

from .editor import BatteryEditor


class _SystemPowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


class BatteryNotificationType(NotificationType):
    POLL_INTERVAL_SECONDS = 15
    DEFAULT_REPEAT_SECONDS = 60
    MIN_REPEAT_SECONDS = 5
    MAX_REPEAT_SECONDS = 31536000

    @property
    def type_id(self) -> str:
        return "battery"

    @property
    def display_name(self) -> str:
        return "Battery Level"

    def create_editor(self, parent=None):
        return BatteryEditor(parent)

    def get_battery_status(self):
        try:
            status = _SystemPowerStatus()
            succeeded = ctypes.windll.kernel32.GetSystemPowerStatus(
                ctypes.byref(status)
            )
        except (AttributeError, OSError):
            return None

        if (
            not succeeded
            or status.ACLineStatus not in (0, 1)
            or status.BatteryLifePercent > 100
        ):
            return None

        return status.ACLineStatus == 1, status.BatteryLifePercent

    def _condition_matches(self, settings, status):
        if status is None:
            return False

        mode = settings.get("mode", "plug_in")
        try:
            threshold = int(settings.get("threshold", 35))
        except (TypeError, ValueError):
            return False

        plugged_in, percentage = status

        if mode == "plug_in":
            return not plugged_in and percentage <= threshold

        if mode == "unplug":
            return plugged_in and percentage >= threshold

        return False

    def get_next_run(
        self,
        notification: Notification,
        now: datetime,
    ):
        settings = notification.settings
        if not self._condition_matches(
            settings,
            self.get_battery_status(),
        ):
            return now + timedelta(
                seconds=self.POLL_INTERVAL_SECONDS
            )

        reminder_text = settings.get("next_reminder_at")
        if reminder_text:
            try:
                reminder_at = datetime.fromisoformat(reminder_text)
            except (TypeError, ValueError):
                reminder_at = now

            if reminder_at > now:
                return reminder_at

        return now

    def get_next_after_trigger(
        self,
        notification: Notification,
        now: datetime,
    ):
        try:
            repeat_seconds = int(
                notification.settings.get(
                    "repeat_seconds",
                    self.DEFAULT_REPEAT_SECONDS,
                )
            )
        except (TypeError, ValueError):
            repeat_seconds = self.DEFAULT_REPEAT_SECONDS

        return now + timedelta(
            seconds=max(self.MIN_REPEAT_SECONDS, repeat_seconds)
        )

    def apply_next_run(
        self,
        notification: Notification,
        next_run: datetime | None,
    ):
        if next_run is None:
            notification.enabled = False
            return

        notification.settings = {
            **notification.settings,
            "next_reminder_at": next_run.isoformat(),
        }

    def validate(self, notification: Notification):
        settings = notification.settings
        if settings.get("mode") not in ("plug_in", "unplug"):
            return False, "Choose whether to plug in or unplug."

        try:
            threshold = int(settings.get("threshold"))
        except (TypeError, ValueError):
            return False, "Enter a valid battery percentage."

        if not 1 <= threshold <= 100:
            return False, "Battery percentage must be between 1 and 100."

        try:
            repeat_seconds = int(
                settings.get(
                    "repeat_seconds",
                    self.DEFAULT_REPEAT_SECONDS,
                )
            )
        except (TypeError, ValueError):
            return False, "Enter a valid repeat interval."

        if not self.MIN_REPEAT_SECONDS <= repeat_seconds <= self.MAX_REPEAT_SECONDS:
            return False, "Repeat interval must be at least 5 seconds."

        return True, ""

    def get_summary(self, notification: Notification):
        settings = notification.settings
        threshold = settings.get("threshold", 35)
        repeat_seconds = settings.get(
            "repeat_seconds",
            self.DEFAULT_REPEAT_SECONDS,
        )

        if settings.get("mode", "plug_in") == "unplug":
            return f"Unplug at {threshold}% (every {repeat_seconds}s)"

        return f"Plug in at {threshold}% (every {repeat_seconds}s)"