from abc import ABC, abstractmethod
from datetime import datetime

from app.core.models import Notification


class NotificationType(ABC):
    """
    Base class for every notification type.
    """

    # --------------------------------------------------
    # Identity
    # --------------------------------------------------

    @property
    @abstractmethod
    def type_id(self) -> str:
        """
        Internal ID.

        Example:

            date_time
            countdown
            daily
        """
        pass

    # --------------------------------------------------

    @property
    @abstractmethod
    def display_name(self) -> str:
        """
        Name shown to the user.

        Example:

            Date & Time
            Countdown
            Daily
        """
        pass

    # --------------------------------------------------
    # Scheduling
    # --------------------------------------------------

    @abstractmethod
    def get_next_run(
        self,
        notification: Notification,
        now: datetime
    ) -> datetime | None:
        """
        Return the next time this notification
        should fire.

        Return None if there is no next run.
        """
        pass

    # --------------------------------------------------
    # After notification fires
    # --------------------------------------------------

    @abstractmethod
    def get_next_after_trigger(
        self,
        notification: Notification,
        now: datetime
    ) -> datetime | None:
        """
        Calculate the next occurrence after
        this notification has fired.
        """
        pass

    def apply_next_run(
        self,
        notification: Notification,
        next_run: datetime | None,
    ):
        """Store the next occurrence or disable a completed notification."""

        if next_run is None:
            notification.enabled = False
            return

        notification.settings = {
            **notification.settings,
            "date": next_run.strftime("%Y-%m-%d"),
            "time": next_run.strftime("%H:%M:%S"),
        }

    # --------------------------------------------------
    # Editor
    # --------------------------------------------------

    @abstractmethod
    def create_editor(self, parent=None):
        """
        Return the QWidget/QDialog used to edit
        this notification type.
        """
        pass

    # --------------------------------------------------
    # Serialization
    # --------------------------------------------------

    def validate(
        self,
        notification: Notification
    ) -> tuple[bool, str]:

        return True, ""

    # --------------------------------------------------

    def get_summary(
        self,
        notification: Notification
    ) -> str:

        return self.display_name