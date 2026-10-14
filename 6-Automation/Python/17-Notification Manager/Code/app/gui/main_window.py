from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QHeaderView,
    QInputDialog,
    QDialog,
    QDialogButtonBox,
    QLabel,
)

from app.gui.notification_dialog import NotificationDialog
from app.gui.icon import get_icon_path


class MainWindow(QMainWindow):
    def __init__(self, application):
        super().__init__()

        self.application = application
        self.notification_popup = None

        icon_path = get_icon_path()
        if icon_path is not None:
            self.setWindowIcon(QIcon(str(icon_path)))

        self.setWindowTitle("Notification Manager")
        self.resize(1000, 600)

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        # Top buttons
        buttons = QHBoxLayout()

        self.add_button = QPushButton("Add Notification")
        self.edit_button = QPushButton("Edit")
        self.delete_button = QPushButton("Delete")
        self.toggle_button = QPushButton("Enable / Disable")

        self.add_button.clicked.connect(self.add_notification)
        self.edit_button.clicked.connect(self.edit_notification)
        self.delete_button.clicked.connect(self.delete_notification)
        self.toggle_button.clicked.connect(self.toggle_notification)

        buttons.addWidget(self.add_button)
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.toggle_button)
        buttons.addStretch()

        layout.addLayout(buttons)

        # Notification table
        self.table = QTableWidget()
        self.table.setColumnCount(7)

        self.table.setHorizontalHeaderLabels([
            "Enabled",
            "Type",
            "Title",
            "Message",
            "Schedule",
            "Sound",
            "Sound File",
        ])

        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )

        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )

        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )

        header = self.table.horizontalHeader()

        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents
        )

        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents
        )

        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents
        )

        header.setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.Stretch
        )

        header.setSectionResizeMode(
            4,
            QHeaderView.ResizeMode.ResizeToContents
        )

        header.setSectionResizeMode(
            5,
            QHeaderView.ResizeMode.ResizeToContents
        )

        header.setSectionResizeMode(
            6,
            QHeaderView.ResizeMode.Stretch
        )

        self.table.doubleClicked.connect(
            lambda _: self.edit_notification()
        )

        layout.addWidget(self.table)

    @Slot(str)
    def on_notification_triggered(self, notification_id):
        notification = next(
            (
                item
                for item in self.application.notifications
                if item.id == notification_id
            ),
            None,
        )

        if notification is None:
            return

        self.show_notification_popup(notification)
        self.refresh()

    def show_notification_popup(self, notification):
        if notification is None:
            return None

        popup = self.notification_popup

        if popup is None:
            popup = QDialog(self)
            popup.setObjectName("notification_popup")
            popup.setMinimumWidth(360)
            popup.setMinimumHeight(160)

            layout = QVBoxLayout(popup)

            self.notification_popup_title = QLabel()
            self.notification_popup_title.setStyleSheet(
                "font-size: 16px; font-weight: bold;"
            )
            layout.addWidget(self.notification_popup_title)

            self.notification_popup_message = QLabel()
            self.notification_popup_message.setWordWrap(True)
            self.notification_popup_message.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            layout.addWidget(self.notification_popup_message)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
            )
            buttons.accepted.connect(popup.close)
            layout.addWidget(buttons)

            self.notification_popup = popup

        popup.setWindowTitle(notification.title or "Notification")
        self.notification_popup_title.setText(
            notification.title or "Notification"
        )
        self.notification_popup_message.setText(
            notification.message or ""
        )

        self.show()
        self.raise_()
        self.activateWindow()

        popup.show()
        popup.raise_()
        popup.activateWindow()

        return popup

    def refresh(self):
        self.table.setRowCount(0)

        notifications = self.application.notifications

        for notification in notifications:
            row = self.table.rowCount()
            self.table.insertRow(row)

            enabled_item = QTableWidgetItem(
                "Yes" if notification.enabled else "No"
            )

            type_handler = self.application.registry.get(
                notification.type
            )

            if type_handler:
                type_name = type_handler.display_name

                try:
                    schedule = type_handler.get_summary(
                        notification
                    )
                except Exception:
                    schedule = ""
            else:
                type_name = notification.type
                schedule = ""

            values = [
                enabled_item,
                QTableWidgetItem(type_name),
                QTableWidgetItem(notification.title),
                QTableWidgetItem(notification.message),
                QTableWidgetItem(schedule),
                QTableWidgetItem(
                    "Yes" if notification.sound_enabled else "No"
                ),
                QTableWidgetItem(notification.sound_file),
            ]

            for column, item in enumerate(values):
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    notification.id
                )

                self.table.setItem(row, column, item)

    def get_selected_notification(self):
        row = self.table.currentRow()

        if row < 0:
            return None

        item = self.table.item(row, 0)

        if item is None:
            return None

        notification_id = item.data(
            Qt.ItemDataRole.UserRole
        )

        for notification in self.application.notifications:
            if notification.id == notification_id:
                return notification

        return None

    def add_notification(self):
        handlers = self.application.registry.all()

        if not handlers:
            QMessageBox.information(
                self,
                "Add Notification",
                "No notification types are available.",
            )
            return

        type_name, accepted = QInputDialog.getItem(
            self,
            "Notification Type",
            "Choose a notification type:",
            [handler.display_name for handler in handlers],
            0,
            False,
        )

        if not accepted:
            return

        selected_handler = next(
            handler
            for handler in handlers
            if handler.display_name == type_name
        )

        dialog = NotificationDialog(
            registry=self.application.registry,
            initial_type=selected_handler.type_id,
            parent=self,
        )

        if dialog.exec():
            notification = dialog.get_notification()

            if notification is None:
                return

            self.application.add_notification(
                notification
            )

            self.refresh()

    def edit_notification(self):
        notification = self.get_selected_notification()

        if notification is None:
            QMessageBox.information(
                self,
                "Edit Notification",
                "Please select a notification first.",
            )
            return

        dialog = NotificationDialog(
            registry=self.application.registry,
            notification=notification,
            parent=self,
        )

        if dialog.exec():
            updated = dialog.get_notification()

            if updated is None:
                return

            self.application.update_notification(
                updated
            )

            self.refresh()

    def delete_notification(self):
        notification = self.get_selected_notification()

        if notification is None:
            QMessageBox.information(
                self,
                "Delete Notification",
                "Please select a notification first.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete Notification",
            f"Delete '{notification.title}'?",
        )

        if answer == QMessageBox.StandardButton.Yes:
            self.application.delete_notification(
                notification.id
            )

            self.refresh()

    def toggle_notification(self):
        notification = self.get_selected_notification()

        if notification is None:
            QMessageBox.information(
                self,
                "Notification",
                "Please select a notification first.",
            )
            return

        notification.enabled = not notification.enabled

        self.application.update_notification(
            notification
        )

        self.refresh()

    def closeEvent(self, event):
        # Closing the window hides it instead of
        # terminating the tray application.
        event.ignore()
        self.hide()