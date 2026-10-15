import math
import os
import tempfile

import fitz

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFileDialog,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class PDFEditorCanvas(QGraphicsView):
    def __init__(self, scene, editor):
        super().__init__(scene, editor)
        self.editor = editor
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()

        if delta > 0:
            self.editor.previous_page()
            event.accept()
            return
        if delta < 0:
            self.editor.next_page()
            event.accept()
            return

        super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.editor.previous_page()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Right:
            self.editor.next_page()
            event.accept()
            return
        super().keyPressEvent(event)


class PageThumbnailList(QListWidget):
    pageOrderDropped = Signal(list, list)

    def dropEvent(self, event):
        super().dropEvent(event)
        page_order = [
            self.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.count())
        ]
        selected_page_ids = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.selectedItems()
        ]
        self.pageOrderDropped.emit(page_order, selected_page_ids)


class EditorPageManagerDialog(QDialog):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Manage Pages")
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available_size = screen.availableGeometry().size()
            self.resize(
                min(1200, max(520, available_size.width() - 60)),
                min(850, max(500, available_size.height() - 80)),
            )
        else:
            self.resize(1000, 750)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Drag pages to change their order. Select one or more pages "
                "to delete, or use Move Up and Move Down. Scroll through the "
                "thumbnail grid; image pages show their source filename."
            )
        )

        self.page_list = PageThumbnailList()
        self.page_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.page_list.setFlow(QListWidget.Flow.LeftToRight)
        self.page_list.setWrapping(True)
        self.page_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.page_list.setMovement(QListWidget.Movement.Snap)
        self.page_list.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
        )
        self.page_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.page_list.setDropIndicatorShown(True)
        self.page_list.setWordWrap(True)
        self.page_list.setIconSize(QSize(170, 210))
        self.page_list.setGridSize(QSize(220, 280))
        self.page_list.setSpacing(10)
        self.page_list.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.page_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.page_list.currentRowChanged.connect(self.select_editor_page)
        self.page_list.itemSelectionChanged.connect(self.update_buttons)
        self.page_list.pageOrderDropped.connect(self.apply_drag_order)
        layout.addWidget(self.page_list, 1)

        page_buttons = QHBoxLayout()
        self.move_up_button = QPushButton("Move Up")
        self.move_up_button.clicked.connect(lambda: self.move_selected_pages(-1))
        page_buttons.addWidget(self.move_up_button)

        self.move_down_button = QPushButton("Move Down")
        self.move_down_button.clicked.connect(lambda: self.move_selected_pages(1))
        page_buttons.addWidget(self.move_down_button)

        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.clicked.connect(self.delete_selected_pages)
        page_buttons.addWidget(self.delete_button)
        layout.addLayout(page_buttons)

        add_buttons = QHBoxLayout()
        add_blank_button = QPushButton("Add Blank Page")
        add_blank_button.clicked.connect(self.add_blank_page)
        add_buttons.addWidget(add_blank_button)

        add_images_button = QPushButton("Add Image Page(s)")
        add_images_button.clicked.connect(self.add_image_pages)
        add_buttons.addWidget(add_images_button)
        layout.addLayout(add_buttons)

        done_button = QPushButton("Done")
        done_button.clicked.connect(self.accept)
        layout.addWidget(done_button)

        self.refresh_page_list([self.editor.current_page])

    def selected_rows(self):
        return sorted(
            self.page_list.row(item)
            for item in self.page_list.selectedItems()
        )

    def select_editor_page(self, row):
        if 0 <= row < len(self.editor.document):
            self.editor.page_selector.setCurrentIndex(row)

    def refresh_page_list(self, selected_rows=None):
        if selected_rows is None:
            selected_rows = [self.editor.current_page]

        self.page_list.blockSignals(True)
        self.page_list.clear()
        for page_index, components in enumerate(
            self.editor.components_by_page
        ):
            page = self.editor.document.load_page(page_index)
            page_image = next(
                (
                    component
                    for component in components
                    if component.data.get("page_image", False)
                ),
                None,
            )
            if page_image is not None:
                thumbnail = page_image.image.scaled(
                    170,
                    210,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            else:
                pixmap_data = page.get_pixmap(
                    matrix=fitz.Matrix(0.28, 0.28),
                    alpha=False,
                )
                thumbnail = QPixmap.fromImage(
                    QImage(
                        pixmap_data.samples,
                        pixmap_data.width,
                        pixmap_data.height,
                        pixmap_data.stride,
                        QImage.Format.Format_RGB888,
                    ).copy()
                )
            if page_image is None:
                label = f"Page {page_index + 1}"
            else:
                image_path = page_image.data["path"]
                label = (
                    f"Page {page_index + 1} - "
                    f"{os.path.basename(image_path)}"
                )
            item = QListWidgetItem(QIcon(thumbnail), label)
            item.setData(Qt.ItemDataRole.UserRole, page_index)
            if page_image is not None:
                item.setToolTip(image_path)
            self.page_list.addItem(item)

        for row in selected_rows:
            if 0 <= row < self.page_list.count():
                self.page_list.item(row).setSelected(True)
        if selected_rows:
            current_row = min(
                max(selected_rows[0], 0),
                self.page_list.count() - 1,
            )
            self.page_list.setCurrentRow(current_row)
        self.page_list.blockSignals(False)
        self.update_buttons()

    def update_buttons(self):
        selected_rows = self.selected_rows()
        page_count = len(self.editor.document)
        selected_set = set(selected_rows)
        self.delete_button.setEnabled(
            bool(selected_rows) and len(selected_rows) < page_count
        )
        self.delete_button.setToolTip(
            "At least one page must remain in the document."
            if selected_rows and len(selected_rows) >= page_count
            else ""
        )
        self.move_up_button.setEnabled(
            any(row > 0 and row - 1 not in selected_set for row in selected_rows)
        )
        self.move_down_button.setEnabled(
            any(
                row < page_count - 1 and row + 1 not in selected_set
                for row in selected_rows
            )
        )

    def add_blank_page(self):
        self.editor.add_page()
        self.refresh_page_list([self.editor.current_page])

    def add_image_pages(self):
        page_count = len(self.editor.document)
        self.editor.add_image_pages()
        if len(self.editor.document) != page_count:
            self.refresh_page_list([self.editor.current_page])

    def delete_selected_pages(self):
        selected_rows = self.selected_rows()
        if not selected_rows:
            return
        if len(selected_rows) >= len(self.editor.document):
            QMessageBox.warning(
                self,
                "Keep One Page",
                "At least one page must remain in the document.",
            )
            return

        page_numbers = ", ".join(str(row + 1) for row in selected_rows)
        answer = QMessageBox.question(
            self,
            "Delete Pages",
            f"Delete page(s) {page_numbers}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        selected_current = self.editor.current_page in selected_rows
        if selected_current:
            remaining_page_count = (
                len(self.editor.document) - len(selected_rows)
            )
            selected_page = min(
                selected_rows[0],
                remaining_page_count - 1,
            )
        else:
            selected_page = self.editor.current_page - sum(
                row < self.editor.current_page for row in selected_rows
            )
        self.editor.delete_pages(selected_rows, selected_page)
        self.refresh_page_list([self.editor.current_page])

    def move_selected_pages(self, direction):
        selected_rows = self.selected_rows()
        if not selected_rows:
            return

        selected_pages = set(selected_rows)
        page_order = list(range(len(self.editor.document)))
        if direction < 0:
            for row in range(1, len(page_order)):
                if (
                    page_order[row] in selected_pages
                    and page_order[row - 1] not in selected_pages
                ):
                    page_order[row - 1], page_order[row] = (
                        page_order[row],
                        page_order[row - 1],
                    )
        else:
            for row in range(len(page_order) - 2, -1, -1):
                if (
                    page_order[row] in selected_pages
                    and page_order[row + 1] not in selected_pages
                ):
                    page_order[row], page_order[row + 1] = (
                        page_order[row + 1],
                        page_order[row],
                    )

        if page_order == list(range(len(page_order))):
            return

        new_selected_rows = [
            row for row, page_id in enumerate(page_order)
            if page_id in selected_pages
        ]
        self.editor.reorder_pages(page_order)
        self.refresh_page_list(new_selected_rows)

    def apply_drag_order(self, page_order, selected_page_ids):
        if page_order == list(range(len(self.editor.document))):
            return
        selected_rows = [
            page_order.index(page_id)
            for page_id in selected_page_ids
            if page_id in page_order
        ]
        self.editor.reorder_pages(page_order)
        self.refresh_page_list(selected_rows)


class ComponentPropertiesDialog(QDialog):
    def __init__(self, component, parent=None):
        super().__init__(parent)

        self.component = component
        self.values = {}
        self.setWindowTitle(f"{component.kind.replace('_', ' ').title()} Properties")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        scene_rect = component.mapRectToScene(component.rect())
        self.position_x = self.create_number(scene_rect.x(), -10000, 10000)
        self.position_y = self.create_number(scene_rect.y(), -10000, 10000)
        self.width_input = self.create_number(scene_rect.width(), 12, 10000)
        self.height_input = self.create_number(scene_rect.height(), 12, 10000)
        form.addRow("X position (pt):", self.position_x)
        form.addRow("Y position (pt):", self.position_y)
        form.addRow("Width (pt):", self.width_input)
        form.addRow("Height (pt):", self.height_input)

        self.data = dict(component.data)
        if component.kind == "text":
            self.text = QTextEdit(self.data.get("text", ""))
            self.text.setMinimumHeight(100)
            form.addRow("Text:", self.text)
            self.font_size = self.create_number(
                float(self.data.get("font_size", 14)), 1, 300
            )
            form.addRow("Font size (pt):", self.font_size)
            self.text_color = self.create_color_button(
                self.data.get("color", "#111827")
            )
            form.addRow("Text color:", self.text_color)

        if component.kind == "image":
            image_row = QHBoxLayout()
            self.image_path = QLineEdit(self.data.get("path", ""))
            browse_image = QPushButton("Browse...")
            browse_image.clicked.connect(self.browse_image)
            image_row.addWidget(self.image_path)
            image_row.addWidget(browse_image)
            form.addRow("Image:", image_row)

        if component.kind == "arrow":
            self.stroke_color = self.create_color_button(
                self.data.get("stroke_color", "#263b58")
            )
            form.addRow("Arrow color:", self.stroke_color)
            self.line_width = self.create_number(
                float(self.data.get("line_width", 1.5)), 0.1, 20
            )
            form.addRow("Arrow line width:", self.line_width)

        if component.kind in (
            "text",
            "image",
            "rectangle",
            "ellipse",
            "text_field",
            "checkbox",
        ):
            if component.kind not in ("text_field", "checkbox"):
                self.border_enabled = QCheckBox("Show border")
                self.border_enabled.setChecked(
                    bool(
                        self.data.get(
                            "border_enabled",
                            component.kind in ("rectangle", "ellipse"),
                        )
                    )
                )
                form.addRow("Border:", self.border_enabled)
            self.border_color = self.create_color_button(
                self.data.get(
                    "border_color",
                    self.data.get("stroke_color", "#263b58"),
                )
            )
            form.addRow("Border color:", self.border_color)
            self.border_width = self.create_number(
                float(
                    self.data.get(
                        "border_width",
                        self.data.get("line_width", 1.5),
                    )
                ),
                0.1,
                20,
            )
            form.addRow("Border width (pt):", self.border_width)

        if component.kind in (
            "rectangle",
            "ellipse",
            "text_field",
            "checkbox",
        ):
            self.fill_enabled = QCheckBox("Use fill color")
            self.fill_enabled.setChecked(bool(self.data.get("fill_enabled", False)))
            form.addRow("Fill:", self.fill_enabled)
            self.fill_color = self.create_color_button(
                self.data.get("fill_color", "#d7e6f8")
            )
            form.addRow("Fill color:", self.fill_color)

        if component.kind == "arrow":
            self.arrow_angle = self.create_number(
                float(self.data.get("angle", 0)), -180, 180
            )
            form.addRow("Angle (degrees):", self.arrow_angle)

        if component.kind in ("text_field", "checkbox"):
            default_field_name = self.data.get("field_name", "")
            self.field_name = QLineEdit(default_field_name)
            self.field_name.setPlaceholderText("Auto-generate if blank")
            form.addRow("Field name:", self.field_name)

            default_label = self.data.get(
                "field_label",
                "Text field" if component.kind == "text_field" else "Checkbox",
            )
            self.field_label = QLineEdit(default_label)
            form.addRow("Field label:", self.field_label)

        if component.kind == "text_field":
            self.field_value = QLineEdit(self.data.get("field_value", ""))
            form.addRow("Default value:", self.field_value)
            self.font_size = self.create_number(
                float(self.data.get("font_size", 11)), 1, 300
            )
            form.addRow("Font size (pt):", self.font_size)
            self.text_color = self.create_color_button(
                self.data.get("text_color", "#263b58")
            )
            form.addRow("Text color:", self.text_color)

        if component.kind == "checkbox":
            self.checked_by_default = QCheckBox("Checked by default")
            self.checked_by_default.setChecked(
                bool(self.data.get("checked_by_default", False))
            )
            form.addRow("Initial state:", self.checked_by_default)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        save_button = QPushButton("Apply")
        save_button.clicked.connect(self.accept)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

    @staticmethod
    def create_number(value, minimum, maximum):
        spin_box = QDoubleSpinBox()
        spin_box.setRange(minimum, maximum)
        spin_box.setDecimals(1)
        spin_box.setValue(value)
        return spin_box

    def create_color_button(self, color):
        button = QPushButton()
        self.set_color_button(button, QColor(color))
        button.clicked.connect(lambda: self.choose_color(button))
        return button

    @staticmethod
    def set_color_button(button, color):
        button.setProperty("selectedColor", color.name())
        button.setText(color.name())
        button.setStyleSheet(
            f"background-color: {color.name()}; color: "
            f"{'#ffffff' if color.lightness() < 128 else '#000000'};"
        )

    def choose_color(self, button):
        color = QColorDialog.getColor(
            QColor(button.property("selectedColor")),
            self,
            "Choose Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self.set_color_button(button, color)

    def browse_image(self):
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            self.image_path.text(),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if image_path:
            self.image_path.setText(image_path)

    def accept(self):
        self.values.update(
            {
                "position": QPointF(
                    self.position_x.value(),
                    self.position_y.value(),
                ),
                "rect": QRectF(
                    0,
                    0,
                    self.width_input.value(),
                    self.height_input.value(),
                ),
            }
        )

        if self.component.kind == "text":
            self.data.update(
                {
                    "text": self.text.toPlainText(),
                    "font_size": self.font_size.value(),
                    "color": self.text_color.property("selectedColor"),
                }
            )
        elif self.component.kind == "image":
            image_path = self.image_path.text().strip()
            if not image_path or not os.path.isfile(image_path):
                QMessageBox.warning(
                    self,
                    "Image",
                    "Select an existing image file.",
                )
                return
            self.data["path"] = image_path

        if self.component.kind == "arrow":
            self.data.update(
                {
                    "stroke_color": self.stroke_color.property("selectedColor"),
                    "line_width": self.line_width.value(),
                }
            )

        if self.component.kind in (
            "text",
            "image",
            "rectangle",
            "ellipse",
            "text_field",
            "checkbox",
        ):
            self.data.update(
                {
                    "border_color": self.border_color.property("selectedColor"),
                    "border_width": self.border_width.value(),
                    "stroke_color": self.border_color.property("selectedColor"),
                    "line_width": self.border_width.value(),
                }
            )
            if self.component.kind not in ("text_field", "checkbox"):
                self.data["border_enabled"] = self.border_enabled.isChecked()

        if self.component.kind in (
            "rectangle",
            "ellipse",
            "text_field",
            "checkbox",
        ):
            self.data.update(
                {
                    "fill_enabled": self.fill_enabled.isChecked(),
                    "fill_color": self.fill_color.property("selectedColor"),
                }
            )

        if self.component.kind == "arrow":
            self.data["angle"] = self.arrow_angle.value()

        if self.component.kind in ("text_field", "checkbox"):
            self.data.update(
                {
                    "field_name": self.field_name.text().strip(),
                    "field_label": self.field_label.text().strip(),
                }
            )

        if self.component.kind == "text_field":
            self.data.update(
                {
                    "field_value": self.field_value.text(),
                    "font_size": self.font_size.value(),
                    "text_color": self.text_color.property("selectedColor"),
                }
            )

        if self.component.kind == "checkbox":
            self.data["checked_by_default"] = (
                self.checked_by_default.isChecked()
            )

        super().accept()


def _pdf_rgb(color):
    value = QColor(color)
    return (value.redF(), value.greenF(), value.blueF())


class PageComponent(QGraphicsRectItem):
    def __init__(self, kind, rect, data=None):
        super().__init__(QRectF(rect))
        self.kind = kind
        self.data = data or {}
        self._resizing = False
        self._resize_handle_size = 12
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.update_component_style()
        fill_color = QColor(self.data.get("fill_color", "#d7e6f8"))
        if self.data.get("fill_enabled", False):
            self.setBrush(fill_color)
        else:
            self.setBrush(Qt.BrushStyle.NoBrush)
        self.image = (
            QPixmap(self.data["path"])
            if kind == "image"
            else QPixmap()
        )

    def update_component_style(self):
        border_default = self.kind in (
            "rectangle",
            "ellipse",
            "text_field",
            "checkbox",
        )
        border_enabled = self.kind == "arrow" or self.data.get(
            "border_enabled", border_default
        )
        color = self.data.get(
            "stroke_color" if self.kind == "arrow" else "border_color",
            self.data.get("stroke_color", "#263b58"),
        )
        width = self.data.get(
            "line_width" if self.kind == "arrow" else "border_width",
            self.data.get("line_width", 1.5),
        )
        if not border_enabled:
            color = QColor(color)
            color.setAlpha(0)
        self.setPen(QPen(QColor(color), float(width)))

    def paint(self, painter, option, widget=None):
        rect = self.rect()
        painter.setPen(self.pen())
        painter.setBrush(self.brush())

        if self.kind == "ellipse":
            painter.setPen(self.pen())
            painter.setBrush(
                QColor(self.data["fill_color"])
                if self.data.get("fill_enabled", False)
                else Qt.BrushStyle.NoBrush
            )
            painter.drawEllipse(rect)
        elif self.kind == "arrow":
            head_length = min(18, rect.width() * 0.3)
            angle = math.radians(float(self.data.get("angle", 0)))
            direction = QPointF(math.cos(angle), math.sin(angle))
            perpendicular = QPointF(-direction.y(), direction.x())
            start = rect.center() - direction * (rect.width() / 2)
            tip = rect.center() + direction * (rect.width() / 2)
            head_start = tip - direction * head_length
            painter.drawLine(
                start,
                tip,
            )
            painter.drawLine(
                head_start - perpendicular * (head_length * 0.6),
                tip,
            )
            painter.drawLine(
                head_start + perpendicular * (head_length * 0.6),
                tip,
            )
        elif self.kind in ("rectangle", "text_field"):
            painter.setPen(self.pen())
            painter.setBrush(
                QColor(self.data["fill_color"])
                if self.data.get("fill_enabled", False)
                else Qt.BrushStyle.NoBrush
            )
            painter.drawRect(rect)
            if self.kind == "text_field":
                painter.setPen(self.pen().color())
                painter.drawText(
                    rect.adjusted(6, 3, -6, -3),
                    Qt.AlignmentFlag.AlignVCenter
                    | Qt.TextFlag.TextWordWrap,
                    self.data.get("field_label", "Text field"),
                )
        elif self.kind == "checkbox":
            box = QRectF(rect.left(), rect.top(), 24, rect.height())
            painter.setPen(self.pen())
            painter.setBrush(
                QColor(self.data["fill_color"])
                if self.data.get("fill_enabled", False)
                else Qt.BrushStyle.NoBrush
            )
            painter.drawRect(box)
            painter.setPen(QColor("#667085"))
            painter.drawText(
                rect.adjusted(30, 0, 0, 0),
                Qt.AlignmentFlag.AlignVCenter,
                self.data.get("field_label", "Checkbox"),
            )
        elif self.kind == "image":
            if not self.image.isNull():
                painter.drawPixmap(rect.toRect(), self.image)
            else:
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Image unavailable")
            painter.setPen(self.pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
        elif self.kind == "text":
            font = QFont()
            font.setPointSizeF(float(self.data.get("font_size", 14)))
            painter.setFont(font)
            painter.setPen(QColor(self.data.get("color", "#111827")))
            painter.drawText(
                rect.adjusted(6, 4, -6, -4),
                Qt.TextFlag.TextWordWrap,
                self.data.get("text", ""),
            )
            painter.setPen(self.pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        if self.isSelected():
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#1d4ed8"), 1))
            painter.drawRect(
                QRectF(
                    rect.right() - self._resize_handle_size,
                    rect.bottom() - self._resize_handle_size,
                    self._resize_handle_size,
                    self._resize_handle_size,
                )
            )

    def mousePressEvent(self, event):
        handle = QRectF(
            self.rect().right() - self._resize_handle_size,
            self.rect().bottom() - self._resize_handle_size,
            self._resize_handle_size,
            self._resize_handle_size,
        )
        self._resizing = handle.contains(event.pos())
        if self._resizing:
            self.setSelected(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            rect = self.rect()
            self.setRect(
                QRectF(
                    rect.x(),
                    rect.y(),
                    max(24, event.pos().x() - rect.x()),
                    max(20, event.pos().y() - rect.y()),
                )
            )
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        views = self.scene().views()
        parent = views[0].window() if views else None
        dialog = ComponentPropertiesDialog(self, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.setRect(dialog.values["rect"])
            self.setPos(dialog.values["position"])
            self.data = dialog.data
            self.update_component_style()
            if self.data.get("fill_enabled", False):
                self.setBrush(QColor(self.data.get("fill_color", "#d7e6f8")))
            else:
                self.setBrush(Qt.BrushStyle.NoBrush)
            if self.kind == "image":
                self.image = QPixmap(self.data["path"])
            self.update()
        event.accept()

    def to_pdf_rect(self, page):
        scene_rect = self.mapRectToScene(self.rect())
        rect = fitz.Rect(
            scene_rect.left(),
            scene_rect.top(),
            scene_rect.right(),
            scene_rect.bottom(),
        )
        return rect * page.derotation_matrix


class PDFEditorDialog(QDialog):
    def __init__(self, file_path=None, initial_output_path=None, parent=None):
        super().__init__(parent)

        self.file_path = file_path
        self.default_output_path = initial_output_path
        self.document = fitz.open(file_path) if file_path else fitz.open()
        self.components_by_page = [[] for _ in range(len(self.document))]
        self.current_page = 0
        self.available_dialog_width = 1100

        if not len(self.document):
            self.document.new_page(width=595, height=842)
            self.components_by_page.append([])

        self.setWindowTitle("Edit PDF Content")
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available_size = screen.availableGeometry().size()
            max_width = max(1, available_size.width() - 40)
            max_height = max(1, available_size.height() - 80)
            self.available_dialog_width = max_width
            self.setMaximumSize(max_width, max_height)
            self.resize(min(1100, max_width), min(850, max_height))
        else:
            self.resize(1100, 850)

        self.create_ui()
        self.refresh_page_selector()
        self.show_page(0)

    def create_ui(self):
        layout = QVBoxLayout(self)

        page_controls = QVBoxLayout()
        page_navigation = QHBoxLayout()
        self.previous_button = QPushButton("Previous Page")
        self.previous_button.clicked.connect(self.previous_page)
        page_navigation.addWidget(self.previous_button)

        page_navigation.addWidget(QLabel("Page:"))
        self.page_selector = QComboBox()
        self.page_selector.currentIndexChanged.connect(self.show_page)
        page_navigation.addWidget(self.page_selector)

        self.next_button = QPushButton("Next Page")
        self.next_button.clicked.connect(self.next_page)
        page_navigation.addWidget(self.next_button)
        page_navigation.addStretch()
        page_controls.addLayout(page_navigation)

        page_actions = QHBoxLayout()
        add_page_button = QPushButton("Add Page")
        add_page_button.clicked.connect(self.add_page)
        page_actions.addWidget(add_page_button)

        add_image_pages_button = QPushButton("Add Image Pages")
        add_image_pages_button.clicked.connect(self.add_image_pages)
        page_actions.addWidget(add_image_pages_button)

        manage_pages_button = QPushButton("Manage Pages")
        manage_pages_button.clicked.connect(self.manage_pages)
        page_actions.addWidget(manage_pages_button)

        self.delete_page_button = QPushButton("Delete Page")
        self.delete_page_button.clicked.connect(self.delete_current_page)
        page_actions.addWidget(self.delete_page_button)
        page_actions.addStretch()
        page_controls.addLayout(page_actions)
        layout.addLayout(page_controls)

        component_controls = QVBoxLayout()
        first_component_row = QHBoxLayout()
        add_text_button = QPushButton("Add Text")
        add_text_button.clicked.connect(self.add_text)
        first_component_row.addWidget(add_text_button)

        add_image_button = QPushButton("Add Image")
        add_image_button.clicked.connect(self.add_image)
        first_component_row.addWidget(add_image_button)

        add_rectangle_button = QPushButton("Add Rectangle")
        add_rectangle_button.clicked.connect(self.add_rectangle)
        first_component_row.addWidget(add_rectangle_button)

        add_ellipse_button = QPushButton("Add Ellipse")
        add_ellipse_button.clicked.connect(self.add_ellipse)
        first_component_row.addWidget(add_ellipse_button)
        component_controls.addLayout(first_component_row)

        second_component_row = QHBoxLayout()
        add_arrow_button = QPushButton("Add Arrow")
        add_arrow_button.clicked.connect(self.add_arrow)
        second_component_row.addWidget(add_arrow_button)

        add_text_field_button = QPushButton("Add Text Field")
        add_text_field_button.clicked.connect(self.add_text_field)
        second_component_row.addWidget(add_text_field_button)

        add_checkbox_button = QPushButton("Add Checkbox")
        add_checkbox_button.clicked.connect(self.add_checkbox)
        second_component_row.addWidget(add_checkbox_button)

        remove_component_button = QPushButton("Remove Selected")
        remove_component_button.clicked.connect(self.remove_selected_component)
        second_component_row.addWidget(remove_component_button)
        component_controls.addLayout(second_component_row)
        layout.addLayout(component_controls)

        instructions = QLabel(
            "Drag components to move them; drag the lower-right handle to "
            "resize. Double-click any component to edit its properties. Use "
            "the mouse wheel or arrow keys to flip pages."
        )
        instructions.setWordWrap(True)
        instructions.setMaximumWidth(max(1, self.available_dialog_width - 40))
        layout.addWidget(instructions)

        self.page_source_label = QLabel()
        self.page_source_label.setWordWrap(True)
        self.page_source_label.setMaximumWidth(
            max(1, self.available_dialog_width - 40)
        )
        self.page_source_label.hide()
        layout.addWidget(self.page_source_label)

        self.scene = QGraphicsScene(self)
        self.canvas = PDFEditorCanvas(self.scene, self)
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.displayed_page = None
        layout.addWidget(self.canvas, 1)

        bottom_controls = QHBoxLayout()
        bottom_controls.addStretch()
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        bottom_controls.addWidget(cancel_button)

        save_button = QPushButton("Save PDF")
        save_button.clicked.connect(self.save_pdf)
        bottom_controls.addWidget(save_button)
        layout.addLayout(bottom_controls)

    def refresh_page_selector(self, selected_page=None):
        self.page_selector.blockSignals(True)
        self.page_selector.clear()
        self.page_selector.addItems(
            [f"{index + 1}" for index in range(len(self.document))]
        )
        if selected_page is not None:
            self.page_selector.setCurrentIndex(selected_page)
        self.page_selector.blockSignals(False)

    def manage_pages(self):
        dialog = EditorPageManagerDialog(self, self)
        dialog.exec()

    def show_page(self, page_index):
        if not 0 <= page_index < len(self.document):
            return

        self.clear_displayed_page()

        page = self.document.load_page(page_index)
        pixmap_data = page.get_pixmap(alpha=False)
        image = QPixmap.fromImage(
            QImage(
                pixmap_data.samples,
                pixmap_data.width,
                pixmap_data.height,
                pixmap_data.stride,
                QImage.Format.Format_RGB888,
            ).copy()
        )

        self.current_page = page_index
        self.scene.setSceneRect(0, 0, pixmap_data.width, pixmap_data.height)
        self.background_item = self.scene.addPixmap(image)
        self.background_item.setZValue(-100)
        for component in self.components_by_page[page_index]:
            self.scene.addItem(component)
        self.canvas.fitInView(
            self.scene.sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self.displayed_page = page_index
        self.previous_button.setEnabled(page_index > 0)
        self.next_button.setEnabled(page_index < len(self.document) - 1)
        self.delete_page_button.setEnabled(len(self.document) > 1)

        page_image = next(
            (
                component
                for component in self.components_by_page[page_index]
                if component.data.get("page_image", False)
            ),
            None,
        )
        if page_image is None:
            self.page_source_label.clear()
            self.page_source_label.hide()
        else:
            image_path = page_image.data["path"]
            self.page_source_label.setText(
                f"Image page: {os.path.basename(image_path)}"
            )
            self.page_source_label.setToolTip(image_path)
            self.page_source_label.show()

    def clear_displayed_page(self):
        old_background = getattr(self, "background_item", None)
        if old_background is not None:
            self.scene.removeItem(old_background)
            self.background_item = None
        if (
            self.displayed_page is not None
            and self.displayed_page < len(self.components_by_page)
        ):
            for component in self.components_by_page[self.displayed_page]:
                if component.scene() is self.scene:
                    self.scene.removeItem(component)
        self.displayed_page = None

    def add_page(self):
        page = self.document.load_page(self.current_page)
        insert_at = self.current_page + 1
        self.document.new_page(
            pno=insert_at,
            width=page.rect.width,
            height=page.rect.height,
        )
        self.components_by_page.insert(insert_at, [])
        self.refresh_page_selector(insert_at)
        self.show_page(insert_at)

    def delete_current_page(self):
        if len(self.document) <= 1:
            self.delete_page_button.setEnabled(False)
            return

        page_number = self.current_page + 1
        answer = QMessageBox.question(
            self,
            "Delete Page",
            f"Delete page {page_number}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.delete_pages([self.current_page])

    def delete_pages(self, page_indices, selected_page=None):
        page_indices = sorted(set(page_indices))
        if not page_indices or len(page_indices) >= len(self.document):
            return

        self.clear_displayed_page()
        for page_index in reversed(page_indices):
            self.document.delete_page(page_index)
            del self.components_by_page[page_index]

        if selected_page is None:
            selected_page = min(page_indices[0], len(self.document) - 1)
        selected_page = min(max(selected_page, 0), len(self.document) - 1)
        self.refresh_page_selector(selected_page)
        self.show_page(selected_page)

    def reorder_pages(self, page_order):
        if sorted(page_order) != list(range(len(self.document))):
            raise ValueError("Page order must include each page exactly once.")

        old_current_page = self.current_page
        self.clear_displayed_page()
        current_order = list(range(len(self.document)))
        for target_index, page_id in enumerate(page_order):
            current_index = current_order.index(page_id)
            if current_index != target_index:
                self.document.move_page(current_index, target_index)
                current_order.insert(target_index, current_order.pop(current_index))

        self.components_by_page = [
            self.components_by_page[page_id] for page_id in page_order
        ]
        selected_page = page_order.index(old_current_page)
        self.refresh_page_selector(selected_page)
        self.show_page(selected_page)

    def add_image_pages(self):
        image_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images to Add as Pages",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not image_paths:
            return

        image_pages = []
        invalid_images = []
        for image_path in image_paths:
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                invalid_images.append(image_path)
                continue

            page_width = pixmap.width()
            page_height = pixmap.height()
            image_pages.append((image_path, page_width, page_height))

        if invalid_images:
            QMessageBox.warning(
                self,
                "Invalid Images",
                "Could not load these image(s):\n"
                + "\n".join(invalid_images),
            )
        if not image_pages:
            return

        insert_at = self.current_page + 1
        for offset, (image_path, page_width, page_height) in enumerate(image_pages):
            page_index = insert_at + offset
            self.document.new_page(
                pno=page_index,
                width=page_width,
                height=page_height,
            )
            self.components_by_page.insert(page_index, [])
            image_component = PageComponent(
                "image",
                QRectF(0, 0, page_width, page_height),
                {
                    "path": image_path,
                    "page_image": True,
                    "border_enabled": False,
                },
            )
            self.components_by_page[page_index].append(image_component)

        last_added_page = insert_at + len(image_pages) - 1
        self.refresh_page_selector(last_added_page)
        self.show_page(last_added_page)

    def previous_page(self):
        if self.current_page > 0:
            self.page_selector.setCurrentIndex(self.current_page - 1)

    def next_page(self):
        if self.current_page + 1 < len(self.document):
            self.page_selector.setCurrentIndex(self.current_page + 1)

    def add_component(self, kind, rect, data=None):
        component = PageComponent(kind, rect, data)
        offset = 20 * len(self.components_by_page[self.current_page])
        component.setPos(40 + offset, 40 + offset)
        self.scene.addItem(component)
        self.components_by_page[self.current_page].append(component)
        component.setSelected(True)
        return component

    def add_text(self):
        text, accepted = QInputDialog.getMultiLineText(
            self,
            "Add Text",
            "Text:",
            "Double-click to edit",
        )
        if accepted and text:
            self.add_component(
                "text",
                QRectF(0, 0, 220, 90),
                {"text": text, "font_size": 14},
            )

    def add_image(self):
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if image_path:
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                QMessageBox.warning(
                    self,
                    "Image",
                    "The selected image could not be loaded.",
                )
                return
            self.add_component(
                "image",
                QRectF(0, 0, min(pixmap.width(), 240), min(pixmap.height(), 180)),
                {"path": image_path},
            )

    def add_rectangle(self):
        self.add_component("rectangle", QRectF(0, 0, 180, 100))

    def add_ellipse(self):
        self.add_component("ellipse", QRectF(0, 0, 150, 100))

    def add_arrow(self):
        self.add_component("arrow", QRectF(0, 0, 180, 60))

    def add_text_field(self):
        self.add_component("text_field", QRectF(0, 0, 220, 34))

    def add_checkbox(self):
        self.add_component("checkbox", QRectF(0, 0, 120, 24))

    def remove_selected_component(self):
        for item in self.scene.selectedItems():
            if isinstance(item, PageComponent):
                self.scene.removeItem(item)
                self.components_by_page[self.current_page].remove(item)

    def save_pdf(self):
        default_path = self.default_output_path
        if not default_path and self.file_path:
            name, extension = os.path.splitext(self.file_path)
            default_path = f"{name}_edited{extension}"

        if self.default_output_path and not self.file_path:
            output_path = self.default_output_path
        else:
            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save PDF",
                default_path or "",
                "PDF Files (*.pdf)",
            )
        if not output_path:
            return

        if not output_path.lower().endswith(".pdf"):
            output_path += ".pdf"

        if self.file_path and os.path.normcase(os.path.abspath(output_path)) == (
            os.path.normcase(os.path.abspath(self.file_path))
        ):
            QMessageBox.warning(
                self,
                "Choose Another File",
                "Save edits to a different file so the original remains unchanged.",
            )
            return

        try:
            output_folder = os.path.dirname(os.path.abspath(output_path))
            file_descriptor, temporary_path = tempfile.mkstemp(
                suffix=".pdf",
                dir=output_folder,
            )
            os.close(file_descriptor)
            os.remove(temporary_path)
            output_document = None
            try:
                output_document = fitz.open(
                    stream=self.document.tobytes(),
                    filetype="pdf",
                )
                self.apply_components(output_document)
                output_document.save(
                    temporary_path,
                    garbage=4,
                    deflate=True,
                    deflate_images=False,
                    clean=True,
                )
                os.replace(temporary_path, output_path)
            except Exception:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)
                raise
            finally:
                if output_document is not None:
                    output_document.close()
        except Exception as error:
            QMessageBox.critical(
                self,
                "Save PDF Error",
                f"Could not save the PDF:\n\n{error}",
            )
            return

        self.output_path = output_path
        self.accept()

    def apply_components(self, document):
        for page_index, components in enumerate(self.components_by_page):
            page = document.load_page(page_index)
            names = {
                widget.field_name
                for widget in page.widgets() or []
                if widget.field_name
            }
            field_index = 1
            for component in components:
                rect = component.to_pdf_rect(page)
                if component.kind == "text":
                    remaining_space = page.insert_textbox(
                        rect,
                        component.data.get("text", ""),
                        fontsize=float(component.data.get("font_size", 14)),
                        fontname="helv",
                        color=_pdf_rgb(component.data.get("color", "#111827")),
                    )
                    if remaining_space < 0:
                        raise ValueError(
                            f"Text on page {page_index + 1} does not fit. "
                            "Resize the text box or shorten the text."
                        )
                    if component.data.get("border_enabled", False):
                        page.draw_rect(
                            rect,
                            color=_pdf_rgb(
                                component.data.get("border_color", "#263b58")
                            ),
                            width=float(
                                component.data.get("border_width", 1.5)
                            ),
                        )
                elif component.kind == "image":
                    image_rect = (
                        page.rect
                        if component.data.get("page_image", False)
                        else rect
                    )
                    page.insert_image(
                        image_rect,
                        filename=component.data["path"],
                        keep_proportion=not component.data.get(
                            "page_image", False
                        ),
                    )
                    if component.data.get("border_enabled", False):
                        page.draw_rect(
                            rect,
                            color=_pdf_rgb(
                                component.data.get("border_color", "#263b58")
                            ),
                            width=float(
                                component.data.get("border_width", 1.5)
                            ),
                        )
                elif component.kind == "rectangle":
                    page.draw_rect(
                        rect,
                        color=(
                            _pdf_rgb(
                                component.data.get("border_color", "#263b58")
                            )
                            if component.data.get("border_enabled", True)
                            else None
                        ),
                        fill=(
                            _pdf_rgb(component.data["fill_color"])
                            if component.data.get("fill_enabled", False)
                            else None
                        ),
                        width=float(component.data.get("border_width", 1.5)),
                    )
                elif component.kind == "ellipse":
                    page.draw_oval(
                        rect,
                        color=(
                            _pdf_rgb(
                                component.data.get("border_color", "#263b58")
                            )
                            if component.data.get("border_enabled", True)
                            else None
                        ),
                        fill=(
                            _pdf_rgb(component.data["fill_color"])
                            if component.data.get("fill_enabled", False)
                            else None
                        ),
                        width=float(component.data.get("border_width", 1.5)),
                    )
                elif component.kind == "arrow":
                    center = fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
                    angle = math.radians(float(component.data.get("angle", 0)))
                    direction = fitz.Point(math.cos(angle), math.sin(angle))
                    head_length = min(18, rect.width * 0.3)
                    start = center - direction * (rect.width / 2)
                    tip = center + direction * (rect.width / 2)
                    head_start = tip - direction * head_length
                    perpendicular = fitz.Point(-direction.y, direction.x)
                    line_color = _pdf_rgb(
                        component.data.get("stroke_color", "#263b58")
                    )
                    line_width = float(component.data.get("line_width", 1.5))
                    page.draw_line(
                        start,
                        tip,
                        color=line_color,
                        width=line_width,
                    )
                    page.draw_line(
                        head_start - perpendicular * (head_length * 0.6),
                        tip,
                        color=line_color,
                        width=line_width,
                    )
                    page.draw_line(
                        head_start + perpendicular * (head_length * 0.6),
                        tip,
                        color=line_color,
                        width=line_width,
                    )
                elif component.kind in ("text_field", "checkbox"):
                    widget = fitz.Widget()
                    widget.field_type = (
                        fitz.PDF_WIDGET_TYPE_TEXT
                        if component.kind == "text_field"
                        else fitz.PDF_WIDGET_TYPE_CHECKBOX
                    )
                    requested_name = component.data.get("field_name", "").strip()
                    if requested_name:
                        if requested_name in names:
                            raise ValueError(
                                f"Form field name '{requested_name}' is already "
                                f"used on page {page_index + 1}."
                            )
                        field_name = requested_name
                        names.add(field_name)
                    else:
                        while True:
                            field_name = (
                                f"pdfstudio_p{page_index + 1}_{field_index}"
                            )
                            field_index += 1
                            if field_name not in names:
                                names.add(field_name)
                                break
                    widget.field_name = field_name
                    widget.field_label = component.data.get(
                        "field_label",
                        "Text field"
                        if component.kind == "text_field"
                        else "Checkbox",
                    )
                    if component.kind == "checkbox":
                        rect.x1 = min(rect.x1, rect.x0 + 24)
                    widget.rect = rect
                    widget.border_width = (
                        float(component.data.get("border_width", 1.5))
                        if component.data.get("border_enabled", True)
                        else 0
                    )
                    widget.border_color = (
                        _pdf_rgb(component.data.get("border_color", "#263b58"))
                        if component.data.get("border_enabled", True)
                        else None
                    )
                    widget.fill_color = (
                        _pdf_rgb(component.data["fill_color"])
                        if component.data.get("fill_enabled", False)
                        else None
                    )
                    if component.kind == "text_field":
                        widget.field_value = component.data.get("field_value", "")
                        widget.text_fontsize = float(
                            component.data.get("font_size", 11)
                        )
                        widget.text_color = _pdf_rgb(
                            component.data.get("text_color", "#263b58")
                        )
                    else:
                        widget.field_value = (
                            "Yes"
                            if component.data.get("checked_by_default", False)
                            else "Off"
                        )
                    page.add_widget(widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "scene") and self.scene.sceneRect().isValid():
            self.canvas.fitInView(
                self.scene.sceneRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )

    def done(self, result):
        if self.document:
            self.document.close()
            self.document = None
        super().done(result)
