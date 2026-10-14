import os
import winsound

from winotify import Notification, audio


class NotificationEngine:
    """
    Handles the actual delivery of notifications.

    This class is intentionally independent of notification types.
    The scheduler decides WHEN a notification should happen.
    The engine decides HOW it is displayed.
    """

    APP_NAME = "Notification Manager"

    def __init__(self):
        pass

    def show(self, notification):
        """
        Display a Windows toast notification and optionally
        play a sound.
        """

        self._show_toast(notification)

        if notification.sound_enabled:
            self._play_sound(
                notification.sound_file
            )

    # ---------------------------------------------------------
    # WINDOWS TOAST
    # ---------------------------------------------------------

    def _show_toast(self, notification):
        """
        Display the Windows notification.
        """

        try:
            toast = Notification(
                app_id=self.APP_NAME,
                title=notification.title or "Notification",
                msg=notification.message or "",
            )

            # Don't use the default winotify sound because
            # we handle sound separately below.
            toast.set_audio(
                audio.Silent,
                loop=False,
            )

            toast.show()

        except Exception as exc:
            print(
                "[NotificationEngine] Failed to show "
                f"notification: {exc}"
            )

    # ---------------------------------------------------------
    # SOUND
    # ---------------------------------------------------------

    def _play_sound(self, sound_file):
        """
        Play the configured sound file.

        If no custom file is configured, Windows' default
        notification sound is used.
        """

        if not sound_file:
            try:
                winsound.MessageBeep(
                    winsound.MB_ICONASTERISK
                )

            except Exception as exc:
                print(
                    "[NotificationEngine] Failed to play "
                    f"default sound: {exc}"
                )

            return

        # Expand things such as:
        # %USERPROFILE%
        # %APPDATA%
        # etc.
        sound_file = os.path.expandvars(
            sound_file
        )

        # Convert to absolute path.
        sound_file = os.path.abspath(
            sound_file
        )

        if not os.path.isfile(sound_file):
            print(
                "[NotificationEngine] Sound file "
                f"not found: {sound_file}"
            )
            return

        try:
            winsound.PlaySound(
                sound_file,
                winsound.SND_FILENAME
                | winsound.SND_ASYNC,
            )

        except Exception as exc:
            print(
                "[NotificationEngine] Failed to play "
                f"sound '{sound_file}': {exc}"
            )