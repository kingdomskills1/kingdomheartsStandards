import fitz

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QComboBox,
    QLabel,
    QScrollArea,
)


class PDFPage(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #808080;")
        self.setMinimumSize(100, 100)

        self.original_pixmap = None

    def set_page(self, pixmap):
        self.original_pixmap = pixmap
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())


class PDFViewer(QWidget):
    def __init__(self, file_path):
        super().__init__()

        self.file_path = file_path
        self.document = fitz.open(file_path)

        self.current_page = 0
        self.zoom = 1.0
        self.two_page_view = False
        self.fit_page_active = False

        # PDF page
        self.page_label = PDFPage()

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.page_label)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )

        # Keyboard focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Install event filters AFTER the widgets exist
        self.installEventFilter(self)
        self.scroll_area.installEventFilter(self)
        self.page_label.installEventFilter(self)

        # Page number
        self.page_number = QSpinBox()
        self.page_number.setMinimum(1)
        self.page_number.setMaximum(len(self.document))
        self.page_number.setValue(1)
        self.page_number.valueChanged.connect(self.go_to_page)

        # Zoom
        self.zoom_box = QComboBox()
        self.zoom_box.addItems([
            "50%",
            "75%",
            "100%",
            "125%",
            "150%",
            "200%",
            "250%",
        ])
        self.zoom_box.setCurrentText("100%")
        self.zoom_box.currentTextChanged.connect(self.change_zoom)

        # Fit Page
        self.fit_page_button = QPushButton("Fit Page")
        self.fit_page_button.clicked.connect(self.fit_page)

        # Page layout toggle
        self.toggle_pages_button = QPushButton("Two Pages")
        self.toggle_pages_button.clicked.connect(self.toggle_page_layout)

        # Navigation buttons
        self.previous_button = QPushButton("◀")
        self.next_button = QPushButton("▶")

        self.previous_button.setFixedWidth(40)
        self.next_button.setFixedWidth(40)

        self.previous_button.clicked.connect(self.previous_page)
        self.next_button.clicked.connect(self.next_page)

        # Navigation layout
        navigation = QHBoxLayout()

        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.page_number)
        navigation.addWidget(QLabel(f" / {len(self.document)}"))
        navigation.addWidget(self.next_button)

        navigation.addStretch()

        navigation.addWidget(QLabel("Zoom:"))
        navigation.addWidget(self.zoom_box)
        navigation.addWidget(self.fit_page_button)
        navigation.addWidget(self.toggle_pages_button)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addLayout(navigation)
        layout.addWidget(self.scroll_area)

        # Render first page
        self.render_page()

    # ---------------------------------------------------------
    # PDF Rendering
    # ---------------------------------------------------------

    def render_page(self):
        current_pixmap = self._render_page(self.current_page)

        if self.two_page_view and self.current_page + 1 < len(self.document):
            next_pixmap = self._render_page(self.current_page + 1)
            spread = QPixmap(
                current_pixmap.width() + next_pixmap.width(),
                max(current_pixmap.height(), next_pixmap.height()),
            )
            spread.fill(Qt.GlobalColor.gray)

            painter = QPainter(spread)
            painter.drawPixmap(0, 0, current_pixmap)
            painter.drawPixmap(current_pixmap.width(), 0, next_pixmap)
            painter.end()
            self.page_label.set_page(spread)
        else:
            self.page_label.set_page(current_pixmap)

        # Synchronize page number
        self.page_number.blockSignals(True)
        self.page_number.setValue(self.current_page + 1)
        self.page_number.blockSignals(False)

        # Enable / disable navigation buttons
        page_step = 2 if self.two_page_view else 1
        self.previous_button.setEnabled(self.current_page >= page_step)
        self.next_button.setEnabled(
            self.current_page + page_step < len(self.document)
        )

        # Scroll to top when changing page
        self.scroll_area.verticalScrollBar().setValue(0)
        self.scroll_area.horizontalScrollBar().setValue(0)

    def _render_page(self, page_index):
        page = self.document.load_page(page_index)
        matrix = fitz.Matrix(self.zoom, self.zoom)

        pix = page.get_pixmap(
            matrix=matrix,
            alpha=False
        )

        image = QImage(
            pix.samples,
            pix.width,
            pix.height,
            pix.stride,
            QImage.Format.Format_RGB888
        )

        return QPixmap.fromImage(image.copy())

    # ---------------------------------------------------------
    # Previous Page
    # ---------------------------------------------------------

    def previous_page(self):
        page_step = 2 if self.two_page_view else 1
        if self.current_page >= page_step:
            self.current_page -= page_step
            self.render_page()

    # ---------------------------------------------------------
    # Next Page
    # ---------------------------------------------------------

    def next_page(self):
        page_step = 2 if self.two_page_view else 1
        if self.current_page + page_step < len(self.document):
            self.current_page += page_step
            self.render_page()

    # ---------------------------------------------------------
    # Go To Page
    # ---------------------------------------------------------

    def go_to_page(self, page_number):
        page_index = page_number - 1

        if 0 <= page_index < len(self.document):
            if self.two_page_view:
                page_index -= page_index % 2
            self.current_page = page_index
            self.render_page()

    def go_to_bookmark(self, page_number, zoom=None, point=None):
        page_index = page_number - 1
        if not 0 <= page_index < len(self.document):
            return

        if self.two_page_view:
            page_index -= page_index % 2
        if zoom is not None and zoom > 0:
            self.zoom = float(zoom)
            self.fit_page_active = False
            zoom_text = f"{round(self.zoom * 100)}%"
            self.zoom_box.blockSignals(True)
            if self.zoom_box.findText(zoom_text) == -1:
                self.zoom_box.addItem(zoom_text)
            self.zoom_box.setCurrentText(zoom_text)
            self.zoom_box.blockSignals(False)

        self.current_page = page_index
        self.render_page()

        if point is not None:
            self.scroll_area.horizontalScrollBar().setValue(
                round(max(0, point.x) * self.zoom)
            )
            self.scroll_area.verticalScrollBar().setValue(
                round(max(0, point.y) * self.zoom)
            )

    # ---------------------------------------------------------
    # Zoom
    # ---------------------------------------------------------

    def change_zoom(self, value):
        self.fit_page_active = False
        self.zoom = int(value.replace("%", "")) / 100
        self.render_page()

    # ---------------------------------------------------------
    # Fit Page
    # ---------------------------------------------------------

    def fit_page(self):
        page = self.document.load_page(self.current_page)

        available_width = self.scroll_area.viewport().width()
        available_height = self.scroll_area.viewport().height()

        page_width = page.rect.width
        page_height = page.rect.height

        if page_width <= 0 or page_height <= 0:
            return

        self.fit_page_active = True
        zoom_x = available_width / page_width
        zoom_y = available_height / page_height

        self.zoom = min(zoom_x, zoom_y)

        self.render_page()

        percentage = round(self.zoom * 100)

        self.zoom_box.blockSignals(True)

        if self.zoom_box.findText(f"{percentage}%") == -1:
            self.zoom_box.addItem(f"{percentage}%")

        self.zoom_box.setCurrentText(f"{percentage}%")

        self.zoom_box.blockSignals(False)

    def toggle_page_layout(self):
        self.two_page_view = not self.two_page_view
        if self.two_page_view:
            self.current_page -= self.current_page % 2
        self.toggle_pages_button.setText("One Page" if self.two_page_view else "Two Pages")
        self.render_page()

    # ---------------------------------------------------------
    # Keyboard Handling
    # ---------------------------------------------------------
    def eventFilter(self, watched, event):

        # Keyboard
        if event.type() == QEvent.Type.KeyPress:

            if event.key() == Qt.Key.Key_Left:
                self.previous_page()
                return True

            if event.key() == Qt.Key.Key_Right:
                self.next_page()
                return True

        # Mouse wheel
        if event.type() == QEvent.Type.Wheel:

            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:

                delta = event.angleDelta().y()

                if delta > 0:
                    self.zoom_in()

                elif delta < 0:
                    self.zoom_out()

                return True

            if self.fit_page_active:
                delta = event.angleDelta().y()
                if delta == 0:
                    delta = event.pixelDelta().y()

                if delta > 0:
                    self.previous_page()
                    return True

                if delta < 0:
                    self.next_page()
                    return True

        return super().eventFilter(watched, event)


    # ---------------------------------------------------------
    # Direct Keyboard Handling
    # ---------------------------------------------------------

    def keyPressEvent(self, event):

        if event.key() == Qt.Key.Key_Left:
            self.previous_page()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Right:
            self.next_page()
            event.accept()
            return

        super().keyPressEvent(event)

    # ---------------------------------------------------------
    # Close PDF
    # ---------------------------------------------------------

    def close_document(self):
        if self.document:
            self.document.close()
            self.document = None

    def closeEvent(self, event):
        self.close_document()
        event.accept()

    def zoom_in(self):
        self.fit_page_active = False
        self.zoom = min(self.zoom * 1.1, 5.0)

        self.render_page()

        self.update_zoom_box()


    def zoom_out(self):
        self.fit_page_active = False
        self.zoom = max(self.zoom / 1.1, 0.1)

        self.render_page()

        self.update_zoom_box()

    def update_zoom_box(self):
        percentage = round(self.zoom * 100)

        self.zoom_box.blockSignals(True)

        text = f"{percentage}%"

        if self.zoom_box.findText(text) == -1:
            self.zoom_box.addItem(text)

        self.zoom_box.setCurrentText(text)

        self.zoom_box.blockSignals(False)