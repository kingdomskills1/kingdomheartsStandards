from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QLabel,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget
)


class DateTimeEditor(QWidget):

    def __init__(
        self,
        parent=None
    ):

        super().__init__(
            parent
        )

        self.build_ui()

    # --------------------------------------------------

    def build_ui(self):

        layout = QVBoxLayout(
            self
        )

        form = QFormLayout()

        # DATE
        self.date_edit = QDateEdit()

        self.date_edit.setCalendarPopup(
            True
        )
        self.date_edit.setDisplayFormat(
            "yyyy-MM-dd"
        )

        self.date_edit.setDate(
            QDate.currentDate()
        )

        self.date_label = QLabel("Date:")
        form.addRow(
            self.date_label,
            self.date_edit
        )

        self.annual_date_edit = QDateEdit()
        self.annual_date_edit.setCalendarPopup(True)
        self.annual_date_edit.setDateRange(
            QDate(2000, 1, 1),
            QDate(2000, 12, 31),
        )
        self.annual_date_edit.setDisplayFormat("MMMM d")
        self.annual_date_edit.setDate(QDate(2000, 1, 1))
        self.annual_date_label = QLabel("Month and day:")
        form.addRow(
            self.annual_date_label,
            self.annual_date_edit,
        )

        # TIME
        self.time_edit = QTimeEdit()

        self.time_edit.setDisplayFormat(
            "HH:mm:ss"
        )

        self.time_edit.setTime(
            QTime.currentTime()
        )

        form.addRow(
            "Time:",
            self.time_edit
        )

        # RECURRENCE
        self.recurrence_combo = QComboBox()
        self.recurrence_combo.addItem("Once", "once")
        self.recurrence_combo.addItem(
            "Every interval",
            "interval",
        )
        self.recurrence_combo.addItem(
            "Weekly",
            "weekly",
        )
        self.recurrence_combo.addItem(
            "Annually",
            "yearly",
        )
        self.recurrence_combo.currentIndexChanged.connect(
            self._update_recurrence_fields
        )
        form.addRow(
            "Repeat:",
            self.recurrence_combo
        )

        # INTERVAL
        self.repeat_seconds = QSpinBox()

        self.repeat_seconds.setRange(
            1,
            31536000
        )

        self.repeat_seconds.setSuffix(
            " seconds"
        )

        self.interval_label = QLabel(
            "Repeat every:"
        )
        form.addRow(
            self.interval_label,
            self.repeat_seconds
        )

        # WEEKDAY
        self.weekday_combo = QComboBox()
        self.weekday_combo.addItem("Monday", 0)
        self.weekday_combo.addItem("Tuesday", 1)
        self.weekday_combo.addItem("Wednesday", 2)
        self.weekday_combo.addItem("Thursday", 3)
        self.weekday_combo.addItem("Friday", 4)
        self.weekday_combo.addItem("Saturday", 5)
        self.weekday_combo.addItem("Sunday", 6)
        self.weekday_label = QLabel("Day of week:")
        form.addRow(
            self.weekday_label,
            self.weekday_combo
        )

        layout.addLayout(
            form
        )
        self._update_recurrence_fields()

    # --------------------------------------------------

    def _update_recurrence_fields(self, *_):
        recurrence = self.recurrence_combo.currentData()
        self.date_label.setVisible(
            recurrence in ("once", "interval")
        )
        self.date_edit.setVisible(
            recurrence in ("once", "interval")
        )
        self.annual_date_label.setVisible(
            recurrence == "yearly"
        )
        self.annual_date_edit.setVisible(
            recurrence == "yearly"
        )
        self.interval_label.setVisible(recurrence == "interval")
        self.repeat_seconds.setVisible(recurrence == "interval")
        self.weekday_label.setVisible(recurrence == "weekly")
        self.weekday_combo.setVisible(recurrence == "weekly")

    # --------------------------------------------------

    def load_settings(
        self,
        settings: dict
    ):

        date_text = settings.get(
            "date"
        )

        time_text = settings.get(
            "time"
        )

        if date_text:

            date = QDate.fromString(
                date_text,
                "yyyy-MM-dd"
            )

            if date.isValid():

                self.date_edit.setDate(
                    date
                )

        recurrence = settings.get("recurrence")
        if recurrence is None:
            try:
                recurrence = (
                    "interval"
                    if int(settings.get("repeat_seconds", 0)) > 0
                    else "once"
                )
            except (TypeError, ValueError):
                recurrence = "once"

        recurrence_index = self.recurrence_combo.findData(
            recurrence
        )
        if recurrence_index >= 0:
            self.recurrence_combo.setCurrentIndex(
                recurrence_index
            )

        if time_text:

            time = QTime.fromString(
                time_text,
                "HH:mm:ss"
            )

            if time.isValid():

                self.time_edit.setTime(
                    time
                )

        try:
            repeat_seconds = int(
                settings.get("repeat_seconds", 60)
            )
        except (TypeError, ValueError):
            repeat_seconds = 60
        self.repeat_seconds.setValue(
            max(1, min(repeat_seconds, 31536000))
        )

        try:
            weekday = int(settings.get("weekday", 0))
        except (TypeError, ValueError):
            weekday = 0
        weekday_index = self.weekday_combo.findData(weekday)
        if weekday_index >= 0:
            self.weekday_combo.setCurrentIndex(weekday_index)

        if recurrence == "yearly":
            try:
                annual_date = QDate(
                    2000,
                    int(settings.get("month", 1)),
                    int(settings.get("day", 1)),
                )
            except (TypeError, ValueError):
                annual_date = QDate(2000, 1, 1)
            if annual_date.isValid():
                self.annual_date_edit.setDate(annual_date)
            self._update_recurrence_fields()

    # --------------------------------------------------

    def get_settings(self):

        date = self.date_edit.date()
        annual_date = self.annual_date_edit.date()
        time = self.time_edit.time()

        recurrence = self.recurrence_combo.currentData()
        settings = {

            "date": date.toString(
                "yyyy-MM-dd"
            ),

            "time": time.toString(
                "HH:mm:ss"
            ),

            "recurrence": recurrence,
        }

        if recurrence == "interval":
            settings["repeat_seconds"] = (
                self.repeat_seconds.value()
            )
        elif recurrence == "weekly":
            settings["weekday"] = (
                self.weekday_combo.currentData()
            )
        elif recurrence == "yearly":
            settings["month"] = annual_date.month()
            settings["day"] = annual_date.day()

        return settings