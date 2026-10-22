"""Truthful native Qt station UI; modem ownership belongs to the controller."""
from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal, Slot
from PySide6.QtGui import QColor, QCloseEvent, QImage, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .theme import NAVY


class VideoViewport(QWidget):
    """A pixel-preserving picture area, with no synthetic frames or animation."""
    def __init__(self, size: QSize, placeholder: str, parent=None):
        super().__init__(parent)
        self.image = QImage()
        self.placeholder = placeholder
        self.setMinimumSize(size + QSize(4, 4))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName(placeholder)

    def sizeHint(self):
        return self.minimumSize()

    def set_frame(self, image: QImage):
        self.image = image.copy()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#111111'))
        painter.setPen(QColor('#404040'))
        painter.drawLine(0, 0, self.width() - 1, 0)
        painter.drawLine(0, 0, 0, self.height() - 1)
        painter.setPen(QColor('white'))
        painter.drawLine(0, self.height() - 1, self.width() - 1, self.height() - 1)
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height() - 1)
        inside = self.rect().adjusted(2, 2, -2, -2)
        if self.image.isNull():
            painter.setPen(QColor('#b0b0b0'))
            painter.drawText(inside, Qt.AlignmentFlag.AlignCenter, self.placeholder)
        else:
            scaled = self.image.size().scaled(inside.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRect(QPoint(inside.center().x() - scaled.width() // 2,
                                  inside.center().y() - scaled.height() // 2), scaled)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawImage(target, self.image)


class ActivityLamp(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.label = label
        self.active = False
        self.setFixedSize(36, 17)
        self.setAccessibleName(f'{label} inactive')

    def set_active(self, value: bool):
        self.active = bool(value)
        self.setAccessibleName(f'{self.label} {"active" if self.active else "inactive"}')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(QRect(0, 4, 8, 8), QColor('#00a000' if self.active else '#334433'))
        painter.setPen(QColor('#202020'))
        painter.drawRect(QRect(0, 4, 8, 8))
        painter.drawText(QRect(12, 0, 24, 17), Qt.AlignmentFlag.AlignVCenter, self.label)


class AudioMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.setFixedHeight(13)
        self.setMinimumWidth(128)
        self.setAccessibleName('Incoming audio level: 0 percent')

    def set_level(self, value: float):
        self.level = max(0.0, min(1.0, value)) if math.isfinite(value) else 0.0
        self.setAccessibleName(f'Incoming audio level: {round(self.level * 100)} percent')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#202020'))
        count = round(self.level * 10)
        for i in range(10):
            color = '#00a000' if i < 7 else '#c0a000' if i < 9 else '#d00000'
            painter.fillRect(QRect(2 + i * (self.width() - 3) // 10, 2,
                                   max(2, (self.width() - 3) // 10 - 2), 9),
                             QColor(color if i < count else '#344034'))


def _time(value: float, hours: bool = False) -> str:
    seconds = max(0, int(value))
    if hours:
        return f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'
    return f'{seconds // 60:02d}:{seconds % 60:02d}'


class StationWindow(QMainWindow):
    dial_requested = Signal(str, str)
    listen_requested = Signal(str)
    hangup_requested = Signal()
    file_requested = Signal()
    send_requested = Signal()
    pause_requested = Signal(bool)
    stop_requested = Signal()
    refresh_requested = Signal()
    closing = Signal()
    mute_changed = Signal(bool)
    new_station_requested = Signal()
    preview_requested = Signal()
    devices_requested = Signal()
    dependencies_requested = Signal()
    source_changed = Signal(str)

    def __init__(self, station: str, ports: list[tuple[str, str]] | None = None, parent=None):
        super().__init__(parent)
        self.station = str(station)
        self.peer = ''
        self._state = 'idle'
        self._preparing = False
        self._capture_pending = False
        self._capture_video_state = 'stopped'
        self._dependencies_ready = True
        self._movie = None
        self._telemetry = {}
        self._transmitting = False
        self._paused = False
        self._diagnostics = None
        self.setWindowTitle(f'Modem Conference — Station {self.station}')
        self.setMinimumSize(548, 680)
        self.resize(568, 722)
        self._build()
        self.set_ports(ports or [])
        self.set_state('idle')

    def _button(self, text, name, slot, parent=None):
        button = QPushButton(text, parent)
        button.setObjectName(name)
        button.clicked.connect(slot)
        return button

    def _build(self):
        body = QWidget(objectName='stationBody')
        self.setCentralWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(5)
        caption = QLabel(f'▣  Modem Conference — Station {self.station}', objectName='stationCaption')
        outer.addWidget(caption)
        self._build_menu()
        toolbar = QHBoxLayout()
        self.call_button = self._button('☎  &Call', 'callButton', self._dial)
        self.answer_button = self._button('&Answer', 'answerButton', self._listen)
        self.hangup_button = self._button('&Hang up', 'hangupButton', self.hangup_requested.emit)
        self.open_button = self._button('▰  Open &movie…', 'openMovieButton', self.file_requested.emit)
        toolbar.addWidget(self.call_button)
        toolbar.addWidget(self.answer_button)
        toolbar.addWidget(self.hangup_button)
        toolbar.addSpacing(8)
        toolbar.addWidget(self.open_button)
        toolbar.addStretch()
        outer.addLayout(toolbar)

        connection = QGroupBox('Telephone connection')
        grid = QGridLayout(connection)
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(6)
        modem_label = QLabel('&Modem:')
        self.port_combo = QComboBox(objectName='modemSelector')
        self.port_combo.setAccessibleName('Modem serial port')
        self.port_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.port_combo.currentIndexChanged.connect(self._sync_controls)
        modem_label.setBuddy(self.port_combo)
        self.refresh_button = self._button('&Refresh', 'refreshButton', self.refresh_requested.emit)
        number_label = QLabel('Call &to:')
        self.number_edit = QLineEdit('', objectName='telephoneNumber')
        self.number_edit.setAccessibleName('Telephone number to call')
        self.number_edit.setMaxLength(64)
        self.number_edit.textChanged.connect(self._sync_controls)
        self.number_edit.returnPressed.connect(self._dial)
        number_label.setBuddy(self.number_edit)
        self.connection_button = self._button('&Info…', 'connectionInfoButton', self.show_connection_information)
        grid.addWidget(modem_label, 0, 0)
        grid.addWidget(self.port_combo, 0, 1)
        grid.addWidget(self.refresh_button, 0, 2)
        grid.addWidget(number_label, 1, 0)
        grid.addWidget(self.number_edit, 1, 1)
        grid.addWidget(self.connection_button, 1, 2)
        self.connection_label = QLabel('Choose a modem, then call or answer.')
        self.connection_label.setWordWrap(True)
        grid.addWidget(self.connection_label, 2, 0, 1, 2)
        lamps = QHBoxLayout()
        lamps.setSpacing(3)
        self.lamps = {key: ActivityLamp(key.upper()) for key in ('cd', 'tx', 'rx')}
        for lamp in self.lamps.values():
            lamps.addWidget(lamp)
        grid.addLayout(lamps, 2, 2)
        outer.addWidget(connection)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        tab_row.addWidget(QLabel('Current call', objectName='tabCaption'))
        self.peer_label = QLabel('  Remote station', objectName='smallText')
        tab_row.addWidget(self.peer_label)
        tab_row.addStretch()
        outer.addLayout(tab_row)
        panel = QFrame(objectName='videoPanel')
        video_grid = QGridLayout(panel)
        video_grid.setContentsMargins(10, 10, 10, 10)
        video_grid.setHorizontalSpacing(14)
        video_grid.addWidget(QLabel('<b>Receiving</b>'), 0, 0)
        video_grid.addWidget(QLabel('<b>My video</b>'), 0, 1)
        self.remote_video = VideoViewport(QSize(256, 192), 'Waiting for video')
        self.remote_video.setObjectName('incomingVideo')
        self.local_video = VideoViewport(QSize(128, 96), 'Choose a movie')
        self.local_video.setObjectName('outgoingPreview')
        video_grid.addWidget(self.remote_video, 1, 0)
        right = QVBoxLayout()
        right.addWidget(self.local_video)
        self.outgoing_label = QLabel('No movie selected', objectName='smallText')
        self.outgoing_label.setWordWrap(True)
        right.addWidget(self.outgoing_label)
        right.addSpacing(8)
        right.addWidget(QLabel('Incoming audio', objectName='smallText'))
        self.audio_meter = AudioMeter()
        right.addWidget(self.audio_meter)
        self.mute_checkbox = QCheckBox('&Mute audio')
        self.mute_checkbox.setAccessibleName('Mute received audio')
        self.mute_checkbox.toggled.connect(self._mute_toggled)
        right.addWidget(self.mute_checkbox)
        right.addStretch()
        video_grid.addLayout(right, 1, 1)
        self.video_details = QLabel('No incoming video', objectName='smallText')
        video_grid.addWidget(self.video_details, 2, 0, 1, 2)
        video_grid.setColumnStretch(0, 2)
        video_grid.setColumnStretch(1, 1)
        outer.addWidget(panel, 1)

        movie_group = QGroupBox('Source to transmit')
        movie_layout = QVBoxLayout(movie_group)
        source_row = QHBoxLayout()
        self.source_combo = QComboBox(objectName='sourceSelector')
        self.source_combo.addItem('Movie file', 'file')
        self.source_combo.addItem('Camera + microphone', 'camera')
        self.source_combo.currentIndexChanged.connect(self._source_changed)
        self.source_combo.currentIndexChanged.connect(self._sync_controls)
        source_row.addWidget(self.source_combo)
        self.preview_button = self._button('Pre&view', 'previewButton', self.preview_requested.emit)
        source_row.addWidget(self.preview_button)
        self.devices_button = self._button('&Devices…', 'devicesButton', self.devices_requested.emit)
        source_row.addWidget(self.devices_button)
        movie_layout.addLayout(source_row)
        file_row = QHBoxLayout()
        self.filename_label = QLabel('No movie selected', objectName='filename')
        self.filename_label.setMinimumWidth(0)
        self.filename_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.browse_button = self._button('&Browse…', 'browseButton', self.file_requested.emit)
        file_row.addWidget(self.filename_label, 1)
        file_row.addWidget(self.browse_button)
        movie_layout.addLayout(file_row)
        self.movie_progress = QProgressBar(objectName='movieProgress')
        self.movie_progress.setRange(0, 1000)
        self.movie_progress.setValue(0)
        self.movie_progress.setTextVisible(False)
        self.movie_progress.setAccessibleName('Movie transmission progress')
        movie_layout.addWidget(self.movie_progress)
        self.movie_details = QLabel('Select a movie to prepare it for this connection.', objectName='smallText')
        self.movie_details.setWordWrap(True)
        movie_layout.addWidget(self.movie_details)
        actions = QHBoxLayout()
        self.transmit_button = self._button('&Transmit', 'transmitButton', self.send_requested.emit)
        self.pause_button = self._button('&Pause', 'pauseButton', self._pause)
        self.stop_button = self._button('&Stop', 'stopButton', self.stop_requested.emit)
        actions.addStretch()
        actions.addWidget(self.transmit_button)
        actions.addWidget(self.pause_button)
        actions.addWidget(self.stop_button)
        movie_layout.addLayout(actions)
        outer.addWidget(movie_group)

        self.log_view = QPlainTextEdit(objectName='connectionLog')
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.log_view.setMaximumHeight(130)
        self.log_view.setAccessibleName('Connection log')
        self.log_view.hide()
        outer.addWidget(self.log_view)
        status_row = QHBoxLayout()
        status_row.setSpacing(3)
        self.state_label = QLabel('Idle', objectName='statusCell')
        self.rate_label = QLabel('— bps', objectName='statusCell')
        self.time_label = QLabel('00:00:00', objectName='statusCell')
        status_row.addWidget(self.state_label, 1)
        status_row.addWidget(self.rate_label)
        status_row.addWidget(self.time_label)
        outer.addLayout(status_row)
        QWidget.setTabOrder(self.port_combo, self.number_edit)
        QWidget.setTabOrder(self.number_edit, self.call_button)
        QWidget.setTabOrder(self.call_button, self.answer_button)
        QWidget.setTabOrder(self.answer_button, self.hangup_button)
        QWidget.setTabOrder(self.hangup_button, self.browse_button)
        QWidget.setTabOrder(self.browse_button, self.transmit_button)

    def _build_menu(self):
        menu = self.menuBar()
        menu.setNativeMenuBar(False)
        file_menu = menu.addMenu('&File')
        open_action = file_menu.addAction('&Open movie…')
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.file_requested.emit)
        self.open_action = open_action
        file_menu.addAction('&New Station', self.new_station_requested.emit)
        file_menu.addSeparator()
        close = file_menu.addAction('&Close station')
        close.setShortcut(QKeySequence.StandardKey.Close)
        close.triggered.connect(self.close)
        call_menu = menu.addMenu('&Call')
        self.call_action = call_menu.addAction('&Call', self._dial)
        self.answer_action = call_menu.addAction('&Answer', self._listen)
        self.hangup_action = call_menu.addAction('&Hang up', self.hangup_requested.emit)
        view_menu = menu.addMenu('&View')
        self.log_action = view_menu.addAction('Connection &log')
        self.log_action.setCheckable(True)
        self.log_action.toggled.connect(lambda visible: self.log_view.setVisible(visible))
        view_menu.addAction('Connection &information…', self.show_connection_information)
        options = menu.addMenu('&Options')
        options.addAction('&Dependencies…', self.dependencies_requested.emit)
        self.mute_action = options.addAction('&Mute received audio')
        self.mute_action.setCheckable(True)
        self.mute_action.toggled.connect(lambda value: self.mute_checkbox.setChecked(value))
        help_menu = menu.addMenu('&Help')
        help_menu.addAction('&About Modem Conference…', self._about)

    def selected_port(self) -> str:
        return str(self.port_combo.currentData() or '')

    def select_port(self, port: str):
        index = self.port_combo.findData(port)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)

    def set_initial_connection(self, port: str | None, number: str | None = None):
        if port:
            if self.port_combo.findData(port) < 0:
                self.port_combo.addItem(f'Unavailable modem — {port}', port)
                index = self.port_combo.count() - 1
                self.port_combo.setItemData(index, port, Qt.ItemDataRole.ToolTipRole)
            self.select_port(port)
        if number is not None:
            self.number_edit.setText(str(number))

    @Slot(object)
    def set_ports(self, ports: list[tuple[str, str]]):
        selected = self.selected_port()
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        self.port_combo.addItem('Select a modem…', '')
        for path, description in ports:
            self.port_combo.addItem(description or path, path)
            self.port_combo.setItemData(self.port_combo.count() - 1, path, Qt.ItemDataRole.ToolTipRole)
        index = self.port_combo.findData(selected)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)
        self.port_combo.blockSignals(False)
        self._sync_controls()

    def _dial(self):
        if self.call_button.isEnabled():
            self.dial_requested.emit(self.selected_port(), self.number_edit.text().strip())

    def _listen(self):
        if self.answer_button.isEnabled():
            self.listen_requested.emit(self.selected_port())

    def _pause(self):
        self.pause_requested.emit(not self._paused)

    @Slot(str, str)
    def set_state(self, state: str, message: str = ''):
        previous = self._state
        self._state = str(state).lower()
        self.state_label.setText(self._state.replace('_', ' ').capitalize())
        self.connection_label.setText(message or {
            'idle': 'Choose a modem, then call or answer.',
            'listening': 'Waiting for an incoming call…',
            'ringing': 'Incoming call…',
            'dialing': f'Calling {self.number_edit.text().strip()}…',
            'answering': 'Answering incoming call…',
            'connecting': 'Connecting modems…',
            'negotiating': 'Setting up audio and video…',
            'connected': 'Connected. Ready to send and receive.',
            'disconnecting': 'Hanging up…',
            'hanging_up': 'Hanging up…',
            'initializing': 'Preparing modem…',
            'error': 'Connection stopped. See Connection information for details.',
        }.get(self._state, self._state.replace('_', ' ').capitalize()))
        if self._state in {'idle', 'error'}:
            self._capture_video_state = 'stopped'
            self._transmitting = self._paused = False
            self.rate_label.setText('— bps')
            self.time_label.setText('00:00:00')
            for lamp in self.lamps.values():
                lamp.set_active(False)
            self.audio_meter.set_level(0)
            if previous != self._state:
                self.remote_video.set_frame(QImage())
                self.video_details.setText('No incoming video')
        self._sync_controls()

    def _sync_controls(self, *args):
        if not hasattr(self, 'transmit_button'):
            return
        idle = self._state in {'idle', 'error'}
        port_available = bool(self.selected_port())
        call = idle and port_available and bool(self.number_edit.text().strip())
        answer = idle and port_available
        hangup = not idle and self._state not in {'disconnecting', 'hanging_up'}
        for control in (self.call_button, self.call_action):
            control.setEnabled(call)
        for control in (self.answer_button, self.answer_action):
            control.setEnabled(answer)
        for control in (self.hangup_button, self.hangup_action):
            control.setEnabled(hangup)
        self.port_combo.setEnabled(idle)
        self.number_edit.setEnabled(idle)
        self.refresh_button.setEnabled(idle)
        may_browse = not self._preparing and not self._transmitting
        for control in (self.browse_button, self.open_button, self.open_action):
            control.setEnabled(may_browse)
        self.transmit_button.setEnabled(self._state == 'connected' and (bool(self._movie) or self.source_combo.currentData() == 'camera')
                                        and self._dependencies_ready and not self._preparing and not self._transmitting and not self._capture_pending)
        self.source_combo.setEnabled(not self._transmitting)
        self.devices_button.setEnabled(not self._transmitting)
        self.preview_button.setEnabled(self.source_combo.currentData() == 'camera' and not self._transmitting)
        self.pause_button.setEnabled(self._state == 'connected' and self._transmitting)
        self.stop_button.setEnabled(self._capture_pending or self._state == 'connected' and self._transmitting)
        self.pause_button.setText('&Resume' if self._paused else '&Pause')
        if self._movie or self.source_combo.currentData() == 'camera':
            self.outgoing_label.setText('Paused' if self._paused else
                                        f'Sending to {self.number_edit.text().strip()}'
                                        if self._transmitting else 'Ready to transmit')
        if (self.source_combo.currentData() == 'camera' and self._transmitting
                and not self._paused and self._capture_video_state == 'paused'):
            self.outgoing_label.setText('Video paused; audio continues')
            self.movie_details.setText('Video paused; audio continues')

    @Slot(dict)
    def set_telemetry(self, values: dict):
        values = dict(values)
        aliases = {'carrier': 'cd', 'tx_active': 'tx', 'rx_active': 'rx',
                   'media_transmitting': 'transmitting'}
        for source, target in aliases.items():
            if source in values and target not in values:
                values[target] = values[source]
        for source, target in (('media_position_ms', 'sent_seconds'),
                               ('media_duration_ms', 'duration_seconds')):
            if source in values and target not in values:
                values[target] = float(values[source]) / 1000
        self._telemetry.update(values)
        if 'state' in values:
            self.set_state(str(values['state']), str(values.get('message', '')))
        rate = values.get('rate_bps', values.get('rate'))
        if 'rate_bps' in values or 'rate' in values:
            self.rate_label.setText(f'{int(rate):,} bps' if rate is not None and float(rate) > 0 else '— bps')
        elapsed = values.get('elapsed_seconds', values.get('elapsed'))
        if elapsed is not None:
            self.time_label.setText(_time(float(elapsed), hours=True))
        for key, lamp in self.lamps.items():
            if key in values:
                lamp.set_active(values[key])
        if 'transmitting' in values:
            self._transmitting = bool(values['transmitting'])
        if 'paused' in values:
            self._paused = bool(values['paused'])
        if 'audio_level' in values:
            self.set_audio_level(float(values['audio_level']))
        duration = values.get('duration_seconds', (self._movie or {}).get('duration_seconds', 0))
        if 'sent_seconds' in values:
            sent = float(values['sent_seconds'])
            self.movie_progress.setRange(0, 1000)
            self.movie_progress.setValue(round(1000 * sent / float(duration)) if duration else 0)
            if self.source_combo.currentData() == 'camera':
                self.movie_details.setText('Camera + microphone · ' + ('Paused' if self._paused else 'Transmitting' if self._transmitting else 'Ready'))
            else:
                self.movie_details.setText(f'{_time(sent)} / {_time(float(duration))} · '
                                           + ('Paused' if self._paused else 'Transmitting' if self._transmitting else 'Ready'))
        if 'video_description' in values:
            self.video_details.setText(str(values['video_description']))
        if 'peer' in values:
            self.peer_label.setText(f'  Station {values["peer"]}')
        self._sync_controls()
        self._update_diagnostics()

    @Slot(object)
    def set_movie(self, metadata: dict | None):
        self._movie = metadata
        self._transmitting = self._paused = False
        self.movie_progress.setRange(0, 1000)
        self.movie_progress.setValue(0)
        if metadata:
            name = str(metadata.get('name') or metadata.get('title') or Path(str(metadata.get('path', metadata.get('source', 'Movie')))).name)
            self.filename_label.setText(name)
            self.filename_label.setToolTip(str(metadata.get('path', metadata.get('source', name))))
            duration = metadata.get('duration_seconds',
                                    float(metadata.get('duration_ms', 0)) / 1000
                                    if 'duration_ms' in metadata else metadata.get('duration', 0))
            self._movie = {**metadata, 'duration_seconds': duration}
            details = str(metadata.get('description', 'Prepared for the modem connection'))
            self.movie_details.setText(f'{_time(float(duration))} · {details}')
            self.outgoing_label.setText('Ready to transmit')
        else:
            self.filename_label.setText('No movie selected')
            self.filename_label.setToolTip('')
            self.movie_details.setText('Select a movie to prepare it for this connection.')
            self.outgoing_label.setText('No movie selected')
            self.local_video.set_frame(QImage())
        self._sync_controls()

    @Slot(bool, str)
    def set_preparing(self, preparing: bool, message: str = ''):
        self._preparing = preparing
        self.movie_progress.setRange(0, 0 if preparing else 1000)
        if not preparing:
            self.movie_progress.setValue(0)
        if message:
            self.movie_details.setText(message)
        elif not preparing:
            if self._movie:
                duration = float(self._movie.get('duration_seconds', 0))
                description = str(self._movie.get('description', 'Prepared for the modem connection'))
                self.movie_details.setText(f'{_time(duration)} · {description}')
            else:
                self.movie_details.setText('Select a movie to prepare it for this connection.')
        self._sync_controls()

    @Slot(QImage)
    def set_video_frame(self, image: QImage):
        self.remote_video.set_frame(image)
        if not image.isNull():
            self.video_details.setText(f'{image.width()} × {image.height()} pixels · Receiving')

    @Slot(QImage)
    def set_preview_frame(self, image: QImage):
        self.local_video.set_frame(image)

    @Slot(float)
    def set_audio_level(self, level: float):
        self.audio_meter.set_level(level)

    def _mute_toggled(self, muted: bool):
        self.mute_action.blockSignals(True)
        self.mute_action.setChecked(muted)
        self.mute_action.blockSignals(False)
        self.mute_changed.emit(muted)

    @Slot(bool)
    def set_muted(self, muted: bool):
        self.mute_checkbox.blockSignals(True)
        self.mute_checkbox.setChecked(muted)
        self.mute_checkbox.blockSignals(False)
        self.mute_action.blockSignals(True)
        self.mute_action.setChecked(muted)
        self.mute_action.blockSignals(False)

    @Slot(str)
    def append_log(self, line: str):
        self.log_view.appendPlainText(line)

    @Slot(str)
    def show_error(self, message: str):
        self.append_log(f'Error: {message}')
        QMessageBox.warning(self, 'Modem Conference', message)

    def _update_diagnostics(self):
        if self._diagnostics is not None:
            data = {**self._telemetry, 'station': self.station,
                    'port': self.selected_port(), 'state': self._state}
            self._diagnostics.setPlainText(json.dumps(data, indent=2, default=str))

    @Slot()
    def show_connection_information(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Connection information — Station {self.station}')
        dialog.resize(460, 360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Live details reported by this station:'))
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setAccessibleName('Connection details')
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        self._diagnostics = text
        self._update_diagnostics()
        dialog.finished.connect(lambda: setattr(self, '_diagnostics', None))
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()

    def _about(self):
        QMessageBox.about(self, 'About Modem Conference',
                          'Modem Conference\nH.324 dial-up video conferencing laboratory\n\n'
                          'Each station owns one modem and sends its own movie.')

    def closeEvent(self, event: QCloseEvent):
        self.closing.emit()
        super().closeEvent(event)

    def _source_changed(self):
        self._capture_video_state = 'stopped'
        source = self.source_combo.currentData()
        self.source_changed.emit(source)
        if source == 'camera':
            self.filename_label.setText('Camera + microphone')
            self.filename_label.setToolTip('Select capture devices with Devices…')
            self.movie_details.setText('Live capture · 128 × 96 · up to 2 frames/sec')
            self.outgoing_label.setText('Preview or transmit to start capture')
            self.local_video.set_frame(QImage())
        else:
            self.set_movie(self._movie)
        self._sync_controls()

    def set_capture_pending(self, pending):
        self._capture_pending = bool(pending)
        self._sync_controls()

    def set_capture_video_state(self, state):
        self._capture_video_state = state
        if state != 'paused' and self.source_combo.currentData() == 'camera':
            self.movie_details.setText('Camera + microphone · ' + ('Transmitting' if self._transmitting else 'Ready'))
        self._sync_controls()
