import os
import fitz

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QProgressBar,
    QMessageBox,
)


class SplitDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)

        self.file_path = file_path

        self.setWindowTitle("Split PDF")
        self.resize(500, 300)

        self.create_ui()

    def create_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Split Mode:"))

        self.mode_box = QComboBox()
        self.mode_box.addItems([
            "Every Page",
            "Page Range",
            "Custom Ranges",
        ])

        self.mode_box.currentTextChanged.connect(
            self.mode_changed
        )

        layout.addWidget(self.mode_box)

        layout.addWidget(QLabel("Pages / Ranges:"))

        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText(
            "Example: 1-5 or 1-3,4-7,8-12"
        )
        self.pages_edit.setEnabled(False)

        layout.addWidget(self.pages_edit)

        layout.addWidget(QLabel("Output Folder:"))

        folder_layout = QHBoxLayout()

        self.folder_edit = QLineEdit()

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_folder)

        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(browse_button)

        layout.addLayout(folder_layout)

        self.progress = QProgressBar()
        self.progress.setVisible(False)

        layout.addWidget(self.progress)

        buttons = QHBoxLayout()

        buttons.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        split_button = QPushButton("Split")
        split_button.clicked.connect(self.split_pdf)

        buttons.addWidget(cancel_button)
        buttons.addWidget(split_button)

        layout.addLayout(buttons)

    def mode_changed(self, value):
        self.pages_edit.setEnabled(
            value in (
                "Page Range",
                "Custom Ranges",
            )
        )

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
        )

        if folder:
            self.folder_edit.setText(folder)

    def parse_range(self, text, total_pages):
        pages = []

        parts = text.split(",")

        for part in parts:
            part = part.strip()

            if not part:
                continue

            if "-" in part:
                values = part.split("-", 1)

                start = int(values[0].strip())
                end = int(values[1].strip())

                if start > end:
                    start, end = end, start

                start = max(start, 1)
                end = min(end, total_pages)

                if start <= end:
                    pages.append(
                        (start, end)
                    )

            else:
                page = int(part)

                if 1 <= page <= total_pages:
                    pages.append(
                        (page, page)
                    )

        return pages

    def split_pdf(self):
        output_folder = self.folder_edit.text().strip()

        if not output_folder:
            QMessageBox.warning(
                self,
                "Output Folder",
                "Please select an output folder.",
            )
            return

        if not os.path.isdir(output_folder):
            QMessageBox.warning(
                self,
                "Output Folder",
                "The selected output folder does not exist.",
            )
            return

        try:
            document = fitz.open(self.file_path)

            total_pages = len(document)

            mode = self.mode_box.currentText()

            if mode == "Every Page":

                ranges = [
                    (page, page)
                    for page in range(1, total_pages + 1)
                ]

            else:

                ranges = self.parse_range(
                    self.pages_edit.text(),
                    total_pages,
                )

                if not ranges:
                    QMessageBox.warning(
                        self,
                        "Pages",
                        "Please enter valid pages or ranges.",
                    )
                    document.close()
                    return

            base_name = os.path.splitext(
                os.path.basename(self.file_path)
            )[0]

            self.progress.setVisible(True)
            self.progress.setMaximum(len(ranges))
            self.progress.setValue(0)

            for index, (start, end) in enumerate(
                ranges,
                start=1
            ):
                output_file = os.path.join(
                    output_folder,
                    f"{base_name}_part_{index}.pdf",
                )

                new_document = fitz.open()

                new_document.insert_pdf(
                    document,
                    from_page=start - 1,
                    to_page=end - 1,
                )

                new_document.save(output_file)
                new_document.close()

                self.progress.setValue(index)

            document.close()

            QMessageBox.information(
                self,
                "Split Complete",
                f"Successfully created {len(ranges)} PDF file(s).",
            )

            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Split Error",
                f"Could not split PDF:\n\n{e}",
            )