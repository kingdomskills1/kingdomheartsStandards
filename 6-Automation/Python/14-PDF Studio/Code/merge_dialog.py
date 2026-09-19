import os
import fitz

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QListWidget,
    QPushButton,
    QFileDialog,
    QMessageBox,
)


class MergeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Merge")
        self.resize(650, 500)

        self.create_ui()

    def create_ui(self):
        layout = QVBoxLayout(self)

        # Merge mode
        layout.addWidget(QLabel("Merge Type:"))

        self.mode_box = QComboBox()
        self.mode_box.addItems([
            "Merge PDFs",
            "Merge Images",
        ])

        self.mode_box.currentTextChanged.connect(
            self.mode_changed
        )

        layout.addWidget(self.mode_box)

        # File list
        self.file_list = QListWidget()
        layout.addWidget(self.file_list)

        # File buttons
        buttons = QHBoxLayout()

        self.add_button = QPushButton("Add Files")
        self.add_button.clicked.connect(self.add_files)

        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(self.remove_file)

        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.clear_files)

        up_button = QPushButton("Move Up")
        up_button.clicked.connect(self.move_up)

        down_button = QPushButton("Move Down")
        down_button.clicked.connect(self.move_down)

        buttons.addWidget(self.add_button)
        buttons.addWidget(remove_button)
        buttons.addWidget(clear_button)
        buttons.addWidget(up_button)
        buttons.addWidget(down_button)

        layout.addLayout(buttons)

        # Bottom buttons
        bottom = QHBoxLayout()

        bottom.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        self.merge_button = QPushButton("Merge")
        self.merge_button.clicked.connect(self.merge)

        bottom.addWidget(cancel_button)
        bottom.addWidget(self.merge_button)

        layout.addLayout(bottom)

    def mode_changed(self, value):
        self.file_list.clear()

        if value == "Merge PDFs":
            self.add_button.setText("Add PDFs")
        else:
            self.add_button.setText("Add Images")

    def add_files(self):
        mode = self.mode_box.currentText()

        if mode == "Merge PDFs":
            files, _ = QFileDialog.getOpenFileNames(
                self,
                "Select PDF Files",
                "",
                "PDF Files (*.pdf)",
            )
        else:
            files, _ = QFileDialog.getOpenFileNames(
                self,
                "Select Image Files",
                "",
                "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
            )

        for file_path in files:
            self.file_list.addItem(file_path)

    def remove_file(self):
        row = self.file_list.currentRow()

        if row >= 0:
            self.file_list.takeItem(row)

    def clear_files(self):
        self.file_list.clear()

    def move_up(self):
        row = self.file_list.currentRow()

        if row > 0:
            item = self.file_list.takeItem(row)

            self.file_list.insertItem(
                row - 1,
                item,
            )

            self.file_list.setCurrentRow(row - 1)

    def move_down(self):
        row = self.file_list.currentRow()

        if row >= 0 and row < self.file_list.count() - 1:
            item = self.file_list.takeItem(row)

            self.file_list.insertItem(
                row + 1,
                item,
            )

            self.file_list.setCurrentRow(row + 1)

    def merge(self):
        if self.file_list.count() == 0:
            QMessageBox.warning(
                self,
                "Merge",
                "Please add at least one file.",
            )
            return

        output_file, _ = QFileDialog.getSaveFileName(
            self,
            "Save Merged PDF",
            "",
            "PDF Files (*.pdf)",
        )

        if not output_file:
            return

        if not output_file.lower().endswith(".pdf"):
            output_file += ".pdf"

        try:
            mode = self.mode_box.currentText()

            if mode == "Merge PDFs":
                self.merge_pdfs(output_file)
            else:
                self.merge_images(output_file)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Merge Error",
                f"Could not merge files:\n\n{e}",
            )

    def merge_pdfs(self, output_file):
        merged_document = fitz.open()

        try:
            for index in range(self.file_list.count()):
                file_path = self.file_list.item(index).text()

                document = fitz.open(file_path)

                merged_document.insert_pdf(document)

                document.close()

            merged_document.save(output_file)

        finally:
            merged_document.close()

        QMessageBox.information(
            self,
            "Merge Complete",
            f"Successfully merged "
            f"{self.file_list.count()} PDF file(s).",
        )

        self.accept()

    def merge_images(self, output_file):
        merged_document = fitz.open()

        try:
            for index in range(self.file_list.count()):
                image_path = self.file_list.item(index).text()

                image = fitz.Pixmap(image_path)

                page_width = image.width
                page_height = image.height

                page = merged_document.new_page(
                    width=page_width,
                    height=page_height,
                )

                page.insert_image(
                    page.rect,
                    filename=image_path,
                )

            merged_document.save(output_file)

        finally:
            merged_document.close()

        QMessageBox.information(
            self,
            "Merge Complete",
            f"Successfully merged "
            f"{self.file_list.count()} image(s) into a PDF.",
        )

        self.accept()