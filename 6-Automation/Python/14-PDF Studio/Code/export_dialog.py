import os
import fitz

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QSpinBox,
    QProgressBar,
    QMessageBox,
)


class ExportWorker(QObject):
    progress = Signal(int)
    finished = Signal(int)
    error = Signal(str)

    def __init__(
        self,
        file_path,
        pages,
        output_folder,
        image_format,
        dpi,
    ):
        super().__init__()

        self.file_path = file_path
        self.pages = pages
        self.output_folder = output_folder
        self.image_format = image_format
        self.dpi = dpi

        self.cancel_requested = False

    def cancel(self):
        self.cancel_requested = True

    @Slot()
    def run(self):
        document = None

        try:
            document = fitz.open(self.file_path)

            scale = self.dpi / 72
            matrix = fitz.Matrix(scale, scale)

            base_name = os.path.splitext(
                os.path.basename(self.file_path)
            )[0]

            total = len(self.pages)

            for index, page_number in enumerate(
                self.pages,
                start=1,
            ):
                if self.cancel_requested:
                    break

                page = document.load_page(
                    page_number - 1
                )

                pixmap = page.get_pixmap(
                    matrix=matrix,
                    alpha=False,
                )

                output_file = os.path.join(
                    self.output_folder,
                    f"{base_name}_page_{page_number}."
                    f"{self.image_format}",
                )

                if self.image_format == "png":
                    pixmap.save(output_file)
                else:
                    pixmap.save(
                        output_file,
                        output="jpg",
                    )

                percent = round(
                    index / total * 100
                )

                self.progress.emit(percent)

            if self.cancel_requested:
                self.finished.emit(-1)
            else:
                self.finished.emit(total)

        except Exception as e:
            self.error.emit(str(e))

        finally:
            if document:
                document.close()


class ExportDialog(QDialog):
    def __init__(self, file_path, current_page, parent=None):
        super().__init__(parent)

        self.file_path = file_path
        self.current_page = current_page

        self.thread = None
        self.worker = None

        self.setWindowTitle("Export PDF to Images")
        self.resize(500, 350)

        self.create_ui()

    def create_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Pages:"))

        self.range_box = QComboBox()
        self.range_box.addItems([
            "All Pages",
            "Current Page",
            "Page Range",
            "Selected Pages",
        ])

        self.range_box.currentTextChanged.connect(
            self.range_mode_changed
        )

        layout.addWidget(self.range_box)

        layout.addWidget(QLabel("Pages to export:"))

        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText(
            "Example: 1-20 or 1,3,7,10"
        )
        self.pages_edit.setEnabled(False)

        layout.addWidget(self.pages_edit)

        layout.addWidget(QLabel("Image Format:"))

        self.format_box = QComboBox()
        self.format_box.addItems([
            "PNG",
            "JPG",
        ])

        layout.addWidget(self.format_box)

        layout.addWidget(QLabel("Resolution (DPI):"))

        self.dpi_box = QSpinBox()
        self.dpi_box.setRange(72, 600)
        self.dpi_box.setValue(150)
        self.dpi_box.setSingleStep(25)

        layout.addWidget(self.dpi_box)

        layout.addWidget(QLabel("Output Folder:"))

        folder_layout = QHBoxLayout()

        self.folder_edit = QLineEdit()

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(
            self.browse_folder
        )

        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(browse_button)

        layout.addLayout(folder_layout)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)

        layout.addWidget(self.progress)

        buttons = QHBoxLayout()

        buttons.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(
            self.cancel_or_close
        )

        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(
            self.export
        )

        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.export_button)

        layout.addLayout(buttons)

    def range_mode_changed(self, value):
        enabled = value in (
            "Page Range",
            "Selected Pages",
        )

        self.pages_edit.setEnabled(enabled)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
        )

        if folder:
            self.folder_edit.setText(folder)

    def parse_pages(self, text, total_pages):
        pages = set()

        for part in text.split(","):
            part = part.strip()

            if not part:
                continue

            if "-" in part:
                values = part.split("-", 1)

                start = int(values[0].strip())
                end = int(values[1].strip())

                if start > end:
                    start, end = end, start

                for page in range(
                    start,
                    end + 1,
                ):
                    if 1 <= page <= total_pages:
                        pages.add(page)

            else:
                page = int(part)

                if 1 <= page <= total_pages:
                    pages.add(page)

        return sorted(pages)

    def export(self):
        if not self.folder_edit.text().strip():
            QMessageBox.warning(
                self,
                "Output Folder",
                "Please select an output folder.",
            )
            return

        output_folder = self.folder_edit.text().strip()

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
            document.close()

            mode = self.range_box.currentText()

            if mode == "All Pages":
                pages = list(
                    range(1, total_pages + 1)
                )

            elif mode == "Current Page":
                pages = [
                    self.current_page + 1
                ]

            else:
                pages = self.parse_pages(
                    self.pages_edit.text(),
                    total_pages,
                )

                if not pages:
                    QMessageBox.warning(
                        self,
                        "Pages",
                        "Please enter valid page numbers.",
                    )
                    return

        except Exception as e:
            QMessageBox.critical(
                self,
                "PDF Error",
                f"Could not read PDF:\n\n{e}",
            )
            return

        self.progress.setVisible(True)
        self.progress.setValue(0)

        self.export_button.setEnabled(False)
        self.cancel_button.setText("Cancel")

        image_format = (
            self.format_box.currentText().lower()
        )

        dpi = self.dpi_box.value()

        self.thread = QThread()
        self.worker = ExportWorker(
            self.file_path,
            pages,
            output_folder,
            image_format,
            dpi,
        )

        self.worker.moveToThread(self.thread)

        self.thread.started.connect(
            self.worker.run
        )

        self.worker.progress.connect(
            self.progress.setValue
        )

        self.worker.finished.connect(
            self.export_finished
        )

        self.worker.error.connect(
            self.export_error
        )

        self.worker.finished.connect(
            self.thread.quit
        )

        self.worker.error.connect(
            self.thread.quit
        )

        self.thread.finished.connect(
            self.worker.deleteLater
        )

        self.thread.finished.connect(
            self.thread.deleteLater
        )

        self.thread.finished.connect(
            self.thread_finished
        )

        self.thread.start()

    def cancel_or_close(self):
        if self.worker:
            self.worker.cancel()

            self.cancel_button.setEnabled(False)
            self.cancel_button.setText(
                "Stopping..."
            )
        else:
            self.reject()

    def export_finished(self, count):
        if count == -1:
            return

        QMessageBox.information(
            self,
            "Export Complete",
            f"Successfully exported {count} page(s).",
        )

    def export_error(self, message):
        QMessageBox.critical(
            self,
            "Export Error",
            f"Could not export PDF:\n\n{message}",
        )

    def thread_finished(self):
        self.worker = None
        self.thread = None

        self.export_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Close")

    def closeEvent(self, event):
        if self.worker:
            self.worker.cancel()

            if self.thread:
                self.thread.quit()
                self.thread.wait()

        event.accept()