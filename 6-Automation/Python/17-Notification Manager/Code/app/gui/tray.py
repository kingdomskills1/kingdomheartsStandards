from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QMenu,
    QStyle,
    QSystemTrayIcon,
)

from app.gui.icon import get_icon_path


class TrayIcon(QObject):
    """
    System tray integration for Notification Manager.
    """

    def __init__(self, application, main_window):
        super().__init__()

        self.application = application
        self.main_window = main_window

        icon_path = get_icon_path()
        if icon_path is not None:
            icon = QIcon(str(icon_path))
        else:
            # Fallback to a generic Qt icon if the custom icon is missing.
            icon = self.main_window.style().standardIcon(
                QStyle.StandardPixmap.SP_ComputerIcon
            )

        self.tray = QSystemTrayIcon(icon)
        self.tray.setIcon(icon)

        self.tray.setToolTip(
            "Notification Manager"
        )

        self._create_menu()

        self.tray.activated.connect(
            self._on_activated
        )

        self.tray.show()

    # ---------------------------------------------------------
    # MENU
    # ---------------------------------------------------------

    def _create_menu(self):
        menu = QMenu()

        # Open
        open_action = QAction(
            "Open Notification Manager",
            self,
        )

        open_action.triggered.connect(
            self.show_window
        )

        menu.addAction(open_action)

        # Add notification
        add_action = QAction(
            "Add Notification",
            self,
        )

        add_action.triggered.connect(
            self.main_window.add_notification
        )

        menu.addAction(add_action)

        menu.addSeparator()

        # Exit
        exit_action = QAction(
            "Exit",
            self,
        )

        exit_action.triggered.connect(
            self.exit_application
        )

        menu.addAction(exit_action)

        self.tray.setContextMenu(menu)

    # ---------------------------------------------------------
    # WINDOW
    # ---------------------------------------------------------

    def show_window(self):
        """
        Show and activate the main application window.
        """

        self.main_window.show()

        self.main_window.raise_()

        self.main_window.activateWindow()

    # ---------------------------------------------------------
    # TRAY EVENTS
    # ---------------------------------------------------------

    def _on_activated(self, reason):
        """
        Handle tray icon interaction.
        """

        if (
            reason
            == QSystemTrayIcon.ActivationReason.DoubleClick
        ):
            self.show_window()

    # ---------------------------------------------------------
    # EXIT
    # ---------------------------------------------------------

    def exit_application(self):
        """
        Completely shut down the application.
        """

        self.application.shutdown()