from datetime import datetime, timedelta

from app.core.models import Notification
from app.notification_types.base import NotificationType

from .editor import DateTimeEditor


class DateTimeNotificationType(
    NotificationType
):

    # --------------------------------------------------

    @property
    def type_id(self) -> str:

        return "date_time"

    # --------------------------------------------------

    @property
    def display_name(self) -> str:

        return "Date & Time"

    # --------------------------------------------------

    def create_editor(
        self,
        parent=None
    ):

        return DateTimeEditor(
            parent
        )

    # --------------------------------------------------

    def get_next_run(
        self,
        notification: Notification,
        now: datetime
    ):

        settings = notification.settings

        recurrence = self._get_recurrence(settings)

        if recurrence == "weekly":
            return self._next_weekly_run(
                settings,
                now,
                strictly_after=False,
            )

        if recurrence == "yearly":
            return self._next_yearly_run(
                settings,
                now,
                strictly_after=False,
            )

        date_text = settings.get(
            "date"
        )

        time_text = settings.get(
            "time"
        )

        if not date_text or not time_text:
            return None

        try:
            scheduled = datetime.fromisoformat(
                f"{date_text}T{time_text}"
            )

        except (TypeError, ValueError):
            return None

        return scheduled

    # --------------------------------------------------

    def get_next_after_trigger(
        self,
        notification: Notification,
        now: datetime
    ):

        settings = notification.settings
        recurrence = self._get_recurrence(settings)

        if recurrence == "once":
            return None

        if recurrence == "weekly":
            return self._next_weekly_run(
                settings,
                now,
                strictly_after=True,
            )

        if recurrence == "yearly":
            return self._next_yearly_run(
                settings,
                now,
                strictly_after=True,
            )

        try:
            repeat_seconds = int(
                settings.get("repeat_seconds", 0)
            )
        except (TypeError, ValueError):
            return None

        if repeat_seconds <= 0:
            return None

        scheduled = self.get_next_run(
            notification,
            now
        )

        if scheduled is None:
            return None

        # Find the next occurrence.
        next_time = scheduled

        while next_time <= now:

            next_time += timedelta(
                seconds=repeat_seconds
            )

        return next_time

    # --------------------------------------------------

    def validate(
        self,
        notification: Notification
    ):

        settings = notification.settings

        if not settings.get("time"):
            return False, "Time is required."

        try:
            parsed_time = datetime.strptime(
                settings["time"],
                "%H:%M:%S",
            ).time()
        except (TypeError, ValueError):
            return False, "Invalid date/time."

        recurrence = self._get_recurrence(settings)

        if recurrence in ("once", "interval"):
            if not settings.get("date"):
                return False, "Date is required."
            try:
                datetime.fromisoformat(
                    f"{settings['date']}T{settings['time']}"
                )
            except (TypeError, ValueError):
                return False, "Invalid date/time."

            if recurrence == "interval":
                try:
                    repeat_seconds = int(
                        settings.get("repeat_seconds", 0)
                    )
                except (TypeError, ValueError):
                    repeat_seconds = 0
                if repeat_seconds <= 0:
                    return False, (
                        "Repeat interval must be greater than zero."
                    )

        elif recurrence == "weekly":
            try:
                weekday = int(settings.get("weekday"))
            except (TypeError, ValueError):
                return False, "A day of the week is required."
            if not 0 <= weekday <= 6:
                return False, "Invalid day of the week."

        elif recurrence == "yearly":
            try:
                datetime(
                    2000,
                    int(settings.get("month")),
                    int(settings.get("day")),
                    parsed_time.hour,
                    parsed_time.minute,
                    parsed_time.second,
                )
            except (TypeError, ValueError):
                return False, "A valid month and day are required."

        else:
            return False, "Invalid repeat schedule."

        return True, ""

    # --------------------------------------------------

    def get_summary(
        self,
        notification: Notification
    ):

        settings = notification.settings
        recurrence = self._get_recurrence(settings)
        time = settings.get("time", "")

        if recurrence == "weekly":
            try:
                weekday = int(settings.get("weekday", -1))
                day_name = (
                    ("Monday", "Tuesday", "Wednesday", "Thursday",
                     "Friday", "Saturday", "Sunday")[weekday]
                    if 0 <= weekday <= 6
                    else "Weekly"
                )
            except (TypeError, ValueError):
                day_name = "Weekly"
            return f"{day_name} at {time}"

        if recurrence == "yearly":
            try:
                date = datetime(
                    2000,
                    int(settings.get("month")),
                    int(settings.get("day")),
                )
                return f"Every {date.strftime('%B')} {date.day} at {time}"
            except (TypeError, ValueError):
                return f"Annually at {time}"

        date = settings.get("date", "")
        summary = f"{date} {time}".strip()

        if recurrence == "interval":
            try:
                seconds = int(settings.get("repeat_seconds", 0))
            except (TypeError, ValueError):
                seconds = 0
            return f"{summary} (every {seconds} seconds)"

        return summary

    @staticmethod
    def _get_recurrence(settings):
        recurrence = settings.get("recurrence")
        if recurrence:
            return recurrence
        try:
            return (
                "interval"
                if int(settings.get("repeat_seconds", 0)) > 0
                else "once"
            )
        except (TypeError, ValueError):
            return "once"

    @staticmethod
    def _next_weekly_run(settings, now, strictly_after):
        try:
            weekday = int(settings.get("weekday"))
            scheduled_time = datetime.strptime(
                settings["time"],
                "%H:%M:%S",
            ).time()
        except (KeyError, TypeError, ValueError):
            return None

        if not 0 <= weekday <= 6:
            return None

        comparison_time = now.replace(microsecond=0)
        days_ahead = (weekday - now.weekday()) % 7
        candidate = datetime.combine(
            now.date() + timedelta(days=days_ahead),
            scheduled_time,
        )
        if candidate < comparison_time or (
            strictly_after and candidate <= comparison_time
        ):
            candidate += timedelta(days=7)
        return candidate

    @staticmethod
    def _next_yearly_run(settings, now, strictly_after):
        try:
            month = int(settings.get("month"))
            day = int(settings.get("day"))
            scheduled_time = datetime.strptime(
                settings["time"],
                "%H:%M:%S",
            ).time()
            datetime(2000, month, day)
        except (KeyError, TypeError, ValueError):
            return None

        comparison_time = now.replace(microsecond=0)
        for year in range(now.year, now.year + 9):
            try:
                candidate = datetime(
                    year,
                    month,
                    day,
                    scheduled_time.hour,
                    scheduled_time.minute,
                    scheduled_time.second,
                )
            except ValueError:
                continue

            if candidate > comparison_time or (
                not strictly_after and candidate == comparison_time
            ):
                return candidate

        return None