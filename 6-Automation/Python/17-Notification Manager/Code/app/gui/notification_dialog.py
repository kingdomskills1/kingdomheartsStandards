from PySide6.QtCore import QTime, QDate
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QCheckBox,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QSpinBox,
    QWidget,
)

from app.core.models import Notification


class NotificationDialog(QDialog):
    """
    Dialog for creating and editing notifications.

    Common notification fields are handled here.

    Type-specific fields are provided by the selected
    notification extension.
    """

    def __init__(
        self,
        registry,
        notification=None,
        initial_type=None,
        parent=None,
    ):
        super().__init__(parent)

        self.registry = registry
        self.notification = notification
        self.initial_type = initial_type

        self.type_editor = None
        self.current_handler = None

        self.setWindowTitle(
            "Edit Notification"
            if notification
            else "New Notification"
        )

        self.resize(600, 600)

        self._build_ui()
        self._load_notification()

    # =========================================================
    # UI
    # =========================================================

    def _build_ui(self):

        main_layout = QVBoxLayout(self)

        # -----------------------------------------------------
        # Common fields
        # -----------------------------------------------------

        form = QFormLayout()

        # Type
        self.type_combo = QComboBox()

        for handler in self.registry.all():
            self.type_combo.addItem(
                handler.display_name,
                handler.type_id,
            )

        self.type_combo.currentIndexChanged.connect(
            self._type_changed
        )

        form.addRow(
            "Notification Type:",
            self.type_combo,
        )

        # Title
        self.title_edit = QLineEdit()

        self.title_edit.setPlaceholderText(
            "Notification title"
        )

        form.addRow(
            "Title:",
            self.title_edit,
        )

        # Message
        self.message_edit = QTextEdit()

        self.message_edit.setPlaceholderText(
            "Notification message"
        )

        self.message_edit.setMaximumHeight(
            100
        )

        form.addRow(
            "Message:",
            self.message_edit,
        )

        main_layout.addLayout(form)

        # -----------------------------------------------------
        # Type-specific editor
        # -----------------------------------------------------

        type_label = QLabel(
            "Notification Settings"
        )

        type_label.setStyleSheet(
            "font-weight: bold; "
            "font-size: 14px;"
        )

        main_layout.addWidget(type_label)

        self.type_editor_container = QWidget()

        self.type_editor_layout = QVBoxLayout(
            self.type_editor_container
        )

        self.type_editor_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        main_layout.addWidget(
            self.type_editor_container
        )

        # -----------------------------------------------------
        # Sound
        # -----------------------------------------------------

        sound_label = QLabel("Sound")

        sound_label.setStyleSheet(
            "font-weight: bold; "
            "font-size: 14px;"
        )

        main_layout.addWidget(sound_label)

        sound_layout = QFormLayout()

        self.sound_enabled = QCheckBox(
            "Play sound"
        )

        self.sound_enabled.setChecked(
            True
        )

        sound_layout.addRow(
            self.sound_enabled
        )

        sound_file_layout = QHBoxLayout()

        self.sound_file_edit = QLineEdit()

        self.sound_file_edit.setPlaceholderText(
            "Optional .wav sound file"
        )

        self.browse_sound_button = QPushButton(
            "Browse..."
        )

        self.browse_sound_button.clicked.connect(
            self.browse_sound
        )

        sound_file_layout.addWidget(
            self.sound_file_edit
        )

        sound_file_layout.addWidget(
            self.browse_sound_button
        )

        sound_layout.addRow(
            "Sound file:",
            sound_file_layout,
        )

        main_layout.addLayout(
            sound_layout
        )

        # -----------------------------------------------------
        # Buttons
        # -----------------------------------------------------

        button_layout = QHBoxLayout()

        button_layout.addStretch()

        self.cancel_button = QPushButton(
            "Cancel"
        )

        self.cancel_button.clicked.connect(
            self.reject
        )

        self.save_button = QPushButton(
            "Save"
        )

        self.save_button.clicked.connect(
            self.save
        )

        button_layout.addWidget(
            self.cancel_button
        )

        button_layout.addWidget(
            self.save_button
        )

        main_layout.addLayout(
            button_layout
        )

    # =========================================================
    # TYPE
    # =========================================================

    def _type_changed(self, index):

        type_id = self.type_combo.itemData(
            index
        )

        if not type_id:
            return

        handler = self.registry.get(
            type_id
        )

        if handler is None:
            return

        if (
            self.current_handler is handler
            and self.type_editor is not None
        ):
            return

        self.current_handler = handler

        # Remove previous editor.
        if self.type_editor is not None:

            self.type_editor_layout.removeWidget(
                self.type_editor
            )

            self.type_editor.deleteLater()

            self.type_editor = None

        # Create editor supplied by the extension.
        self.type_editor = (
            handler.create_editor(
                parent=self.type_editor_container
            )
        )

        self.type_editor_layout.addWidget(
            self.type_editor
        )

        # If editing an existing notification,
        # load its type-specific settings.
        if (
            self.notification is not None
            and self.notification.type == type_id
        ):
            self._load_type_settings()

    # =========================================================
    # LOAD
    # =========================================================

    def _load_notification(self):

        if self.notification is None:

            index = self.type_combo.findData(
                self.initial_type
            )

            if index < 0 and self.type_combo.count() > 0:
                index = 0

            if index >= 0:
                self.type_combo.setCurrentIndex(index)
                self._type_changed(index)

            return

        # Common fields
        self.title_edit.setText(
            self.notification.title
        )

        self.message_edit.setPlainText(
            self.notification.message
        )

        self.sound_enabled.setChecked(
            self.notification.sound_enabled
        )

        self.sound_file_edit.setText(
            self.notification.sound_file
        )

        # Select notification type.
        index = self.type_combo.findData(
            self.notification.type
        )

        if index >= 0:
            self.type_combo.setCurrentIndex(
                index
            )
            self._type_changed(index)

        else:

            # Unknown type.
            QMessageBox.warning(
                self,
                "Unknown Notification Type",
                "The notification type "
                f"'{self.notification.type}' "
                "is not installed.",
            )

            if self.type_combo.count() > 0:
                self._type_changed(
                    self.type_combo.currentIndex()
                )

    def _load_type_settings(self):

        if (
            self.current_handler is None
            or self.type_editor is None
            or self.notification is None
        ):
            return

        settings = dict(
            self.notification.settings
        )

        editor = self.type_editor

        # The extension editor can implement
        # load_settings(settings).
        if hasattr(
            editor,
            "load_settings",
        ):

            try:
                editor.load_settings(
                    settings
                )

            except Exception as exc:

                QMessageBox.warning(
                    self,
                    "Settings Error",
                    "Could not load notification "
                    f"settings:\n{exc}",
                )

    # =========================================================
    # SOUND
    # =========================================================

    def browse_sound(self):

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Sound File",
            "",
            "Wave Files (*.wav);;All Files (*)",
        )

        if filename:
            self.sound_file_edit.setText(
                filename
            )

    # =========================================================
    # SAVE
    # =========================================================

    def save(self):

        type_id = self.type_combo.currentData()

        if not type_id:
            QMessageBox.warning(
                self,
                "Invalid Notification",
                "Please select a notification type.",
            )
            return

        handler = self.registry.get(
            type_id
        )

        if handler is None:
            QMessageBox.warning(
                self,
                "Invalid Notification",
                "The selected notification type "
                "is not available.",
            )
            return

        title = self.title_edit.text().strip()

        if not title:
            QMessageBox.warning(
                self,
                "Invalid Notification",
                "Please enter a notification title.",
            )
            self.title_edit.setFocus()
            return

        message = (
            self.message_edit
            .toPlainText()
            .strip()
        )

        if not message:
            QMessageBox.warning(
                self,
                "Invalid Notification",
                "Please enter a notification message.",
            )
            self.message_edit.setFocus()
            return

        # -----------------------------------------------------
        # Type-specific settings
        # -----------------------------------------------------

        settings = {}

        if self.type_editor is not None:

            if hasattr(
                self.type_editor,
                "get_settings",
            ):

                try:
                    settings = (
                        self.type_editor
                        .get_settings()
                    )

                except Exception as exc:

                    QMessageBox.warning(
                        self,
                        "Invalid Settings",
                        f"Could not read settings:\n{exc}",
                    )

                    return

        # -----------------------------------------------------
        # Create notification
        # -----------------------------------------------------

        if self.notification is None:

            notification = Notification(
                type=type_id,
                title=title,
                message=message,
                enabled=True,
                sound_enabled=(
                    self.sound_enabled.isChecked()
                ),
                sound_file=(
                    self.sound_file_edit
                    .text()
                    .strip()
                ),
                settings=settings,
            )

        else:

            notification = Notification(
                id=self.notification.id,
                type=type_id,
                title=title,
                message=message,
                enabled=self.notification.enabled,
                sound_enabled=(
                    self.sound_enabled.isChecked()
                ),
                sound_file=(
                    self.sound_file_edit
                    .text()
                    .strip()
                ),
                settings=settings,
            )

        # -----------------------------------------------------
        # Validate through extension
        # -----------------------------------------------------

        try:

            result = handler.validate(
                notification
            )

        except Exception as exc:

            QMessageBox.warning(
                self,
                "Validation Error",
                f"Could not validate notification:\n{exc}",
            )

            return

        # Support both:
        #
        #     (True, "")
        #
        # and:
        #
        #     True
        #

        if isinstance(result, tuple):

            valid = result[0]

            error_message = (
                result[1]
                if len(result) > 1
                else ""
            )

        else:

            valid = bool(result)
            error_message = ""

        if not valid:

            QMessageBox.warning(
                self,
                "Invalid Notification",
                error_message
                or "The notification settings are invalid.",
            )

            return

        self._result = notification

        self.accept()

    # =========================================================
    # RESULT
    # =========================================================

    def get_notification(self):
        """
        Return the notification created by the dialog.

        Returns None if the dialog was cancelled.
        """

        return getattr(
            self,
            "_result",
            None,
        )