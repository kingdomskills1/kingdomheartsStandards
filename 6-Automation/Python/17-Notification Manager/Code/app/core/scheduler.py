import threading
import time
from datetime import datetime
from typing import Callable, Optional


class NotificationScheduler:
    """
    Generic notification scheduler.

    The scheduler itself does NOT know anything about individual
    notification types.

    Each notification type provides a handler through the registry:

        handler.get_next_run(notification, now)
        handler.get_next_after_trigger(notification, now)

    This allows new notification types to be added without changing
    this file.
    """

    def __init__(
        self,
        notifications,
        registry,
        on_trigger: Callable,
        on_changed: Optional[Callable] = None,
    ):
        self.notifications = notifications
        self.registry = registry

        self.on_trigger = on_trigger
        self.on_changed = on_changed

        self._running = False
        self._thread = None

        # Used to wake the scheduler when notifications are changed.
        self._wake_event = threading.Event()

        # Prevent two scheduler operations from modifying the
        # notification list at the same time.
        self._lock = threading.RLock()

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def start(self):
        """Start the scheduler background thread."""

        if self._running:
            return

        self._running = True

        self._thread = threading.Thread(
            target=self._run,
            name="NotificationScheduler",
            daemon=True,
        )

        self._thread.start()

    def stop(self):
        """Stop the scheduler background thread."""

        self._running = False

        # Wake the thread immediately.
        self._wake_event.set()

        if (
            self._thread is not None
            and self._thread.is_alive()
            and threading.current_thread() != self._thread
        ):
            self._thread.join(timeout=3)

        self._thread = None

    def refresh(self):
        """
        Tell the scheduler that notifications have changed.

        This causes the scheduler to immediately recalculate
        the next notification instead of waiting for its current
        sleep period to finish.
        """

        self._wake_event.set()

    # ---------------------------------------------------------
    # MAIN LOOP
    # ---------------------------------------------------------

    def _run(self):
        """
        Background scheduler loop.

        The loop calculates the closest upcoming notification
        and sleeps until that time.
        """

        while self._running:

            try:
                wait_seconds = self._process_notifications()

            except Exception as exc:
                print(
                    f"[Scheduler] Error: {exc}"
                )

                # Avoid a tight error loop.
                wait_seconds = 1.0

            if not self._running:
                break

            # Minimum wait prevents excessive CPU usage.
            wait_seconds = max(
                0.1,
                min(wait_seconds, 60.0),
            )

            # Wait can be interrupted by refresh().
            self._wake_event.wait(
                timeout=wait_seconds
            )

            # Clear the event after waking.
            self._wake_event.clear()

    # ---------------------------------------------------------
    # PROCESSING
    # ---------------------------------------------------------

    def _process_notifications(self):
        """
        Check all enabled notifications.

        Returns:
            Number of seconds until the next notification.
        """

        now = datetime.now()

        next_run_seconds = 60.0

        with self._lock:

            # Work on a copy so that the GUI/application can
            # safely replace notifications.
            notifications = list(
                self.notifications
            )

            for notification in notifications:

                if not notification.enabled:
                    continue

                handler = self.registry.get(
                    notification.type
                )

                if handler is None:
                    print(
                        "[Scheduler] Unknown notification "
                        f"type: {notification.type}"
                    )
                    continue

                try:
                    next_run = handler.get_next_run(
                        notification,
                        now,
                    )

                except Exception as exc:
                    print(
                        "[Scheduler] Failed to calculate "
                        f"next run for '{notification.title}': "
                        f"{exc}"
                    )

                    continue

                if next_run is None:
                    continue

                # Calculate seconds until execution.
                seconds_until = (
                    next_run - now
                ).total_seconds()

                # Notification is due.
                if seconds_until <= 0:

                    self._trigger_notification(
                        notification,
                        handler,
                        now,
                    )

                    # The notification may have been disabled
                    # or rescheduled after triggering.
                    #
                    # Recalculate from current time.
                    continue

                if seconds_until < next_run_seconds:
                    next_run_seconds = seconds_until

        return next_run_seconds

    # ---------------------------------------------------------
    # TRIGGER
    # ---------------------------------------------------------

    def _trigger_notification(
        self,
        notification,
        handler,
        now,
    ):
        """
        Trigger a notification and let its extension determine
        what happens afterward.
        """

        try:
            print(
                "[Scheduler] Triggering: "
                f"{notification.title}"
            )

            self.on_trigger(notification)

        except Exception as exc:
            print(
                "[Scheduler] Error while triggering "
                f"'{notification.title}': {exc}"
            )

        try:
            next_run = handler.get_next_after_trigger(
                notification,
                now,
            )

            handler.apply_next_run(
                notification,
                next_run,
            )

        except Exception as exc:
            print(
                "[Scheduler] Error rescheduling "
                f"for '{notification.title}': {exc}"
            )
            return

        if self.on_changed is not None:
            try:
                self.on_changed()

            except Exception as exc:
                print(
                    "[Scheduler] Error saving changes: "
                    f"{exc}"
                )

        self.refresh()

    # ---------------------------------------------------------
    # THREAD-SAFE NOTIFICATION ACCESS
    # ---------------------------------------------------------

    def set_notifications(self, notifications):
        """
        Replace the scheduler's notification list.

        Useful if the application replaces its list rather
        than modifying the existing list in-place.
        """

        with self._lock:
            self.notifications = notifications

        self.refresh()

    def add_notification(self, notification):
        """Add a notification."""

        with self._lock:
            self.notifications.append(
                notification
            )

        self.refresh()

    def remove_notification(self, notification_id):
        """Remove a notification by ID."""

        with self._lock:

            self.notifications[:] = [
                notification
                for notification in self.notifications
                if notification.id != notification_id
            ]

        self.refresh()