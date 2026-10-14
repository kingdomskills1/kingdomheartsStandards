from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QMenu,
    QStyle,
    QSystemTrayIcon,
)


class TrayIcon(QObject):
    """
    System tray integration for Notification Manager.
    """

    def __init__(self, application, main_window):
        super().__init__()

        self.application = application
        self.main_window = main_window

        self.tray = QSystemTrayIcon()

        # Use a standard Windows/Qt icon.
        #
        # Important:
        # QStyle.SP_ComputerIcon is the correct enum.
        icon = self.main_window.style().standardIcon(
            QStyle.StandardPixmap.SP_ComputerIcon
        )

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