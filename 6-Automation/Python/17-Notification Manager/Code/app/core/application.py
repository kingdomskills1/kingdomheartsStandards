import threading

from PySide6.QtCore import QMetaObject, Qt, Q_ARG
from PySide6.QtWidgets import QApplication

from app.core.storage import NotificationStorage
from app.core.scheduler import NotificationScheduler
from app.core.notification_engine import NotificationEngine

from app.gui.main_window import MainWindow
from app.gui.tray import TrayIcon

from app.notification_types import NotificationTypeRegistry


class NotificationApplication:
    def __init__(self):
        self.qt_app = QApplication.instance()

        if self.qt_app is None:
            self.qt_app = QApplication([])

        # Prevent the application from closing when
        # the main window is hidden.
        self.qt_app.setQuitOnLastWindowClosed(False)

        # Notification extensions
        self.registry = NotificationTypeRegistry()

        # Storage
        self.storage = NotificationStorage()

        # Load saved notifications
        self.notifications = self.storage.load()

        # Notification engine
        self.notification_engine = NotificationEngine()

        # Main window
        self.main_window = MainWindow(self)

        # Tray
        self.tray = TrayIcon(
            self,
            self.main_window,
        )

        # Scheduler
        self.scheduler = NotificationScheduler(
            notifications=self.notifications,
            registry=self.registry,
            on_trigger=self.handle_notification,
            on_changed=self.save_notifications,
        )

    def add_notification(self, notification):
        self.notifications.append(notification)

        self.save_notifications()

        self.scheduler.refresh()

    def update_notification(self, notification):
        for index, existing in enumerate(self.notifications):
            if existing.id == notification.id:
                self.notifications[index] = notification
                break

        self.save_notifications()

        self.scheduler.refresh()

    def delete_notification(self, notification_id):
        self.notifications = [
            notification
            for notification in self.notifications
            if notification.id != notification_id
        ]

        self.save_notifications()

        self.scheduler.refresh()

    def save_notifications(self):
        self.storage.save(self.notifications)

    def handle_notification(self, notification):
        if threading.current_thread() is threading.main_thread():
            self.main_window.on_notification_triggered(
                notification.id
            )
        else:
            QMetaObject.invokeMethod(
                self.main_window,
                "on_notification_triggered",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, notification.id),
            )

        self.notification_engine.show(
            notification
        )

        self.save_notifications()

    def run(self):
        self.scheduler.start()

        self.main_window.show()

        return self.qt_app.exec()

    def shutdown(self):
        self.scheduler.stop()

        self.save_notifications()

        self.tray.tray.hide()

        self.qt_app.quit()