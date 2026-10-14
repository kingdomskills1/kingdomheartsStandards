import sys
import os
import json
import subprocess
import tempfile

import fitz

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QDockWidget,
    QToolBar,
    QTabWidget,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QPushButton,
    QLabel,
    QMenu,
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from pdf_viewer import PDFViewer
from export_dialog import ExportDialog
from split_dialog import SplitDialog
from merge_dialog import MergeDialog
from compress_dialog import CompressDialog
from page_manager_dialog import PageManagerDialog
from pdf_editor_dialog import PDFEditorDialog


class BookmarkTree(QTreeWidget):
    orderChanged = Signal()

    def dropEvent(self, event):
        super().dropEvent(event)
        self.orderChanged.emit()


class BookmarkPanel(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.viewer = None
        self._refreshing = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Bookmarks"))

        self.tree = BookmarkTree()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(
            QTreeWidget.DragDropMode.InternalMove
        )
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree.itemClicked.connect(self.open_bookmark)
        self.tree.orderChanged.connect(self.apply_tree_order)
        layout.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.add_bookmark)
        buttons.addWidget(self.add_button)

        self.add_child_button = QPushButton("Add Sub")
        self.add_child_button.clicked.connect(self.add_sub_bookmark)
        buttons.addWidget(self.add_child_button)

        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self.edit_bookmark)
        buttons.addWidget(self.edit_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_bookmark)
        buttons.addWidget(self.delete_button)
        layout.addLayout(buttons)

        self.set_viewer(None)

    def set_viewer(self, viewer):
        self.viewer = viewer
        self.tree.clear()
        enabled = viewer is not None
        for button in (
            self.add_button,
            self.add_child_button,
            self.edit_button,
            self.delete_button,
        ):
            button.setEnabled(enabled)
        if not enabled:
            return

        parents = []
        try:
            toc = getattr(
                viewer,
                "bookmark_entries",
                viewer.document.get_toc(simple=False),
            )
        except Exception as error:
            QMessageBox.warning(
                self,
                "Bookmarks",
                f"Could not read PDF bookmarks:\n\n{error}",
            )
            return

        self._refreshing = True
        for entry in toc:
            level, title, page_number = entry[:3]
            item = QTreeWidgetItem(
                [f"{title}  (Page {page_number})"]
            )
            item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {
                    "title": title,
                    "page": page_number,
                    "entry": entry,
                },
            )
            while len(parents) >= level:
                parents.pop()
            if level == 1:
                self.tree.addTopLevelItem(item)
            elif parents:
                parents[-1].addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            parents.append(item)
        self.tree.expandAll()
        self._refreshing = False

    def current_page_number(self):
        return self.viewer.current_page + 1 if self.viewer is not None else 1

    def open_bookmark(self, item, _column):
        if self.viewer is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is not None:
            destination = data.get("entry", [None, None, None])
            destination = (
                destination[3]
                if len(destination) > 3 and isinstance(destination[3], dict)
                else {}
            )
            self.viewer.go_to_bookmark(
                data["page"],
                destination.get("zoom"),
                destination.get("to"),
            )

    def add_bookmark(self):
        self.create_bookmark(None)

    def add_sub_bookmark(self):
        selected = self.tree.currentItem()
        if selected is None:
            QMessageBox.information(
                self,
                "Add Sub-bookmark",
                "Select a bookmark to add a sub-bookmark under it.",
            )
            return
        self.create_bookmark(selected)

    def create_bookmark(self, parent_item):
        title, accepted = QInputDialog.getText(
            self,
            "Add Bookmark",
            "Bookmark name:",
        )
        if not accepted or not title.strip():
            return
        page_number, accepted = QInputDialog.getInt(
            self,
            "Add Bookmark",
            "Page number:",
            self.current_page_number(),
            1,
            len(self.viewer.document),
        )
        if not accepted:
            return

        item = QTreeWidgetItem(
            [f"{title.strip()}  (Page {page_number})"]
        )
        destination = self.capture_destination(page_number)
        item.setData(
            0,
            Qt.ItemDataRole.UserRole,
            {
                "title": title.strip(),
                "page": page_number,
                "entry": [
                    1,
                    title.strip(),
                    page_number,
                    destination,
                ],
            },
        )
        if parent_item is None:
            self.tree.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
            parent_item.setExpanded(True)
        self.tree.setCurrentItem(item)
        self.apply_tree_order()

    def edit_bookmark(self):
        item = self.tree.currentItem()
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        title, accepted = QInputDialog.getText(
            self,
            "Edit Bookmark",
            "Bookmark name:",
            text=data["title"],
        )
        if not accepted or not title.strip():
            return
        page_number, accepted = QInputDialog.getInt(
            self,
            "Edit Bookmark",
            "Page number:",
            data["page"],
            1,
            len(self.viewer.document),
        )
        if not accepted:
            return
        data["title"] = title.strip()
        data["page"] = page_number
        data["entry"] = [
            1,
            data["title"],
            page_number,
            self.capture_destination(page_number),
        ]
        item.setData(0, Qt.ItemDataRole.UserRole, data)
        item.setText(0, f"{data['title']}  (Page {page_number})")
        self.apply_tree_order()

    def capture_destination(self, page_number):
        zoom = max(float(self.viewer.zoom), 0.01)
        page = self.viewer.document.load_page(page_number - 1)
        scroll_x = self.viewer.scroll_area.horizontalScrollBar().value()
        scroll_y = self.viewer.scroll_area.verticalScrollBar().value()
        point = fitz.Point(
            min(max(scroll_x / zoom, 0), page.rect.width),
            min(max(scroll_y / zoom, 0), page.rect.height),
        )
        return {
            "kind": fitz.LINK_GOTO,
            "page": page_number - 1,
            "to": point,
            "zoom": zoom,
        }

    def delete_bookmark(self):
        item = self.tree.currentItem()
        if item is None:
            return
        parent = item.parent()
        if parent is None:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        else:
            parent.takeChild(parent.indexOfChild(item))
        self.apply_tree_order()

    def apply_tree_order(self):
        if self._refreshing or self.viewer is None:
            return
        entries = []
        item_entries = []

        def append_items(parent, level):
            is_root = parent is self.tree.invisibleRootItem()
            count = (
                self.tree.topLevelItemCount()
                if is_root
                else parent.childCount()
            )
            for index in range(count):
                item = (
                    self.tree.topLevelItem(index)
                    if is_root
                    else parent.child(index)
                )
                data = item.data(0, Qt.ItemDataRole.UserRole)
                entry = (
                    list(data["entry"])
                    if data["entry"]
                    else [level, data["title"], data["page"]]
                )
                entry[0] = level
                entry[1] = data["title"]
                entry[2] = data["page"]
                if len(entry) > 3 and isinstance(entry[3], dict):
                    entry[3] = dict(entry[3])
                    entry[3].pop("xref", None)
                entries.append(entry)
                item_entries.append((item, entry))
                append_items(item, level + 1)

        append_items(self.tree.invisibleRootItem(), 1)
        try:
            if not self.main_window.save_bookmarks(self.viewer, entries):
                self.set_viewer(self.viewer)
                return
            for item, entry in item_entries:
                data = item.data(0, Qt.ItemDataRole.UserRole)
                data["entry"] = list(entry)
                item.setData(0, Qt.ItemDataRole.UserRole, data)
        except Exception as error:
            QMessageBox.critical(
                self,
                "Bookmark Error",
                f"Could not update PDF bookmarks:\n\n{error}",
            )
            self.set_viewer(self.viewer)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

        self.setWindowTitle("PDF Studio")
        self.resize(1200, 800)

        self.create_home_toolbar()
        self.create_tabs()
        self.create_bookmark_sidebar()

    def open_pdf_paths(self, file_paths):
        for file_path in file_paths:
            if os.path.splitext(file_path)[1].lower() == ".pdf":
                self.add_pdf_tab(os.path.abspath(file_path))

        self.showNormal()
        self.raise_()
        self.activateWindow()

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

        self.recent_files_menu = QMenu("Recent PDFs", self)
        self.recent_action = QAction("Recent PDFs", self)
        self.recent_action.setMenu(self.recent_files_menu)
        self.refresh_recent_files_menu()
        self.home_toolbar.addAction(self.recent_action)

        self.home_toolbar.addSeparator()

        create_action = QAction("Create PDF", self)
        create_action.triggered.connect(self.create_pdf)
        self.home_toolbar.addAction(create_action)

        edit_content_action = QAction("Edit Content", self)
        edit_content_action.triggered.connect(self.edit_current_pdf_content)
        self.home_toolbar.addAction(edit_content_action)

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

    def load_recent_pdfs(self):
        if not hasattr(self, "recent_pdfs_file"):
            self.recent_pdfs_file = os.path.join(
                os.path.expanduser("~"),
                ".pdf_studio_recent_pdfs.txt",
            )

        try:
            if not os.path.exists(self.recent_pdfs_file):
                return []

            with open(self.recent_pdfs_file, "r", encoding="utf-8") as file:
                entries = [
                    os.path.abspath(line.strip())
                    for line in file
                    if line.strip()
                ]
        except OSError:
            return []

        unique_paths = []
        seen = set()
        for file_path in entries:
            normalized = os.path.normcase(os.path.abspath(file_path))
            if normalized in seen or not os.path.isfile(normalized):
                continue
            seen.add(normalized)
            unique_paths.append(normalized)
        return unique_paths[:10]

    def save_recent_pdfs(self, file_paths):
        if not hasattr(self, "recent_pdfs_file"):
            self.recent_pdfs_file = os.path.join(
                os.path.expanduser("~"),
                ".pdf_studio_recent_pdfs.txt",
            )

        directory = os.path.dirname(self.recent_pdfs_file)
        if directory and not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError:
                return

        try:
            with open(self.recent_pdfs_file, "w", encoding="utf-8") as file:
                for file_path in file_paths:
                    file.write(f"{file_path}\n")
        except OSError:
            pass

    def add_recent_pdf(self, file_path):
        if not file_path:
            return

        normalized_path = os.path.normcase(os.path.abspath(file_path))
        if not os.path.isfile(normalized_path):
            return

        recent_paths = [
            os.path.normcase(os.path.abspath(path))
            for path in self.load_recent_pdfs()
        ]
        recent_paths = [
            path for path in recent_paths if path != normalized_path
        ]
        recent_paths.insert(0, normalized_path)
        recent_paths = recent_paths[:10]

        self.save_recent_pdfs(recent_paths)
        if hasattr(self, "recent_files_menu"):
            self.refresh_recent_files_menu()

    def open_recent_pdf(self, file_path):
        if not file_path or not os.path.isfile(file_path):
            QMessageBox.warning(
                self,
                "Recent PDF",
                f"This recent PDF is no longer available:\n\n{file_path}",
            )
            return
        self.add_pdf_tab(file_path)

    def clear_recent_pdfs(self):
        self.save_recent_pdfs([])
        if hasattr(self, "recent_files_menu"):
            self.refresh_recent_files_menu()

    def refresh_recent_files_menu(self):
        if not hasattr(self, "recent_files_menu"):
            return

        self.recent_files_menu.clear()
        recent_paths = self.load_recent_pdfs()

        if not recent_paths:
            no_recent_action = QAction("No recent PDFs", self)
            no_recent_action.setEnabled(False)
            self.recent_files_menu.addAction(no_recent_action)
            return

        for file_path in recent_paths:
            action = QAction(file_path, self)
            action.triggered.connect(
                lambda _checked=False, path=file_path: self.open_recent_pdf(path)
            )
            self.recent_files_menu.addAction(action)

        self.recent_files_menu.addSeparator()
        clear_action = QAction("Clear Recent PDFs", self)
        clear_action.triggered.connect(self.clear_recent_pdfs)
        self.recent_files_menu.addAction(clear_action)

    def create_tabs(self):
        self.tabs = QTabWidget()

        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)

        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.sync_bookmarks)

        self.setCentralWidget(self.tabs)

    def create_bookmark_sidebar(self):
        self.bookmark_dock = QDockWidget("Bookmarks", self)
        self.bookmark_dock.setObjectName("BookmarksDock")
        self.bookmark_panel = BookmarkPanel(self)
        self.bookmark_dock.setWidget(self.bookmark_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.bookmark_dock)

        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.bookmark_dock.toggleViewAction())

    def sync_bookmarks(self, index=None):
        if index is None:
            index = self.tabs.currentIndex()
        viewer = self.tabs.widget(index) if index >= 0 else None
        self.bookmark_panel.set_viewer(viewer)

    def save_bookmarks(self, viewer, entries):
        temporary_path = None
        output_document = None
        same_file_viewers = []
        saved_view_states = []
        target_path = os.path.normcase(os.path.abspath(viewer.file_path))

        try:
            output_document = fitz.open(
                stream=viewer.document.tobytes(),
                filetype="pdf",
            )
            output_document.set_toc(entries)

            target_folder = os.path.dirname(os.path.abspath(viewer.file_path))
            file_descriptor, temporary_path = tempfile.mkstemp(
                suffix=".pdf",
                dir=target_folder,
            )
            os.close(file_descriptor)
            os.remove(temporary_path)
            output_document.save(
                temporary_path,
                garbage=4,
                deflate=True,
                clean=True,
            )
            output_document.close()
            output_document = None

            for index in range(self.tabs.count()):
                open_viewer = self.tabs.widget(index)
                if (
                    isinstance(open_viewer, PDFViewer)
                    and os.path.normcase(os.path.abspath(open_viewer.file_path))
                    == target_path
                ):
                    same_file_viewers.append(open_viewer)
                    saved_view_states.append(
                        {
                            "page": open_viewer.current_page,
                            "zoom": open_viewer.zoom,
                            "fit": open_viewer.fit_page_active,
                            "two_page": open_viewer.two_page_view,
                            "scroll_x": (
                                open_viewer.scroll_area.horizontalScrollBar().value()
                            ),
                            "scroll_y": (
                                open_viewer.scroll_area.verticalScrollBar().value()
                            ),
                        }
                    )

            for open_viewer in same_file_viewers:
                open_viewer.close_document()

            os.replace(temporary_path, viewer.file_path)
            temporary_path = None

            for open_viewer, state in zip(
                same_file_viewers,
                saved_view_states,
            ):
                open_viewer.document = fitz.open(open_viewer.file_path)
                open_viewer.current_page = min(
                    state["page"],
                    len(open_viewer.document) - 1,
                )
                open_viewer.page_number.setMaximum(
                    len(open_viewer.document)
                )
                open_viewer.zoom = state["zoom"]
                open_viewer.fit_page_active = state["fit"]
                open_viewer.two_page_view = state["two_page"]
                open_viewer.render_page()
                open_viewer.scroll_area.horizontalScrollBar().setValue(
                    state["scroll_x"]
                )
                open_viewer.scroll_area.verticalScrollBar().setValue(
                    state["scroll_y"]
                )
                open_viewer.bookmark_entries = (
                    open_viewer.document.get_toc(simple=False)
                )

            return True
        except Exception as error:
            if output_document is not None:
                output_document.close()
            for open_viewer in same_file_viewers:
                if open_viewer.document is None:
                    open_viewer.document = fitz.open(open_viewer.file_path)
            QMessageBox.critical(
                self,
                "Bookmark Save Error",
                f"Could not automatically save bookmarks to the PDF:\n\n{error}",
            )
            return False
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.remove(temporary_path)

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

    def create_pdf(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Create PDF",
            "",
            "PDF Files (*.pdf)",
        )
        if not file_path:
            return

        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"

        dialog = PDFEditorDialog(
            initial_output_path=file_path,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.output_path:
            self.add_pdf_tab(dialog.output_path)

    def edit_current_pdf_content(self):
        index = self.tabs.currentIndex()
        if index < 0:
            QMessageBox.warning(
                self,
                "Edit Content",
                "Please open a PDF first.",
            )
            return

        viewer = self.tabs.widget(index)
        dialog = PDFEditorDialog(viewer.file_path, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.output_path:
            self.add_pdf_tab(dialog.output_path)

    def update_current_pdf(self):
        index = self.tabs.currentIndex()
        if index < 0:
            QMessageBox.warning(
                self,
                "Update PDF",
                "Please open a PDF first.",
            )
            return

        viewer = self.tabs.widget(index)
        dialog = PageManagerDialog(viewer.file_path, self)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted and dialog.output_file:
                self.add_pdf_tab(dialog.output_file)
        finally:
            if dialog.document:
                dialog.document.close()
                dialog.document = None

    def add_pdf_tab(self, file_path):
        try:
            viewer = PDFViewer(file_path)

            file_name = file_path.split("/")[-1]
            file_name = file_name.split("\\")[-1]

            self.add_recent_pdf(file_path)

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
    app.setApplicationName("PDF Studio")

    app.setStyle("Fusion")

    server = None
    if os.name == "nt":
        server_name = "PDFStudioSingleInstance"
        if forward_to_running_instance(server_name, sys.argv[1:]):
            return

        server = QLocalServer()
        if not server.listen(server_name):
            if forward_to_running_instance(server_name, sys.argv[1:]):
                return

            QLocalServer.removeServer(server_name)
            if not server.listen(server_name):
                QMessageBox.critical(
                    None,
                    "PDF Studio",
                    "Could not start the single-instance service:\n\n"
                    f"{server.errorString()}",
                )
                return

    window = MainWindow()
    if server is not None:
        server.newConnection.connect(
            lambda: open_instance_requests(server, window)
        )
    window.open_pdf_paths(sys.argv[1:])
    window.show()

    if os.name == "nt":
        try:
            register_windows_pdf_handler()
        except OSError as error:
            QMessageBox.warning(
                window,
                "Windows Default Apps",
                f"PDF Studio could not register as a PDF app:\n\n{error}",
            )

    sys.exit(app.exec())


def forward_to_running_instance(server_name, file_paths):
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if not socket.waitForConnected(500):
        return False

    payload = json.dumps(file_paths).encode("utf-8") + b"\n"
    if socket.write(payload) != len(payload):
        socket.abort()
        return False
    if (
        socket.bytesToWrite()
        and not socket.waitForBytesWritten(1000)
        and socket.bytesToWrite()
    ):
        socket.abort()
        return False
    socket.flush()
    socket.disconnectFromServer()
    return True


def open_instance_requests(server, window):
    while server.hasPendingConnections():
        socket = server.nextPendingConnection()
        buffer = bytearray()

        def read_request(socket=socket, buffer=buffer):
            buffer.extend(bytes(socket.readAll()))
            while b"\n" in buffer:
                message, _, remaining = buffer.partition(b"\n")
                buffer[:] = remaining
                try:
                    file_paths = json.loads(message)
                    if not isinstance(file_paths, list) or not all(
                        isinstance(path, str) for path in file_paths
                    ):
                        raise ValueError("Expected a list of file paths.")
                except (json.JSONDecodeError, ValueError) as error:
                    QMessageBox.warning(
                        window,
                        "PDF Studio",
                        f"Could not process files from another launch:\n\n{error}",
                    )
                    continue

                window.open_pdf_paths(file_paths)

        socket.readyRead.connect(read_request)
        socket.disconnected.connect(socket.deleteLater)
        read_request()


def register_windows_pdf_handler():
    if os.name != "nt":
        return

    import winreg

    app_name = "PDF Studio"
    prog_id = "PDFStudio.Document"
    capabilities_path = "Software\\PDF Studio\\Capabilities"
    classes_path = "Software\\Classes"

    if getattr(sys, "frozen", False):
        executable = sys.executable
        command = subprocess.list2cmdline([executable]) + ' "%1"'
    else:
        executable = os.path.join(
            os.path.dirname(sys.executable),
            "pythonw.exe",
        )
        if not os.path.isfile(executable):
            executable = sys.executable
        command = subprocess.list2cmdline(
            [executable, os.path.abspath(__file__)]
        ) + ' "%1"'

    def set_registry_value(path, name, value):
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            path,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    set_registry_value(
        f"{classes_path}\\{prog_id}",
        None,
        "PDF Studio PDF Document",
    )
    set_registry_value(
        f"{classes_path}\\{prog_id}\\shell\\open\\command",
        None,
        command,
    )
    set_registry_value(
        f"{classes_path}\\.pdf\\OpenWithProgids",
        prog_id,
        "",
    )
    set_registry_value(
        f"{capabilities_path}\\FileAssociations",
        ".pdf",
        prog_id,
    )
    set_registry_value(
        capabilities_path,
        "ApplicationName",
        app_name,
    )
    set_registry_value(
        capabilities_path,
        "ApplicationDescription",
        "View and edit PDF files with PDF Studio.",
    )
    set_registry_value(
        "Software\\RegisteredApplications",
        app_name,
        capabilities_path,
    )


if __name__ == "__main__":
    main()