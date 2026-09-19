import sys

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QToolBar,
    QTabWidget,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence

from pdf_viewer import PDFViewer
from export_dialog import ExportDialog
from split_dialog import SplitDialog
from merge_dialog import MergeDialog
from compress_dialog import CompressDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

        self.setWindowTitle("PDF Viewer")
        self.resize(1200, 800)

        self.create_home_toolbar()
        self.create_tabs()

    def create_home_toolbar(self):
        close_shortcut = QAction(self)
        close_shortcut.setShortcut(QKeySequence("Ctrl+W"))
        close_shortcut.triggered.connect(self.close_current_tab)

        self.addAction(close_shortcut)

        self.home_toolbar = QToolBar("Home")
        self.home_toolbar.setObjectName("HomeToolbar")
        self.home_toolbar.setIconSize(QSize(24, 24))
        self.home_toolbar.setMovable(False)

        self.addToolBar(self.home_toolbar)

        open_action = QAction("Open PDF", self)
        open_action.triggered.connect(self.open_pdf)

        self.home_toolbar.addAction(open_action)

        open_multiple_action = QAction("Open Multiple PDFs", self)
        open_multiple_action.triggered.connect(self.open_multiple_pdfs)

        self.home_toolbar.addAction(open_multiple_action)

        self.home_toolbar.addSeparator()

        close_action = QAction("Close", self)
        close_action.triggered.connect(self.close_current_tab)

        self.home_toolbar.addAction(close_action)

        close_all_action = QAction("Close All", self)
        close_all_action.triggered.connect(self.close_all_tabs)

        self.home_toolbar.addAction(close_all_action)

        # Export Dialog
        self.home_toolbar.addSeparator()
        export_action = QAction("Export", self)
        export_action.triggered.connect(self.export_current_pdf)
        self.home_toolbar.addAction(export_action)

        # split Dialog
        split_action = QAction("Split", self)
        split_action.triggered.connect(self.split_current_pdf)

        self.home_toolbar.addAction(split_action)

        # Merge Dialog
        merge_action = QAction("Merge", self)
        merge_action.triggered.connect(self.merge_pdfs)

        self.home_toolbar.addAction(merge_action)

        # Merge Dialog
        compress_action = QAction("Compress", self)
        compress_action.triggered.connect(
            self.compress_current_pdf
        )

        self.home_toolbar.addAction(
            compress_action
        )

    def create_tabs(self):
        self.tabs = QTabWidget()

        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)

        self.tabs.tabCloseRequested.connect(self.close_tab)

        self.setCentralWidget(self.tabs)

    def open_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PDF",
            "",
            "PDF Files (*.pdf)"
        )

        if file_path:
            self.add_pdf_tab(file_path)

    def open_multiple_pdfs(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open PDF Files",
            "",
            "PDF Files (*.pdf)"
        )

        for file_path in file_paths:
            self.add_pdf_tab(file_path)

    def add_pdf_tab(self, file_path):
        try:
            viewer = PDFViewer(file_path)

            file_name = file_path.split("/")[-1]
            file_name = file_name.split("\\")[-1]

            index = self.tabs.addTab(viewer, file_name)
            self.tabs.setCurrentIndex(index)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Could not open PDF:\n\n{e}"
            )

    def close_current_tab(self):
        index = self.tabs.currentIndex()

        if index >= 0:
            self.close_tab(index)

    def close_tab(self, index):
        widget = self.tabs.widget(index)

        if widget:
            widget.close_document()
            widget.deleteLater()

        self.tabs.removeTab(index)

    def close_all_tabs(self):
        while self.tabs.count() > 0:
            self.close_tab(0)

    def closeEvent(self, event):
        self.close_all_tabs()
        event.accept()


    def export_current_pdf(self):
        index = self.tabs.currentIndex()

        if index < 0:
            QMessageBox.warning(
                self,
                "Export",
                "Please open a PDF first.",
            )
            return

        viewer = self.tabs.widget(index)

        dialog = ExportDialog(
            viewer.file_path,
            viewer.current_page,
            self,
        )

        dialog.exec()

    def split_current_pdf(self):
        index = self.tabs.currentIndex()

        if index < 0:
            QMessageBox.warning(
                self,
                "Split",
                "Please open a PDF first.",
            )
            return

        viewer = self.tabs.widget(index)

        dialog = SplitDialog(
            viewer.file_path,
            self,
        )

        dialog.exec()


    def merge_pdfs(self):
        dialog = MergeDialog(self)
        dialog.exec()


    def compress_current_pdf(self):
        index = self.tabs.currentIndex()

        if index < 0:
            QMessageBox.warning(
                self,
                "Compress",
                "Please open a PDF first.",
            )
            return

        viewer = self.tabs.widget(index)

        dialog = CompressDialog(
            viewer.file_path,
            self,
        )

        dialog.exec()

def main():
    app = QApplication(sys.argv)

    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()