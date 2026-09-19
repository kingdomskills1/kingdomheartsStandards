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
    QProgressBar,
    QMessageBox,
)


class CompressWorker(QObject):
    progress = Signal(int)
    finished = Signal(str, int, int)
    error = Signal(str)

    def __init__(
        self,
        input_file,
        output_file,
        dpi,
    ):
        super().__init__()

        self.input_file = input_file
        self.output_file = output_file
        self.dpi = dpi

        self.cancel_requested = False

    def cancel(self):
        self.cancel_requested = True

    @Slot()
    def run(self):
        source = None
        output = None

        try:
            source = fitz.open(self.input_file)
            output = fitz.open()

            total = len(source)

            for index in range(total):

                if self.cancel_requested:
                    source.close()
                    output.close()

                    if os.path.exists(self.output_file):
                        os.remove(self.output_file)

                    return

                source_page = source.load_page(index)

                new_page = output.new_page(
                    width=source_page.rect.width,
                    height=source_page.rect.height,
                )

                scale = self.dpi / 72

                matrix = fitz.Matrix(
                    scale,
                    scale,
                )

                pixmap = source_page.get_pixmap(
                    matrix=matrix,
                    alpha=False,
                )

                new_page.insert_image(
                    new_page.rect,
                    pixmap=pixmap,
                )

                percent = round(
                    (index + 1) / total * 100
                )

                self.progress.emit(percent)

            source.close()

            output.save(
                self.output_file,
                garbage=4,
                deflate=True,
                clean=True,
            )

            output.close()

            self.finished.emit(
                self.output_file,
                os.path.getsize(self.input_file),
                os.path.getsize(self.output_file),
            )

        except Exception as e:
            if source:
                source.close()

            if output:
                output.close()

            self.error.emit(str(e))


class CompressDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)

        self.file_path = file_path

        self.thread = None
        self.worker = None

        self.setWindowTitle("Compress PDF")
        self.resize(500, 350)

        self.create_ui()

    def create_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Compression Quality:"))

        self.quality_box = QComboBox()

        self.quality_box.addItems([
            "Low Size - 72 DPI",
            "Medium - 120 DPI",
            "High Quality - 150 DPI",
            "Very High Quality - 200 DPI",
            "Custom",
        ])

        self.quality_box.currentTextChanged.connect(
            self.quality_changed
        )

        layout.addWidget(self.quality_box)

        layout.addWidget(QLabel("Custom DPI:"))

        self.dpi_edit = QLineEdit()
        self.dpi_edit.setText("150")
        self.dpi_edit.setEnabled(False)

        layout.addWidget(self.dpi_edit)

        layout.addWidget(
            QLabel(
                "Lower DPI = smaller PDF\n"
                "Higher DPI = better image quality"
            )
        )

        layout.addWidget(QLabel("Output File:"))

        output_layout = QHBoxLayout()

        self.output_edit = QLineEdit()

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(
            self.browse_output
        )

        output_layout.addWidget(self.output_edit)
        output_layout.addWidget(browse_button)

        layout.addLayout(output_layout)

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

        self.compress_button = QPushButton(
            "Compress"
        )
        self.compress_button.clicked.connect(
            self.compress
        )

        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.compress_button)

        layout.addLayout(buttons)

        self.set_default_output()

    def set_default_output(self):
        folder = os.path.dirname(self.file_path)

        name = os.path.splitext(
            os.path.basename(self.file_path)
        )[0]

        output = os.path.join(
            folder,
            f"{name}_compressed.pdf",
        )

        self.output_edit.setText(output)

    def quality_changed(self, value):
        custom = value == "Custom"

        self.dpi_edit.setEnabled(custom)

    def get_dpi(self):
        value = self.quality_box.currentText()

        if value.startswith("Low"):
            return 72

        if value.startswith("Medium"):
            return 120

        if value.startswith("High"):
            return 150

        if value.startswith("Very High"):
            return 200

        try:
            dpi = int(self.dpi_edit.text())

            if dpi < 36:
                dpi = 36

            if dpi > 600:
                dpi = 600

            return dpi

        except ValueError:
            return None

    def browse_output(self):
        output_file, _ = QFileDialog.getSaveFileName(
            self,
            "Save Compressed PDF",
            self.output_edit.text(),
            "PDF Files (*.pdf)",
        )

        if output_file:
            if not output_file.lower().endswith(
                ".pdf"
            ):
                output_file += ".pdf"

            self.output_edit.setText(
                output_file
            )

    def compress(self):
        output_file = self.output_edit.text().strip()

        if not output_file:
            QMessageBox.warning(
                self,
                "Output File",
                "Please select an output file.",
            )
            return

        if os.path.abspath(output_file) == os.path.abspath(
            self.file_path
        ):
            QMessageBox.warning(
                self,
                "Output File",
                "The output file must be different "
                "from the original PDF.",
            )
            return

        dpi = self.get_dpi()

        if dpi is None:
            QMessageBox.warning(
                self,
                "DPI",
                "Please enter a valid DPI.",
            )
            return

        self.progress.setVisible(True)
        self.progress.setValue(0)

        self.compress_button.setEnabled(False)
        self.cancel_button.setText("Cancel")

        self.thread = QThread()

        self.worker = CompressWorker(
            self.file_path,
            output_file,
            dpi,
        )

        self.worker.moveToThread(
            self.thread
        )

        self.thread.started.connect(
            self.worker.run
        )

        self.worker.progress.connect(
            self.progress.setValue
        )

        self.worker.finished.connect(
            self.compression_finished
        )

        self.worker.error.connect(
            self.compression_error
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

            self.cancel_button.setEnabled(
                False
            )

            self.cancel_button.setText(
                "Stopping..."
            )

        else:
            self.reject()

    def compression_finished(
        self,
        output_file,
        original_size,
        compressed_size,
    ):
        original_mb = original_size / (
            1024 * 1024
        )

        compressed_mb = compressed_size / (
            1024 * 1024
        )

        if original_size > 0:
            reduction = (
                1
                - compressed_size / original_size
            ) * 100
        else:
            reduction = 0

        QMessageBox.information(
            self,
            "Compression Complete",
            f"Original size: "
            f"{original_mb:.2f} MB\n"
            f"Compressed size: "
            f"{compressed_mb:.2f} MB\n"
            f"Size reduction: "
            f"{reduction:.1f}%",
        )

    def compression_error(self, message):
        QMessageBox.critical(
            self,
            "Compression Error",
            f"Could not compress PDF:\n\n{message}",
        )

    def thread_finished(self):
        self.worker = None
        self.thread = None

        self.compress_button.setEnabled(
            True
        )

        self.cancel_button.setEnabled(
            True
        )

        self.cancel_button.setText(
            "Close"
        )

    def closeEvent(self, event):
        if self.worker:
            self.worker.cancel()

            if self.thread:
                self.thread.quit()
                self.thread.wait()

        event.accept()