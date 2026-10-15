import sys
import os
import random
import shutil
import ctypes
import json
import subprocess
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import (
    Qt, QTimer, QEvent, QAbstractNativeEventFilter, Signal, QProcess, QPoint,
    QObject, QSettings, QRectF
)
from PySide6.QtGui import QAction, QKeySequence, QColor, QPainter, QPen, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QFileDialog, QMessageBox, QStyle,
    QFrame, QSizePolicy, QStyleOptionSlider, QProgressBar, QListWidget,
    QListWidgetItem, QAbstractItemView, QComboBox
)

try:
    import vlc
except ImportError:
    vlc = None


VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".mpeg",
    ".mpg", ".m4v", ".3gp", ".ts", ".mts", ".m2ts", ".vob", ".ogv",
    ".divx", ".asf", ".rm", ".rmvb",
}
PLAYBACK_MODES = {
    "Play next": "next",
    "Play previous": "previous",
    "Play once": "repeat_one",
    "Repeat once": "repeat_once",
    "Repeat all": "repeat_all",
    "Random in folder": "random_folder",
}

MEDIA_FILTER = (
    "Media files (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.mpeg "
    "*.mpg *.m4v *.3gp *.ts *.mts *.m2ts *.vob *.ogv *.divx *.asf *.rm *.rmvb "
    "*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.opus *.wma *.aiff *.ape *.mid *.midi);;"
    "All files (*.*)"
)

TRIM_EXPORT_FILTERS = {
    "MP4 video (*.mp4)": "mp4",
    "Matroska video (*.mkv)": "mkv",
    "QuickTime video (*.mov)": "mov",
    "WebM video (*.webm)": "webm",
    "AVI video (*.avi)": "avi",
    "Animated GIF (*.gif)": "gif",
}
JOIN_EXPORT_FILTERS = {
    label: extension
    for label, extension in TRIM_EXPORT_FILTERS.items()
    if extension != "gif"
}

WM_LBUTTONDBLCLK = 0x0203
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEWHEEL = 0x020A
MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002


class VideoDoubleClickFilter(QAbstractNativeEventFilter):
    def __init__(self, player_window):
        super().__init__()
        self.player_window = player_window

    def nativeEventFilter(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return False, 0

        native_message = ctypes.cast(
            ctypes.c_void_p(int(message)), ctypes.POINTER(wintypes.MSG)
        ).contents
        if native_message.hWnd != self.player_window.active_video_hwnd:
            return False, 0

        if native_message.message == WM_LBUTTONDBLCLK:
            QTimer.singleShot(0, self.player_window.toggle_fullscreen)
            return True, 0
        if native_message.hWnd == self.player_window.trim_video_hwnd:
            return False, 0
        if native_message.message == WM_MOUSEWHEEL:
            delta = ctypes.c_short((int(native_message.wParam) >> 16) & 0xFFFF).value
            screen_x, screen_y = native_message.pt.x, native_message.pt.y
            QTimer.singleShot(
                0,
                lambda: self.player_window.adjust_zoom_at(
                    10 if delta > 0 else -10,
                    screen_x,
                    screen_y,
                ),
            )
            return True, 0
        if native_message.message in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
            if self.player_window.begin_video_pan(
                native_message.pt.x, native_message.pt.y
            ):
                ctypes.windll.user32.SetCapture(
                    wintypes.HWND(self.player_window.video_hwnd)
                )
                return True, 0
        if (
            native_message.message == WM_MOUSEMOVE
            and int(native_message.wParam) & (MK_LBUTTON | MK_RBUTTON)
            and self.player_window.video_pan_origin is not None
        ):
            x, y = native_message.pt.x, native_message.pt.y
            QTimer.singleShot(
                0, lambda: self.player_window.update_video_pan(x, y)
            )
            return True, 0
        if native_message.message in (WM_LBUTTONUP, WM_RBUTTONUP):
            if self.player_window.end_video_pan():
                ctypes.windll.user32.ReleaseCapture()
                return True, 0
        return False, 0


class SeekSlider(QSlider):
    clicked = Signal(int)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )
        click_position = event.position().toPoint()
        jump_to_click = not handle_rect.contains(click_position)

        super().mousePressEvent(event)

        if jump_to_click:
            groove_rect = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider,
                option,
                QStyle.SubControl.SC_SliderGroove,
                self,
            )
            slider_min = groove_rect.x()
            slider_max = groove_rect.right() - handle_rect.width() + 1
            slider_span = max(1, slider_max - slider_min)
            position = click_position.x() - slider_min - handle_rect.width() // 2
            value = QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                position,
                slider_span,
                option.upsideDown,
            )
            self.setSliderPosition(value)
            self.setValue(value)
            self.clicked.emit(value)


class PlayerSignals(QObject):
    end_reached = Signal()


class SingleInstanceServer(QObject):
    request_received = Signal(str)
    request_error = Signal(str)

    def __init__(self, server_name, parent=None):
        super().__init__(parent)
        self.server_name = server_name
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept_connections)
        self.buffers = {}

    def listen(self):
        return self.server.listen(self.server_name)

    def _accept_connections(self):
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            self.buffers[connection] = bytearray()
            connection.readyRead.connect(
                lambda client=connection: self._read_connection(client)
            )
            connection.disconnected.connect(
                lambda client=connection: self._close_connection(client)
            )
            self._read_connection(connection)

    def _read_connection(self, connection):
        self.buffers[connection].extend(connection.readAll().data())
        while b"\n" in self.buffers[connection]:
            line, _, remaining = self.buffers[connection].partition(b"\n")
            self.buffers[connection] = bytearray(remaining)
            try:
                requested_file = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.request_error.emit(f"Invalid open request: {exc}")
                connection.disconnectFromServer()
                return
            if not isinstance(requested_file, str):
                self.request_error.emit("Invalid open request: expected a file path.")
                connection.disconnectFromServer()
                return
            self.request_received.emit(requested_file)
            connection.disconnectFromServer()
            return

    def _close_connection(self, connection):
        self.buffers.pop(connection, None)
        connection.deleteLater()


def forward_open_request(server_name, filename):
    connection = QLocalSocket()
    connection.connectToServer(server_name)
    if not connection.waitForConnected(300):
        return False
    message = json.dumps(filename or "").encode("utf-8") + b"\n"
    if connection.write(message) != len(message):
        raise RuntimeError(f"Could not send media open request: {connection.errorString()}")
    connection.flush()
    connection.disconnectFromServer()
    if (
        connection.state() != QLocalSocket.LocalSocketState.UnconnectedState
        and not connection.waitForDisconnected(5000)
    ):
        raise RuntimeError(f"Could not finish media open request: {connection.errorString()}")
    return True


class TrimTimeline(QWidget):
    seek_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration_ms = 0
        self.current_ms = 0
        self.start_ms = None
        self.end_ms = None
        self.setMinimumHeight(28)
        self.setMaximumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click or drag to seek; trim markers are shown here")

    def set_positions(self, duration_ms, current_ms, start_ms, end_ms):
        self.duration_ms = max(0, duration_ms)
        self.current_ms = max(0, current_ms)
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.update()

    def _seek_at_x(self, x):
        if self.duration_ms <= 0:
            return
        track_left = 10
        track_width = max(1, self.width() - 20)
        ratio = max(0.0, min(1.0, (x - track_left) / track_width))
        self.seek_requested.emit(round(ratio * self.duration_ms))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._seek_at_x(event.position().x())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._seek_at_x(event.position().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        left = 10
        right = max(left + 1, self.width() - 10)
        center_y = self.height() // 2
        track = QRectF(left, center_y - 4, right - left, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#454b57"))
        painter.drawRoundedRect(track, 4, 4)

        if self.duration_ms > 0:
            def marker_x(position):
                ratio = max(0.0, min(1.0, position / self.duration_ms))
                return round(left + ratio * (right - left))

            if self.start_ms is not None and self.end_ms is not None:
                selection = QRectF(
                    marker_x(self.start_ms),
                    center_y - 4,
                    max(0, marker_x(self.end_ms) - marker_x(self.start_ms)),
                    8,
                )
                painter.setBrush(QColor("#4f9cf9"))
                painter.drawRoundedRect(selection, 3, 3)

            for position, color in (
                (self.start_ms, QColor("#66dd88")),
                (self.end_ms, QColor("#ff6b6b")),
            ):
                if position is not None:
                    x = marker_x(position)
                    painter.setPen(QPen(color, 3))
                    painter.drawLine(x, center_y - 12, x, center_y + 12)

            playhead_x = marker_x(self.current_ms)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawLine(playhead_x, center_y - 8, playhead_x, center_y + 8)


class PlaylistWindow(QWidget):
    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Playlist")
        self.resize(440, 320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        self.playlist_widget = QListWidget()
        self.playlist_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        layout.addWidget(self.playlist_widget, 1)

        file_buttons = QHBoxLayout()
        file_buttons.setSpacing(5)
        self.add_button = QPushButton("Add Files")
        self.remove_button = QPushButton("Remove Selected")
        file_buttons.addWidget(self.add_button)
        file_buttons.addWidget(self.remove_button)
        layout.addLayout(file_buttons)

        playlist_buttons = QHBoxLayout()
        playlist_buttons.setSpacing(5)
        self.load_button = QPushButton("Load Playlist")
        self.save_button = QPushButton("Save Playlist")
        playlist_buttons.addWidget(self.load_button)
        playlist_buttons.addWidget(self.save_button)
        layout.addLayout(playlist_buttons)

        navigation = QHBoxLayout()
        navigation.setSpacing(5)
        self.previous_button = QPushButton("Previous Track")
        self.next_button = QPushButton("Next Track")
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        layout.addLayout(navigation)
        self.setStyleSheet("""
            QPushButton {
                min-height: 24px;
                padding: 3px 7px;
                border-radius: 4px;
            }
            QListWidget {
                padding: 2px;
            }
        """)

    def closeEvent(self, event):
        self.hide()
        event.accept()


class TrimWindow(QWidget):
    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Trim Media")
        self.resize(640, 470)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.video_area = QFrame()
        self.video_area.setObjectName("trimVideoArea")
        self.video_area.setMinimumHeight(200)
        self.video_area.setStyleSheet("QFrame#trimVideoArea { background: #000000; }")
        video_layout = QVBoxLayout(self.video_area)
        video_layout.setContentsMargins(0, 0, 0, 0)
        self.video_surface = QWidget(self.video_area)
        self.video_surface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video_surface.setAttribute(
            Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True
        )
        self.video_surface.setStyleSheet("background-color: #000000;")
        video_layout.addWidget(self.video_surface)
        layout.addWidget(self.video_area, 1)

        self.timeline = TrimTimeline(self)
        layout.addWidget(self.timeline)
        playback_controls = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setEnabled(False)
        playback_controls.addWidget(self.play_button)
        playback_controls.addStretch(1)
        layout.addLayout(playback_controls)
        timing_row = QHBoxLayout()
        timing_row.setSpacing(12)
        self.start_time_label = QLabel("START\nNot set")
        self.end_time_label = QLabel("END\nNot set")
        self.duration_label = QLabel("SELECTED DURATION\nNot set")
        self.marker_label = self.start_time_label
        for label in (
            self.start_time_label,
            self.end_time_label,
            self.duration_label,
        ):
            label.setMinimumWidth(150)
            label.setStyleSheet(
                "QLabel { background: #24272e; padding: 8px; "
                "font-size: 14px; font-weight: bold; }"
            )
            timing_row.addWidget(label, 1)
        layout.addLayout(timing_row)
        layout.addWidget(QLabel("Green: trim start    Red: trim end    White: playback position"))

        trim_controls = QHBoxLayout()
        self.start_button = QPushButton("Set Trim Start")
        self.start_button.setEnabled(False)
        trim_controls.addWidget(self.start_button)
        self.end_button = QPushButton("Set Trim End")
        self.end_button.setEnabled(False)
        trim_controls.addWidget(self.end_button)
        self.save_button = QPushButton("Save Trimmed As...")
        self.save_button.setEnabled(False)
        trim_controls.addWidget(self.save_button)
        layout.addLayout(trim_controls)

        status_row = QHBoxLayout()
        self.status = QLabel("Open media, then set trim start and end.")
        status_row.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setFixedWidth(120)
        self.progress.hide()
        status_row.addWidget(self.progress)
        layout.addLayout(status_row)

    def closeEvent(self, event):
        self.parent().restore_main_video_output()
        self.hide()
        event.accept()


def format_time(milliseconds):
    if milliseconds is None or milliseconds < 0:
        milliseconds = 0
    seconds = int(milliseconds // 1000)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def format_precise_time(milliseconds):
    if milliseconds is None or milliseconds < 0:
        return "Not set"
    total_milliseconds = int(milliseconds)
    whole_seconds, fraction = divmod(total_milliseconds, 1000)
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{fraction:03d}"


class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python Video Player")
        self.resize(1100, 700)
        self.setMinimumSize(700, 450)

        self.instance = None
        self.player = None
        self.current_file = ""
        self.settings = QSettings()
        recent_files = self.settings.value("recentFiles", [])
        if isinstance(recent_files, str):
            recent_files = [recent_files]
        self.recent_files = [
            path for path in recent_files
            if isinstance(path, str) and path
        ][:10]
        self.playlist_paths = []
        self.playlist_index = -1
        self.playlist_window = None
        self.is_seeking = False
        self.was_playing_before_seek = False
        self.playback_ended = False
        self.pending_resume_position_ms = None
        self.is_fullscreen = False
        self.trim_start_ms = None
        self.trim_end_ms = None
        self.trim_error_output = bytearray()
        self.export_progress_buffer = bytearray()
        self.export_total_ms = 0
        self.export_kind = None
        self.zoom_factor = 1.0
        self.video_pan = (0, 0)
        self.video_pan_origin = None
        self.video_pan_start = (0, 0)

        self._build_ui()
        self._build_menu()
        self._build_shortcuts()
        self.player_signals = PlayerSignals(self)
        self.player_signals.end_reached.connect(
            self._handle_playback_end,
            Qt.ConnectionType.QueuedConnection,
        )
        self.trim_process = QProcess(self)
        self.trim_process.readyReadStandardOutput.connect(self._read_export_progress)
        self.trim_process.readyReadStandardError.connect(self._read_trim_stderr)
        self.trim_process.finished.connect(self._trim_finished)
        self.trim_process.errorOccurred.connect(self._trim_process_error)
        self.video_hwnd = int(self.video_surface.winId())
        self.trim_video_hwnd = int(self.trim_window.video_surface.winId())
        self.active_video_hwnd = self.video_hwnd
        self.native_double_click_filter = VideoDoubleClickFilter(self)
        QApplication.instance().installNativeEventFilter(self.native_double_click_filter)
        QApplication.instance().installEventFilter(self)
        self._init_vlc()

        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.update_playback_ui)
        self.timer.start()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video_area = QFrame()
        self.video_area.setObjectName("videoArea")
        self.video_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_area.setMinimumHeight(250)
        self.video_surface = QWidget(self.video_area)
        self.video_surface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video_surface.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.video_surface.setStyleSheet("background-color: #000000;")
        self.video_area.installEventFilter(self)
        layout.addWidget(self.video_area, 1)

        self.controls_panel = QWidget()
        controls_layout = QVBoxLayout(self.controls_panel)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(0)

        self.now_playing = QLabel("Open a video to begin")
        self.now_playing.setObjectName("nowPlaying")
        self.now_playing.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls_layout.addWidget(self.now_playing)

        self.position_slider = SeekSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.position_slider.setSingleStep(1)
        self.position_slider.setPageStep(10)
        self.position_slider.setToolTip(
            "Click or drag to seek; use Left/Right arrows to seek"
        )
        self.position_slider.sliderPressed.connect(self._seek_started)
        self.position_slider.sliderReleased.connect(self._seek_finished)
        self.position_slider.sliderMoved.connect(self._seek_preview)
        self.position_slider.clicked.connect(self._seek_to_position)
        controls_layout.addWidget(self.position_slider)

        time_row = QHBoxLayout()
        time_row.setContentsMargins(12, 0, 12, 0)
        self.current_time = QLabel("00:00")
        self.total_time = QLabel("00:00")
        time_row.addWidget(self.current_time)
        time_row.addStretch(1)
        time_row.addWidget(self.total_time)
        controls_layout.addLayout(time_row)

        playback_mode_row = QHBoxLayout()
        playback_mode_row.setContentsMargins(12, 0, 12, 4)
        playback_mode_row.addWidget(QLabel("Playback mode"))
        self.playback_mode = QComboBox()
        for label, mode in PLAYBACK_MODES.items():
            self.playback_mode.addItem(label, mode)
        self.playback_mode.setToolTip(
            "Choose what plays when the current video ends."
        )
        self.playback_mode.setMinimumWidth(180)
        playback_mode_row.addWidget(self.playback_mode)
        playback_mode_row.addStretch(1)
        controls_layout.addLayout(playback_mode_row)

        self.playlist_window = PlaylistWindow(self)
        self.playlist_widget = self.playlist_window.playlist_widget
        self.playlist_widget.itemDoubleClicked.connect(self._play_playlist_item)
        self.playlist_window.add_button.clicked.connect(self.add_playlist_files)
        self.playlist_window.remove_button.clicked.connect(self.remove_playlist_files)
        self.playlist_window.load_button.clicked.connect(self.load_playlist)
        self.playlist_window.save_button.clicked.connect(self.save_playlist)
        self.playlist_window.previous_button.clicked.connect(self.play_previous_track)
        self.playlist_window.next_button.clicked.connect(self.play_next_track)

        self.trim_window = TrimWindow(self)
        self.trim_window.timeline.seek_requested.connect(self._seek_trim_timeline)
        self.trim_window.play_button.clicked.connect(self.toggle_play_pause)
        self.trim_play_button = self.trim_window.play_button
        self.trim_start_button = self.trim_window.start_button
        self.trim_end_button = self.trim_window.end_button
        self.trim_save_button = self.trim_window.save_button
        self.trim_status = self.trim_window.status
        self.export_progress = self.trim_window.progress
        self.trim_start_button.clicked.connect(self.set_trim_start)
        self.trim_end_button.clicked.connect(self.set_trim_end)
        self.trim_save_button.clicked.connect(self.save_trimmed_media)

        zoom_controls = QHBoxLayout()
        zoom_controls.setContentsMargins(12, 4, 12, 4)
        zoom_controls.addWidget(QLabel("Zoom"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(100, 300)
        self.zoom_slider.setSingleStep(10)
        self.zoom_slider.setPageStep(25)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setMaximumWidth(240)
        self.zoom_slider.valueChanged.connect(self.set_zoom)
        zoom_controls.addWidget(self.zoom_slider)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(48)
        zoom_controls.addWidget(self.zoom_label)
        zoom_controls.addWidget(QLabel("Wheel to zoom; drag to move"))
        self.reset_view_button = QPushButton("Reset View")
        self.reset_view_button.clicked.connect(self.reset_video_view)
        zoom_controls.addWidget(self.reset_view_button)
        zoom_controls.addStretch(1)
        controls_layout.addLayout(zoom_controls)

        controls = QHBoxLayout()
        controls.setContentsMargins(12, 10, 12, 12)
        controls.setSpacing(8)

        self.open_button = QPushButton("Open")
        self.open_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.open_button.clicked.connect(self.open_file)
        controls.addWidget(self.open_button)

        self.playlist_button = QPushButton("Playlist")
        self.playlist_button.clicked.connect(self.show_playlist_window)
        controls.addWidget(self.playlist_button)

        self.trim_button = QPushButton("Trim")
        self.trim_button.clicked.connect(self.show_trim_window)
        controls.addWidget(self.trim_button)

        self.join_button = QPushButton("Join Videos...")
        self.join_button.clicked.connect(self.join_videos)
        controls.addWidget(self.join_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.stop_button)

        self.previous_track_button = QPushButton("Previous")
        self.previous_track_button.setToolTip("Play the previous track")
        self.previous_track_button.clicked.connect(self.play_previous_track)
        controls.addWidget(self.previous_track_button)

        self.play_button = QPushButton("Play")
        self.play_button.setMinimumWidth(90)
        self.play_button.clicked.connect(self.toggle_play_pause)
        controls.addWidget(self.play_button)

        self.next_track_button = QPushButton("Next")
        self.next_track_button.setToolTip("Play the next track")
        self.next_track_button.clicked.connect(self.play_next_track)
        controls.addWidget(self.next_track_button)

        self.mute_button = QPushButton("Mute")
        self.mute_button.clicked.connect(self.toggle_mute)
        controls.addWidget(self.mute_button)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 200)
        self.volume_slider.setValue(80)
        self.volume_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.volume_slider.setSingleStep(1)
        self.volume_slider.setMaximumWidth(140)
        self.volume_slider.setToolTip(
            "Volume: 100% is normal; values above 100% boost the audio; "
            "use Up/Down arrows to adjust"
        )
        self.volume_slider.valueChanged.connect(self.set_volume)
        controls.addWidget(QLabel("Volume"))
        controls.addWidget(self.volume_slider)
        self.volume_value_label = QLabel(f"{self.volume_slider.value()}%")
        self.volume_value_label.setMinimumWidth(36)
        self.volume_value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        controls.addWidget(self.volume_value_label)
        self.reset_volume_button = QPushButton("Reset")
        self.reset_volume_button.setToolTip("Reset volume to 80%")
        self.reset_volume_button.clicked.connect(self.reset_volume)
        controls.addWidget(self.reset_volume_button)

        controls.addStretch(1)
        self.fullscreen_button = QPushButton("Full Screen")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        controls.addWidget(self.fullscreen_button)
        controls_layout.addLayout(controls)
        layout.addWidget(self.controls_panel)

        self.setStyleSheet("""
            QWidget#root { background: #181a1f; color: #f0f0f0; }
            QFrame#videoArea { background: #000000; }
            QLabel { color: #eeeeee; padding: 4px 10px; }
            QLabel#nowPlaying { background: #24272e; padding: 8px 12px; }
            QPushButton {
                background: #30343d; color: #ffffff; border: 1px solid #454b57;
                border-radius: 5px; padding: 8px 13px;
            }
            QPushButton:hover { background: #414754; }
            QPushButton:pressed { background: #20232a; }
            QSlider::groove:horizontal { height: 5px; background: #454b57; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #4f9cf9; border-radius: 2px; }
            QSlider::handle:horizontal {
                background: #ffffff; width: 13px; margin: -5px 0; border-radius: 6px;
            }
        """)

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("&File")
        self.open_action = QAction("&Open video...", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_file)
        file_menu.addAction(self.open_action)

        self.recent_menu = file_menu.addMenu("Recent videos")
        self._rebuild_recent_menu()

        playlist_menu = self.menuBar().addMenu("&Playlist")
        show_playlist_action = QAction("Show playlist", self)
        show_playlist_action.setShortcut("Ctrl+L")
        show_playlist_action.triggered.connect(self.show_playlist_window)
        playlist_menu.addAction(show_playlist_action)
        playlist_menu.addSeparator()
        add_playlist_action = QAction("Add media files...", self)
        add_playlist_action.triggered.connect(self.add_playlist_files)
        playlist_menu.addAction(add_playlist_action)
        load_playlist_action = QAction("Load playlist...", self)
        load_playlist_action.triggered.connect(self.load_playlist)
        playlist_menu.addAction(load_playlist_action)
        save_playlist_action = QAction("Save playlist...", self)
        save_playlist_action.triggered.connect(self.save_playlist)
        playlist_menu.addAction(save_playlist_action)

        trim_menu = self.menuBar().addMenu("&Trim")
        show_trim_action = QAction("Show trim controls", self)
        show_trim_action.setShortcut("Ctrl+T")
        show_trim_action.triggered.connect(self.show_trim_window)
        trim_menu.addAction(show_trim_action)

        self.join_action = QAction("Join videos...", self)
        self.join_action.triggered.connect(self.join_videos)
        file_menu.addAction(self.join_action)

        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        playback_menu = self.menuBar().addMenu("&Playback")
        play_action = QAction("Play / Pause", self)
        play_action.setShortcut(Qt.Key.Key_Space)
        play_action.triggered.connect(self.toggle_play_pause)
        playback_menu.addAction(play_action)

        stop_action = QAction("Stop", self)
        stop_action.setShortcut("Ctrl+S")
        stop_action.triggered.connect(self.stop)
        playback_menu.addAction(stop_action)

        fullscreen_action = QAction("Toggle Full Screen", self)
        fullscreen_action.setShortcut("F")
        fullscreen_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(fullscreen_action)
        playback_menu.addAction(fullscreen_action)

    def _build_shortcuts(self):
        shortcuts = [
            ("Left", lambda: self._seek_by_slider_step(-1)),
            ("Right", lambda: self._seek_by_slider_step(1)),
            ("Up", lambda: self._adjust_volume_by_step(1)),
            ("Down", lambda: self._adjust_volume_by_step(-1)),
            ("Alt+Left", lambda: self.skip(-10000)),
            ("Alt+Right", lambda: self.skip(10000)),
            ("Ctrl+Left", lambda: self.skip(-60000)),
            ("Ctrl+Right", lambda: self.skip(60000)),
            ("M", self.toggle_mute),
            ("Escape", self.leave_fullscreen),
            ("]", lambda: self.adjust_zoom(10)),
            ("[", lambda: self.adjust_zoom(-10)),
            ("R", self.reset_video_view),
            ("D", lambda: self.pan_video(-40, 0)),
            ("W", lambda: self.pan_video(0, 40)),
            ("A", lambda: self.pan_video(40, 0)),
            ("S", lambda: self.pan_video(0, -40)),
        ]
        for key, callback in shortcuts:
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            action.triggered.connect(callback)
            self.addAction(action)

    def eventFilter(self, watched, event):
        if watched is self.video_area and event.type() == QEvent.Type.Resize:
            self._update_video_surface_geometry()
            return False
        if (
            event.type() == QEvent.Type.MouseButtonDblClick
            and event.button() == Qt.MouseButton.LeftButton
            and isinstance(watched, QWidget)
            and (
                watched is self.centralWidget()
                or watched is self.video_area
                or self.video_area.isAncestorOf(watched)
            )
        ):
            self.toggle_fullscreen()
            return True
        return super().eventFilter(watched, event)

    def set_zoom(self, percentage):
        self.zoom_factor = percentage / 100
        self.zoom_label.setText(f"{percentage}%")
        self._update_video_surface_geometry()

    def adjust_zoom(self, change):
        self.zoom_slider.setValue(
            max(
                self.zoom_slider.minimum(),
                min(
                    self.zoom_slider.maximum(),
                    self.zoom_slider.value() + change,
                ),
            )
        )

    def adjust_zoom_at(self, change, screen_x, screen_y):
        viewport = self.video_area.size()
        if viewport.width() <= 0 or viewport.height() <= 0:
            self.adjust_zoom(change)
            return

        cursor = self.video_area.mapFromGlobal(QPoint(screen_x, screen_y))
        old_width = max(1, round(viewport.width() * self.zoom_factor))
        old_height = max(1, round(viewport.height() * self.zoom_factor))
        relative_x = (cursor.x() - self.video_pan[0]) / old_width
        relative_y = (cursor.y() - self.video_pan[1]) / old_height
        target_zoom = max(
            self.zoom_slider.minimum(),
            min(self.zoom_slider.maximum(), self.zoom_slider.value() + change),
        )
        if target_zoom == self.zoom_slider.value():
            return

        self.zoom_slider.setValue(target_zoom)
        new_width = max(1, round(viewport.width() * self.zoom_factor))
        new_height = max(1, round(viewport.height() * self.zoom_factor))
        self.video_pan = (
            round(cursor.x() - relative_x * new_width),
            round(cursor.y() - relative_y * new_height),
        )
        self._update_video_surface_geometry()

    def reset_video_view(self):
        self.video_pan = (0, 0)
        self.zoom_slider.setValue(100)
        self.set_zoom(self.zoom_slider.value())

    def pan_video(self, dx, dy):
        if self.zoom_factor <= 1:
            return
        self.video_pan = (self.video_pan[0] + dx, self.video_pan[1] + dy)
        self._update_video_surface_geometry()

    def _update_video_surface_geometry(self):
        if not hasattr(self, "video_surface"):
            return
        viewport = self.video_area.size()
        width = max(1, round(viewport.width() * self.zoom_factor))
        height = max(1, round(viewport.height() * self.zoom_factor))
        max_x = viewport.width() - width
        max_y = viewport.height() - height
        x = max(max_x, min(0, self.video_pan[0]))
        y = max(max_y, min(0, self.video_pan[1]))
        self.video_pan = (x, y)
        self.video_surface.setGeometry(x, y, width, height)

    def begin_video_pan(self, screen_x, screen_y):
        if self.zoom_factor <= 1:
            return False
        self.video_pan_origin = (screen_x, screen_y)
        self.video_pan_start = self.video_pan
        return True

    def update_video_pan(self, screen_x, screen_y):
        if self.video_pan_origin is None:
            return
        origin_x, origin_y = self.video_pan_origin
        start_x, start_y = self.video_pan_start
        self.video_pan = (
            start_x + screen_x - origin_x,
            start_y + screen_y - origin_y,
        )
        self._update_video_surface_geometry()

    def end_video_pan(self):
        was_panning = self.video_pan_origin is not None
        self.video_pan_origin = None
        return was_panning

    def _init_vlc(self):
        if vlc is None:
            self._show_vlc_error(
                "The Python VLC package is not installed.\n\n"
                "Run install.bat, or use:\n"
                "py -m pip install python-vlc"
            )
            return
        try:
            self.instance = vlc.Instance("--no-video-title-show", "--quiet")
            self.player = self.instance.media_player_new()
            self.player.set_hwnd(self.video_hwnd)
            self.player.audio_set_volume(self.volume_slider.value())
            self.player_event_manager = self.player.event_manager()
            self.player_event_manager.event_attach(
                vlc.EventType.MediaPlayerEndReached,
                self._on_vlc_end_reached,
            )
        except Exception as exc:
            self._show_vlc_error(
                "VLC could not be initialized.\n\n"
                "Install the 64-bit VLC desktop application, then restart this program.\n\n"
                f"Details: {exc}"
            )

    def _show_vlc_error(self, message):
        QMessageBox.warning(self, "VLC setup required", message)

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open media", str(Path.home()), MEDIA_FILTER
        )
        if filename:
            self.play_file(filename)

    def open_external_file(self, filename):
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        if filename:
            self.play_file(filename)

    def play_file(self, filename, playlist_index=None):
        if not self.player or not self.instance:
            self._show_vlc_error(
                "The playback engine is unavailable. Install 64-bit VLC and python-vlc."
            )
            return
        if not os.path.isfile(filename):
            QMessageBox.warning(self, "File not found", "The selected video file no longer exists.")
            return
        try:
            media = self.instance.media_new_path(os.path.abspath(filename))
            self.player.set_media(media)
            self.player.set_hwnd(self.active_video_hwnd)
            self.current_file = filename
            self.setWindowTitle(
                f"{os.path.basename(filename)} - Python Video Player"
            )
            self.playlist_index = (
                playlist_index if playlist_index is not None else -1
            )
            self.playback_ended = False
            self.pending_resume_position_ms = None
            if self.playlist_index >= 0:
                self.playlist_widget.setCurrentRow(self.playlist_index)
            self._reset_trim_markers()
            self.now_playing.setText(os.path.basename(filename))
            self.position_slider.setValue(0)
            self.current_time.setText("00:00")
            self.total_time.setText("00:00")
            self.player.play()
            self._set_playback_button_text("Pause")
            self.trim_play_button.setEnabled(True)
            self.set_volume(self.volume_slider.value())
            self._add_recent_file(filename)
        except Exception as exc:
            QMessageBox.critical(self, "Playback error", f"Could not open this file.\n\n{exc}")

    def _add_recent_file(self, filename):
        path = os.path.abspath(filename)
        normalized_path = self._normalized_media_path(path)
        self.recent_files = [
            recent
            for recent in self.recent_files
            if self._normalized_media_path(recent) != normalized_path
        ]
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:10]
        self.settings.setValue("recentFiles", self.recent_files)
        self.settings.sync()
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self.recent_menu.clear()
        existing_files = []
        for path in self.recent_files:
            if os.path.isfile(path):
                existing_files.append(path)
                action = QAction(Path(path).name, self)
                action.setToolTip(path)
                action.triggered.connect(
                    lambda checked=False, recent_path=path: self.play_file(recent_path)
                )
                self.recent_menu.addAction(action)

        if existing_files:
            self.recent_menu.addSeparator()
            clear_action = QAction("Clear recent videos", self)
            clear_action.triggered.connect(self.clear_recent_files)
            self.recent_menu.addAction(clear_action)
        else:
            empty_action = QAction("No recent videos", self)
            empty_action.setEnabled(False)
            self.recent_menu.addAction(empty_action)

    def clear_recent_files(self):
        self.recent_files.clear()
        self.settings.remove("recentFiles")
        self.settings.sync()
        self._rebuild_recent_menu()

    @staticmethod
    def _normalized_media_path(filename):
        return os.path.normcase(os.path.abspath(filename))

    def show_playlist_window(self):
        self.playlist_window.show()
        self.playlist_window.raise_()
        self.playlist_window.activateWindow()

    def show_trim_window(self):
        self.trim_window.show()
        self.trim_window.raise_()
        self.trim_window.activateWindow()
        QTimer.singleShot(0, self._attach_trim_video_output)

    def _attach_trim_video_output(self):
        if not self.trim_window.isVisible():
            return
        self.trim_video_hwnd = int(self.trim_window.video_surface.winId())
        try:
            self._switch_video_output(self.trim_video_hwnd)
        except Exception as exc:
            try:
                self._switch_video_output(self.video_hwnd)
            except Exception as restore_exc:
                QMessageBox.warning(
                    self,
                    "Trim preview unavailable",
                    "Could not show video in the trim window or restore the main "
                    f"video output.\n\n{exc}\n\n{restore_exc}",
                )
                return
            QMessageBox.warning(
                self,
                "Trim preview unavailable",
                f"Could not show video in the trim window.\n\n{exc}",
            )

    def _switch_video_output(self, hwnd):
        if not self.player:
            self.active_video_hwnd = hwnd
            return

        state = self.player.get_state()
        was_playing = state == vlc.State.Playing
        was_paused = state == vlc.State.Paused
        position_ms = self.player.get_time()

        if was_playing or was_paused:
            self.player.stop()
        self.player.set_hwnd(hwnd)
        self.active_video_hwnd = hwnd

        if was_playing or was_paused:
            self.player.play()
            self._set_playback_button_text("Pause")
            QTimer.singleShot(
                50,
                lambda: self._restore_output_playback(
                    hwnd, position_ms, was_paused, 20
                ),
            )

    def _restore_output_playback(
        self, hwnd, position_ms, was_paused, attempts_remaining
    ):
        if not self.player or self.active_video_hwnd != hwnd:
            return
        if (
            self.player.get_state() != vlc.State.Playing
            and attempts_remaining > 0
        ):
            QTimer.singleShot(
                50,
                lambda: self._restore_output_playback(
                    hwnd,
                    position_ms,
                    was_paused,
                    attempts_remaining - 1,
                ),
            )
            return
        if position_ms >= 0:
            self.player.set_time(position_ms)
        if was_paused:
            self.player.pause()
            self._set_playback_button_text("Play")

    def restore_main_video_output(self):
        try:
            self._switch_video_output(self.video_hwnd)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Video output warning",
                f"Could not restore video to the main window.\n\n{exc}",
            )

    def add_playlist_files(self):
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Add media to playlist",
            str(Path.home()),
            MEDIA_FILTER,
        )
        self._append_playlist_files(filenames)

    def _append_playlist_files(self, filenames):
        for filename in filenames:
            path = os.path.abspath(filename)
            self.playlist_paths.append(path)
            item = QListWidgetItem(Path(path).name)
            item.setToolTip(path)
            self.playlist_widget.addItem(item)
        if self.playlist_paths and self.playlist_index < 0:
            self.playlist_widget.setCurrentRow(0)

    def remove_playlist_files(self):
        selected_rows = sorted(
            (self.playlist_widget.row(item) for item in self.playlist_widget.selectedItems()),
            reverse=True,
        )
        if not selected_rows:
            return
        current_path = self.current_file
        removed_current = any(
            self._normalized_media_path(self.playlist_paths[row])
            == self._normalized_media_path(current_path)
            for row in selected_rows
        ) if current_path else False
        for row in selected_rows:
            self.playlist_widget.takeItem(row)
            del self.playlist_paths[row]

        if removed_current:
            self.playlist_index = -1
        elif self.playlist_index >= 0:
            self.playlist_index -= sum(row < self.playlist_index for row in selected_rows)
        if self.playlist_paths:
            self.playlist_widget.setCurrentRow(
                max(0, min(self.playlist_index, len(self.playlist_paths) - 1))
            )
        else:
            self.playlist_index = -1

    def load_playlist(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Load playlist",
            str(Path.home()),
            "Playlists (*.m3u8 *.m3u);;All files (*.*)",
        )
        if not filename:
            return
        try:
            lines = Path(filename).read_text(encoding="utf-8-sig").splitlines()
            playlist_dir = Path(filename).resolve().parent
            paths = []
            for line in lines:
                entry = line.strip()
                if not entry or entry.startswith("#"):
                    continue
                media_path = Path(entry)
                if not media_path.is_absolute():
                    media_path = playlist_dir / media_path
                paths.append(str(media_path.resolve()))
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, "Load playlist failed", str(exc))
            return

        self.playlist_widget.clear()
        self.playlist_paths.clear()
        self.playlist_index = -1
        self._append_playlist_files(paths)
        self.trim_status.setText(f"Loaded playlist with {len(paths)} items.")

    def save_playlist(self):
        if not self.playlist_paths:
            QMessageBox.information(self, "Save playlist", "Add media to the playlist first.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save playlist",
            str(Path.home() / "playlist.m3u8"),
            "M3U8 playlist (*.m3u8);;M3U playlist (*.m3u)",
        )
        if not filename:
            return
        if not Path(filename).suffix:
            filename = f"{filename}.m3u8"

        playlist_dir = Path(filename).resolve().parent
        entries = ["#EXTM3U"]
        for media_path in self.playlist_paths:
            absolute_path = Path(media_path).resolve()
            try:
                entry = os.path.relpath(absolute_path, playlist_dir)
            except ValueError:
                entry = str(absolute_path)
            entries.append(entry)
        try:
            Path(filename).write_text("\n".join(entries) + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Save playlist failed", str(exc))
            return
        self.trim_status.setText(f"Playlist saved: {Path(filename).name}")

    def _play_playlist_item(self, item):
        index = self.playlist_widget.row(item)
        if 0 <= index < len(self.playlist_paths):
            self._play_playlist_index(index)

    def play_previous_track(self):
        self._navigate_track(-1)

    def play_next_track(self):
        self._navigate_track(1)

    def _navigate_track(self, step):
        if not self.current_file:
            return

        paths = (
            self.playlist_paths
            if self.playlist_index >= 0
            else self._folder_video_paths()
        )
        current_path = self._normalized_media_path(self.current_file)
        current_index = next(
            (
                index for index, path in enumerate(paths)
                if self._normalized_media_path(path) == current_path
            ),
            -1,
        )
        next_index = current_index + step
        if not 0 <= next_index < len(paths):
            return

        if paths is self.playlist_paths:
            self._play_playlist_index(next_index)
        else:
            self.play_file(paths[next_index])

    def _folder_video_paths(self):
        if not self.current_file:
            return []
        folder = Path(self.current_file).parent
        try:
            return sorted(
                (
                    str(path.resolve())
                    for path in folder.iterdir()
                    if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
                ),
                key=lambda path: (Path(path).name.casefold(), path.casefold()),
            )
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Could not read video folder",
                f"Could not list videos in:\n{folder}\n\n{exc}",
            )
            return []

    def _handle_playback_end(self):
        if not self.current_file:
            return

        self.playback_ended = True
        self.pending_resume_position_ms = None
        mode = self.playback_mode.currentData()
        if mode == "repeat_one":
            self.stop()
            self.playback_ended = True
            return

        if mode == "random_folder":
            paths = self._folder_video_paths()
            current_path = self._normalized_media_path(self.current_file)
            candidates = [
                path for path in paths
                if self._normalized_media_path(path) != current_path
            ]
            if not candidates:
                candidates = paths
            if candidates:
                self.play_file(random.choice(candidates))
            return

        paths = (
            self.playlist_paths
            if self.playlist_index >= 0
            else self._folder_video_paths()
        )
        current_path = self._normalized_media_path(self.current_file)
        current_index = next(
            (
                index for index, path in enumerate(paths)
                if self._normalized_media_path(path) == current_path
            ),
            -1,
        )
        if current_index < 0:
            return

        step = -1 if mode == "previous" else 1
        next_index = current_index + step
        if not 0 <= next_index < len(paths):
            if mode != "repeat_all":
                return
            next_index = 0 if step > 0 else len(paths) - 1

        if paths is self.playlist_paths:
            self._play_playlist_index(next_index)
        else:
            self.play_file(paths[next_index])

    def _play_playlist_index(self, index):
        if not 0 <= index < len(self.playlist_paths):
            return
        self.playlist_index = index
        self.playlist_widget.setCurrentRow(index)
        self.play_file(self.playlist_paths[index], playlist_index=index)

    def _on_vlc_end_reached(self, event):
        self.player_signals.end_reached.emit()

    def _reset_trim_markers(self):
        self.trim_start_ms = None
        self.trim_end_ms = None
        self.trim_start_button.setEnabled(True)
        self.trim_end_button.setEnabled(True)
        self.trim_save_button.setEnabled(False)
        self.trim_status.setText("Set trim start and end from the current playback position.")
        self._update_trim_visuals()

    def _playback_position_for_trim(self):
        if not self.player or not self.current_file:
            QMessageBox.information(self, "Trim media", "Open a media file before setting trim points.")
            return None
        position = self.player.get_time()
        if position < 0:
            QMessageBox.information(
                self, "Trim media", "Wait until playback starts, then set the trim point."
            )
            return None
        return position

    def set_trim_start(self):
        position = self._playback_position_for_trim()
        if position is None:
            return
        self.trim_start_ms = position
        if self.trim_end_ms is not None and self.trim_end_ms <= position:
            self.trim_end_ms = None
        self._update_trim_status()

    def set_trim_end(self):
        position = self._playback_position_for_trim()
        if position is None:
            return
        if self.trim_start_ms is None:
            QMessageBox.information(
                self, "Trim media", "Set the trim start before setting the trim end."
            )
            return
        if position <= self.trim_start_ms:
            QMessageBox.information(
                self, "Trim media", "The trim end must be later than the trim start."
            )
            return
        self.trim_end_ms = position
        self._update_trim_status()

    def _update_trim_status(self):
        self.trim_status.setText(
            f"Start: {format_precise_time(self.trim_start_ms)}    "
            f"End: {format_precise_time(self.trim_end_ms)}"
        )
        self._update_trim_visuals()
        self.trim_save_button.setEnabled(
            self.trim_start_ms is not None
            and self.trim_end_ms is not None
            and self.trim_end_ms > self.trim_start_ms
        )

    def _update_trim_visuals(self, current_ms=None, duration_ms=None):
        if duration_ms is None:
            duration_ms = self.player.get_length() if self.player else 0
        if current_ms is None:
            current_ms = self.player.get_time() if self.player else 0
        self.trim_window.timeline.set_positions(
            duration_ms,
            current_ms,
            self.trim_start_ms,
            self.trim_end_ms,
        )
        self.trim_window.start_time_label.setText(
            f"START\n{format_precise_time(self.trim_start_ms)}"
        )
        self.trim_window.end_time_label.setText(
            f"END\n{format_precise_time(self.trim_end_ms)}"
        )
        if self.trim_start_ms is not None and self.trim_end_ms is not None:
            selected_duration = self.trim_end_ms - self.trim_start_ms
            duration_text = format_precise_time(selected_duration)
        else:
            duration_text = "Not set"
        self.trim_window.duration_label.setText(
            f"SELECTED DURATION\n{duration_text}"
        )

    def save_trimmed_media(self):
        if self.trim_start_ms is None or self.trim_end_ms is None:
            QMessageBox.information(
                self, "Trim media", "Set both trim start and trim end before exporting."
            )
            return
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            QMessageBox.warning(
                self,
                "FFmpeg required",
                "FFmpeg was not found. Install FFmpeg and add its bin folder to PATH, "
                "then restart the player to export trimmed media.",
            )
            return

        source_path = Path(self.current_file).resolve()
        default_output = source_path.with_name(f"{source_path.stem}_trimmed.mp4")
        output_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save trimmed media",
            str(default_output),
            ";;".join(TRIM_EXPORT_FILTERS),
            "MP4 video (*.mp4)",
        )
        if not output_path:
            return
        output_format = Path(output_path).suffix.lower().lstrip(".")
        if not output_format:
            output_format = TRIM_EXPORT_FILTERS[selected_filter]
            output_path = f"{output_path}.{output_format}"
        if output_format not in TRIM_EXPORT_FILTERS.values():
            QMessageBox.warning(
                self,
                "Unsupported export format",
                "Choose MP4, MKV, MOV, WebM, AVI, or GIF for the trimmed export.",
            )
            return
        if output_format == "gif":
            codec_arguments = [
                "-filter_complex",
                "[0:v:0]fps=15,scale=640:-1:flags=lanczos,split[palette_src][gif_src];"
                "[palette_src]palettegen[palette];[gif_src][palette]paletteuse[gif]",
                "-map", "[gif]",
                "-an",
                "-loop", "0",
            ]
        elif output_format == "webm":
            codec_arguments = [
                "-map", "0:v?",
                "-map", "0:a?",
                "-c:v", "libvpx-vp9",
                "-deadline", "good",
                "-cpu-used", "2",
                "-b:v", "0",
                "-crf", "30",
                "-c:a", "libopus",
                "-b:a", "128k",
            ]
        elif output_format == "avi":
            codec_arguments = [
                "-map", "0:v?",
                "-map", "0:a?",
                "-c:v", "mpeg4",
                "-q:v", "5",
                "-c:a", "libmp3lame",
                "-q:a", "2",
            ]
        else:
            codec_arguments = [
                "-map", "0:v?",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "20",
                "-c:a", "aac",
                "-b:a", "192k",
            ]
            if output_format == "mp4" or output_format == "mov":
                codec_arguments.extend(["-movflags", "+faststart"])

        if os.path.normcase(os.path.abspath(output_path)) == os.path.normcase(str(source_path)):
            QMessageBox.warning(self, "Trim media", "Choose a new file name; the source will not be overwritten.")
            return

        duration_ms = self.trim_end_ms - self.trim_start_ms
        arguments = [
            "-hide_banner",
            "-y",
            "-nostats",
            "-progress", "pipe:1",
            "-ss", f"{self.trim_start_ms / 1000:.3f}",
            "-i", str(source_path),
            "-t", f"{duration_ms / 1000:.3f}",
            *codec_arguments,
            output_path,
        ]
        self.trim_error_output.clear()
        self.export_progress_buffer.clear()
        self.export_total_ms = duration_ms
        self.trim_output_path = output_path
        self.export_kind = "trim"
        self._set_export_running(True)
        self.trim_status.setText("Trimming: 0%")
        self.trim_process.start(ffmpeg, arguments)

    def _read_export_progress(self):
        self.export_progress_buffer.extend(bytes(self.trim_process.readAllStandardOutput()))
        while b"\n" in self.export_progress_buffer:
            line, _, remaining = self.export_progress_buffer.partition(b"\n")
            self.export_progress_buffer = bytearray(remaining)
            key, separator, value = line.decode(errors="replace").strip().partition("=")
            if not separator:
                continue
            if key == "out_time":
                self._update_export_progress(self._parse_ffmpeg_time(value))
            elif key == "progress" and value == "end":
                self._show_export_progress(100)

    @staticmethod
    def _parse_ffmpeg_time(value):
        try:
            hours, minutes, seconds = value.split(":")
            return round(
                (int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000
            )
        except (ValueError, TypeError):
            return None

    def _update_export_progress(self, current_ms):
        if self.export_total_ms <= 0 or current_ms is None:
            return
        percentage = max(0, min(99, int(current_ms * 100 / self.export_total_ms)))
        self._show_export_progress(percentage)

    def _show_export_progress(self, percentage):
        self.export_progress.setValue(percentage)
        operation = "Trimming" if self.export_kind == "trim" else "Joining"
        self.trim_status.setText(f"{operation}: {percentage}%")

    def _read_trim_stderr(self):
        self.trim_error_output.extend(bytes(self.trim_process.readAllStandardError()))

    def _trim_finished(self, exit_code, exit_status):
        self._read_trim_stderr()
        self._read_export_progress()
        self._set_export_running(False)
        completed = exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit
        operation = self.export_kind
        self.export_kind = None
        if completed:
            self.export_progress.setValue(100)
            self.trim_status.setText("Export completed: 100%")
            QMessageBox.information(
                self,
                "Export complete",
                f"The exported media was saved to:\n{self.trim_output_path}",
            )
            return

        details = self.trim_error_output.decode(errors="replace").strip()
        if len(details) > 1600:
            details = details[-1600:]
        message = (
            "FFmpeg could not export the selected segment."
            if operation == "trim"
            else "FFmpeg could not join the selected videos."
        )
        if details:
            message = f"{message}\n\n{details}"
        self.export_progress.hide()
        self.trim_status.setText("Export failed.")
        QMessageBox.warning(self, "Export failed", message)

    def _trim_process_error(self, error):
        if error != QProcess.ProcessError.FailedToStart:
            return
        operation = self.export_kind
        self.export_kind = None
        self._set_export_running(False)
        self.export_progress.hide()
        self.trim_status.setText("Could not start FFmpeg.")
        action = "trim" if operation == "trim" else "join videos"
        QMessageBox.warning(
            self,
            "Export failed",
            f"Could not start FFmpeg to {action}.\n\n{self.trim_process.errorString()}",
        )

    def _set_export_running(self, running):
        has_media = bool(self.current_file)
        if running:
            self.export_progress.setValue(0)
            self.export_progress.show()
        elif self.trim_process.state() == QProcess.ProcessState.NotRunning:
            self.export_progress.setValue(100)
        self.trim_start_button.setEnabled(not running and has_media)
        self.trim_end_button.setEnabled(not running and has_media)
        self.open_button.setEnabled(not running)
        self.join_button.setEnabled(not running)
        self.open_action.setEnabled(not running)
        self.join_action.setEnabled(not running)
        self.trim_save_button.setEnabled(
            not running
            and has_media
            and self.trim_start_ms is not None
            and self.trim_end_ms is not None
            and self.trim_end_ms > self.trim_start_ms
        )

    def join_videos(self):
        if self.trim_process.state() != QProcess.ProcessState.NotRunning:
            return
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose videos to join (in the order shown)",
            str(Path.home()),
            "Video files (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.mpeg "
            "*.mpg *.m4v *.3gp *.ts *.mts *.m2ts *.vob *.ogv *.divx *.asf *.rm *.rmvb);;"
            "All files (*.*)",
        )
        if len(filenames) < 2:
            if filenames:
                QMessageBox.information(
                    self, "Join videos", "Select at least two video files to join."
                )
            return

        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            QMessageBox.warning(
                self,
                "FFmpeg required",
                "FFmpeg and ffprobe must both be available on PATH to join videos.",
            )
            return

        try:
            clip_info = [self._probe_video(ffprobe, filename) for filename in filenames]
        except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, "Could not read video", str(exc))
            return

        source_path = Path(filenames[0]).resolve()
        default_output = source_path.with_name(f"{source_path.stem}_joined.mp4")
        output_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save joined video",
            str(default_output),
            ";;".join(JOIN_EXPORT_FILTERS),
            "MP4 video (*.mp4)",
        )
        if not output_path:
            return
        output_format = Path(output_path).suffix.lower().lstrip(".")
        if not output_format:
            output_format = JOIN_EXPORT_FILTERS[selected_filter]
            output_path = f"{output_path}.{output_format}"
        if output_format not in JOIN_EXPORT_FILTERS.values():
            QMessageBox.warning(
                self,
                "Unsupported export format",
                "Choose MP4, MKV, MOV, WebM, or AVI for the joined video.",
            )
            return
        output_absolute = os.path.normcase(os.path.abspath(output_path))
        if any(
            output_absolute == os.path.normcase(os.path.abspath(filename))
            for filename in filenames
        ):
            QMessageBox.warning(
                self, "Join videos", "Choose a new file name; source videos will not be overwritten."
            )
            return

        arguments = self._build_join_arguments(filenames, clip_info, output_format, output_path)
        self.trim_error_output.clear()
        self.export_progress_buffer.clear()
        self.export_total_ms = round(sum(clip["duration"] for clip in clip_info) * 1000)
        self.trim_output_path = output_path
        self.export_kind = "join"
        self._set_export_running(True)
        self.trim_status.setText("Joining: 0%")
        self.trim_process.start(ffmpeg, arguments)

    @staticmethod
    def _probe_video(ffprobe, filename):
        result = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration:stream=codec_type,width,height",
                "-of", "json",
                filename,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode:
            details = result.stderr.strip()
            raise ValueError(
                f"ffprobe could not read this video:\n{filename}"
                + (f"\n\n{details}" if details else "")
            )
        metadata = json.loads(result.stdout)
        video_stream = next(
            (stream for stream in metadata["streams"] if stream["codec_type"] == "video"),
            None,
        )
        if video_stream is None:
            raise ValueError(f"This file does not contain a video stream:\n{filename}")
        duration = float(metadata["format"]["duration"])
        if duration <= 0:
            raise ValueError(f"Could not determine the video duration:\n{filename}")
        return {
            "width": int(video_stream["width"]),
            "height": int(video_stream["height"]),
            "duration": duration,
            "has_audio": any(
                stream["codec_type"] == "audio" for stream in metadata["streams"]
            ),
        }

    @staticmethod
    def _build_join_arguments(filenames, clip_info, output_format, output_path):
        max_width = min(1920, max(clip["width"] for clip in clip_info))
        max_height = min(1080, max(clip["height"] for clip in clip_info))
        width = max(2, max_width - max_width % 2)
        height = max(2, max_height - max_height % 2)
        arguments = ["-hide_banner", "-y", "-nostats", "-progress", "pipe:1"]
        for filename in filenames:
            arguments.extend(["-i", filename])

        filters = []
        concat_inputs = []
        for index, clip in enumerate(clip_info):
            video_label = f"v{index}"
            audio_label = f"a{index}"
            filters.append(
                f"[{index}:v:0]scale={width}:{height}:"
                "force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                "setsar=1,fps=30,format=yuv420p"
                f"[{video_label}]"
            )
            if clip["has_audio"]:
                filters.append(
                    f"[{index}:a:0]aresample=48000,"
                    "aformat=sample_fmts=fltp:channel_layouts=stereo"
                    f"[{audio_label}]"
                )
            else:
                filters.append(
                    "anullsrc=r=48000:cl=stereo,"
                    f"atrim=duration={clip['duration']:.6f}"
                    f"[{audio_label}]"
                )
            concat_inputs.extend([f"[{video_label}]", f"[{audio_label}]"])

        filters.append(
            "".join(concat_inputs)
            + f"concat=n={len(filenames)}:v=1:a=1[vout][aout]"
        )
        arguments.extend(["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]"])

        if output_format == "webm":
            arguments.extend([
                "-c:v", "libvpx-vp9", "-deadline", "good", "-cpu-used", "2",
                "-b:v", "0", "-crf", "30", "-c:a", "libopus", "-b:a", "128k",
            ])
        elif output_format == "avi":
            arguments.extend([
                "-c:v", "mpeg4", "-q:v", "5", "-c:a", "libmp3lame", "-q:a", "2",
            ])
        else:
            arguments.extend([
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
            ])
            if output_format in ("mp4", "mov"):
                arguments.extend(["-movflags", "+faststart"])
        arguments.append(output_path)
        return arguments
        self.trim_save_button.setEnabled(
            not running
            and self.trim_start_ms is not None
            and self.trim_end_ms is not None
            and self.trim_end_ms > self.trim_start_ms
        )

    def toggle_play_pause(self):
        if not self.player:
            return
        try:
            if self.player.is_playing():
                self.player.pause()
                self._set_playback_button_text("Play")
            elif self.current_file:
                if self.playback_ended:
                    length = self.player.get_length()
                    self.pending_resume_position_ms = (
                        int(length * self.position_slider.value() / 1000)
                        if length > 0
                        else None
                    )
                # VLC state can take a moment to update after a previous play command.
                self.player.play()
                self._set_playback_button_text("Pause")
            else:
                self.open_file()
        except Exception as exc:
            QMessageBox.warning(self, "Playback error", str(exc))

    def stop(self):
        if self.player:
            self.player.stop()
        self.playback_ended = False
        self.pending_resume_position_ms = None
        self._set_playback_button_text("Play")
        self.position_slider.setValue(0)
        self.current_time.setText("00:00")

    def skip(self, milliseconds):
        if not self.player:
            return
        length = self.player.get_length()
        current = self.player.get_time()
        if length > 0 and current >= 0:
            self.player.set_time(max(0, min(length, current + milliseconds)))

    def _seek_by_slider_step(self, direction):
        value = max(
            self.position_slider.minimum(),
            min(
                self.position_slider.maximum(),
                self.position_slider.value()
                + direction * self.position_slider.singleStep(),
            ),
        )
        self.position_slider.setValue(value)
        self._seek_to_position(value)

    def _adjust_volume_by_step(self, direction):
        self.volume_slider.setValue(
            self.volume_slider.value()
            + direction * self.volume_slider.singleStep()
        )

    def set_volume(self, value):
        self.volume_value_label.setText(f"{value}%")
        if self.player:
            self.player.audio_set_volume(int(value))
        self.mute_button.setText("Unmute" if value == 0 else "Mute")

    def reset_volume(self):
        self.volume_slider.setValue(80)

    def toggle_mute(self):
        if not self.player:
            return
        muted = self.player.audio_get_mute()
        self.player.audio_set_mute(not muted)
        self.mute_button.setText("Unmute" if not muted else "Mute")

    def _set_playback_button_text(self, text):
        self.play_button.setText(text)
        self.trim_play_button.setText(text)

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.is_fullscreen = False
            self.fullscreen_button.setText("Full Screen")
            self.controls_panel.show()
            self.menuBar().show()
        else:
            self.controls_panel.hide()
            self.showFullScreen()
            self.is_fullscreen = True
            self.fullscreen_button.setText("Exit Full Screen")
            self.menuBar().hide()

    def leave_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.is_fullscreen = False
            self.fullscreen_button.setText("Full Screen")
            self.controls_panel.show()
            self.menuBar().show()

    def _seek_started(self):
        self.is_seeking = True

    def _seek_preview(self, value):
        if self.player:
            length = self.player.get_length()
            if length > 0:
                self.current_time.setText(format_time(length * value / 1000))

    def _seek_finished(self):
        if self.player:
            length = self.player.get_length()
            if length > 0:
                position_ms = int(length * self.position_slider.value() / 1000)
                self._seek_player_to(position_ms)
        self.is_seeking = False

    def _seek_to_position(self, value):
        if self.player:
            length = self.player.get_length()
            if length > 0:
                position_ms = int(length * value / 1000)
                self.current_time.setText(format_time(position_ms))
                self._seek_player_to(position_ms)

    def _seek_player_to(self, position_ms):
        if self.playback_ended:
            self.pending_resume_position_ms = position_ms
        else:
            self.player.set_time(position_ms)

    def _seek_trim_timeline(self, position_ms):
        if not self.player:
            return
        length = self.player.get_length()
        if length <= 0:
            return

        position_ms = max(0, min(length, position_ms))
        self._seek_player_to(position_ms)
        self.is_seeking = False
        self.current_time.setText(format_time(position_ms))
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(int(position_ms * 1000 / length))
        self.position_slider.blockSignals(False)
        self._update_trim_visuals(position_ms, length)

    def update_playback_ui(self):
        if not self.player:
            return
        try:
            length = self.player.get_length()
            if (
                self.pending_resume_position_ms is not None
                and self.player.is_playing()
            ):
                self.player.set_time(self.pending_resume_position_ms)
                self.pending_resume_position_ms = None
                self.playback_ended = False
            current = self.player.get_time()
            self._update_trim_visuals(current, length)
            if length > 0:
                self.total_time.setText(format_time(length))
                if not self.is_seeking and not (
                    self.playback_ended and not self.player.is_playing()
                ):
                    self.current_time.setText(format_time(current))
                    self.position_slider.blockSignals(True)
                    self.position_slider.setValue(max(0, min(1000, int(current * 1000 / length))))
                    self.position_slider.blockSignals(False)
            if self.player.is_playing():
                self._set_playback_button_text("Pause")
            elif self.current_file:
                self._set_playback_button_text("Play")
        except Exception:
            pass

    def closeEvent(self, event):
        self.timer.stop()
        if self.player:
            try:
                self.player.stop()
                self.player.release()
            except Exception:
                pass
        if self.instance:
            try:
                self.instance.release()
            except Exception:
                pass
        event.accept()


def main():
    startup_file = next(
        (argument for argument in sys.argv[1:] if not argument.startswith("-")),
        None,
    )
    app = QApplication(sys.argv)
    app.setOrganizationName("PythonVideoPlayer")
    app.setApplicationName("Python Video Player")
    server_name = "PythonVideoStudioSingleInstance"
    startup_file = os.path.abspath(startup_file) if startup_file else None
    if forward_open_request(server_name, startup_file):
        return

    instance_server = SingleInstanceServer(server_name)
    if not instance_server.listen():
        if forward_open_request(server_name, startup_file):
            return
        QLocalServer.removeServer(server_name)
        if (
            not instance_server.listen()
            and not forward_open_request(server_name, startup_file)
        ):
            raise RuntimeError(
                f"Could not listen for media open requests: "
                f"{instance_server.server.errorString()}"
            )

    icon_path = Path(__file__).with_name("Video Studio Icon.ico")
    if not icon_path.is_file():
        icon_path = Path(sys.executable).resolve().with_name(
            "Video Studio Icon.ico"
        )
    if not icon_path.is_file():
        raise FileNotFoundError(
            "Video Studio Icon.ico is missing. Keep it next to main.py or "
            "Video Studio.exe."
        )
    app.setWindowIcon(QIcon(str(icon_path)))
    window = VideoPlayer()
    instance_server.request_received.connect(window.open_external_file)
    instance_server.request_error.connect(
        lambda message: QMessageBox.warning(window, "Open request failed", message)
    )
    window.show()
    if startup_file:
        QTimer.singleShot(0, lambda: window.play_file(startup_file))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
