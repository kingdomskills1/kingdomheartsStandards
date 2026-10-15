from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class BatteryEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Plug in laptop", "plug_in")
        self.mode_combo.addItem("Unplug laptop", "unplug")
        self.mode_combo.currentIndexChanged.connect(
            self._mode_changed
        )
        form.addRow("Remind me to:", self.mode_combo)

        self.threshold = QSpinBox()
        self.threshold.setRange(1, 100)
        self.threshold.setSuffix("%")
        self.threshold.setValue(35)
        form.addRow("Battery level:", self.threshold)

        self.repeat_seconds = QSpinBox()
        self.repeat_seconds.setRange(5, 31536000)
        self.repeat_seconds.setValue(60)
        self.repeat_seconds.setSuffix(" seconds")
        form.addRow("Repeat reminder every:", self.repeat_seconds)

        layout.addLayout(form)

    def _mode_changed(self, index):
        mode = self.mode_combo.itemData(index)
        self.threshold.setValue(95 if mode == "unplug" else 35)

    def load_settings(self, settings: dict):
        mode_index = self.mode_combo.findData(
            settings.get("mode", "plug_in")
        )
        if mode_index >= 0:
            self.mode_combo.setCurrentIndex(mode_index)

        try:
            threshold = int(
                settings.get(
                    "threshold",
                    95 if self.mode_combo.currentData() == "unplug" else 35,
                )
            )
        except (TypeError, ValueError):
            threshold = 95 if self.mode_combo.currentData() == "unplug" else 35

        self.threshold.setValue(threshold)

        try:
            repeat_seconds = int(settings.get("repeat_seconds", 60))
        except (TypeError, ValueError):
            repeat_seconds = 60

        self.repeat_seconds.setValue(repeat_seconds)

    def get_settings(self):
        return {
            "mode": self.mode_combo.currentData(),
            "threshold": self.threshold.value(),
            "repeat_seconds": self.repeat_seconds.value(),
        }