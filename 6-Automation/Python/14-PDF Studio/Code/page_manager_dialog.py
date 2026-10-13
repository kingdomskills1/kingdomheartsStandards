import os

import fitz

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QFileDialog,
    QMessageBox,
)


class PageManagerDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)

        self.file_path = file_path
        self.output_file = None
        self.document = fitz.open(file_path)

        self.setWindowTitle("Update PDF Pages")
        self.resize(520, 450)

        self.create_ui()
        self.refresh_page_list()

    def create_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Select a page to insert a blank page after it, delete it, "
            "move it, or rotate it."
        ))

        self.page_list = QListWidget()
        self.page_list.currentRowChanged.connect(self.update_buttons)
        layout.addWidget(self.page_list)

        page_buttons = QHBoxLayout()

        add_button = QPushButton("Add Blank Page")
        add_button.clicked.connect(self.add_blank_page)

        self.delete_button = QPushButton("Delete Page")
        self.delete_button.clicked.connect(self.delete_page)

        self.move_up_button = QPushButton("Move Up")
        self.move_up_button.clicked.connect(self.move_page_up)

        self.move_down_button = QPushButton("Move Down")
        self.move_down_button.clicked.connect(self.move_page_down)

        self.rotate_button = QPushButton("Rotate 90°")
        self.rotate_button.clicked.connect(self.rotate_page)

        page_buttons.addWidget(add_button)
        page_buttons.addWidget(self.delete_button)
        page_buttons.addWidget(self.move_up_button)
        page_buttons.addWidget(self.move_down_button)
        page_buttons.addWidget(self.rotate_button)
        layout.addLayout(page_buttons)

        bottom_buttons = QHBoxLayout()
        bottom_buttons.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        save_button = QPushButton("Save Updated PDF")
        save_button.clicked.connect(self.save_updated_pdf)

        bottom_buttons.addWidget(cancel_button)
        bottom_buttons.addWidget(save_button)
        layout.addLayout(bottom_buttons)

    def refresh_page_list(self, selected_row=0):
        self.page_list.blockSignals(True)
        self.page_list.clear()
        for index in range(len(self.document)):
            self.page_list.addItem(f"Page {index + 1}")
        if self.page_list.count():
            self.page_list.setCurrentRow(
                min(max(selected_row, 0), self.page_list.count() - 1)
            )
        self.page_list.blockSignals(False)
        self.update_buttons(self.page_list.currentRow())

    def update_buttons(self, row):
        page_count = len(self.document)
        has_selection = 0 <= row < page_count

        self.delete_button.setEnabled(has_selection and page_count > 1)
        self.move_up_button.setEnabled(has_selection and row > 0)
        self.move_down_button.setEnabled(
            has_selection and row < page_count - 1
        )
        self.rotate_button.setEnabled(has_selection)

    def add_blank_page(self):
        row = self.page_list.currentRow()
        if 0 <= row < len(self.document):
            reference_page = self.document.load_page(row)
            width = reference_page.rect.width
            height = reference_page.rect.height
            insert_at = row + 1
        else:
            width, height = 595, 842
            insert_at = len(self.document)

        self.document.new_page(
            pno=insert_at,
            width=width,
            height=height,
        )
        self.refresh_page_list(insert_at)

    def delete_page(self):
        row = self.page_list.currentRow()
        if 0 <= row < len(self.document) and len(self.document) > 1:
            self.document.delete_page(row)
            self.refresh_page_list(min(row, len(self.document) - 1))

    def move_page_up(self):
        row = self.page_list.currentRow()
        if row > 0:
            self.document.move_page(row, row - 1)
            self.refresh_page_list(row - 1)

    def move_page_down(self):
        row = self.page_list.currentRow()
        if 0 <= row < len(self.document) - 1:
            self.document.move_page(row, row + 1)
            self.refresh_page_list(row + 1)

    def rotate_page(self):
        row = self.page_list.currentRow()
        if 0 <= row < len(self.document):
            page = self.document.load_page(row)
            page.set_rotation((page.rotation + 90) % 360)
            self.refresh_page_list(row)

    def save_updated_pdf(self):
        default_path = os.path.splitext(self.file_path)[0] + "_updated.pdf"
        output_file, _ = QFileDialog.getSaveFileName(
            self,
            "Save Updated PDF",
            default_path,
            "PDF Files (*.pdf)",
        )
        if not output_file:
            return

        if not output_file.lower().endswith(".pdf"):
            output_file += ".pdf"

        if os.path.normcase(os.path.abspath(output_file)) == os.path.normcase(
            os.path.abspath(self.file_path)
        ):
            QMessageBox.warning(
                self,
                "Choose Another File",
                "Save the updated PDF to a different file so the original "
                "remains unchanged.",
            )
            return

        try:
            self.document.save(
                output_file,
                garbage=4,
                deflate=True,
                clean=True,
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Update Error",
                f"Could not save the updated PDF:\n\n{error}",
            )
            return

        self.output_file = output_file
        QMessageBox.information(
            self,
            "PDF Updated",
            f"Updated PDF saved to:\n{output_file}",
        )
        self.accept()

    def done(self, result):
        if self.document:
            self.document.close()
            self.document = None
        super().done(result)
