"""Device selection, permission prompts, and dependency configuration."""
from PySide6.QtCore import (QCameraPermission, QCoreApplication,
                           QMicrophonePermission, Qt)
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout)

from . import dependencies
from .settings import load_settings, save_settings


def device_id(device):
    return bytes(device.id()).hex()


class DeviceSelection:
    def __init__(self, owner):
        self.owner = owner
        self.media = QMediaDevices(owner)
        stored = load_settings()
        self.values = {key: stored.get(f'{key}_{owner.station}', '')
                       for key in ('camera', 'microphone', 'speakers')}
        self._capture_generation = 0
        self._capture_pending = False
        owner.capture.stopped.connect(self.cancel_capture_request)
        self.media.videoInputsChanged.connect(self.changed)
        self.media.audioInputsChanged.connect(self.changed)
        self.media.audioOutputsChanged.connect(self.changed)

    def selected(self):
        groups = (QMediaDevices.videoInputs(), QMediaDevices.audioInputs(), QMediaDevices.audioOutputs())
        result = []
        for key, devices in zip(("camera", "microphone", "speakers"), groups):
            matches = [d for d in devices if device_id(d) == self.values.get(key)]
            result.append(matches[0] if len(matches) == 1 else None)
        return result

    def changed(self):
        self.cancel_capture_request()
        camera, mic, speakers = self.selected()
        if self.owner.capture.active and (camera is None or self.owner.capture.sending and mic is None):
            self.owner.capture_error("Selected capture device was removed; transmission stopped. Select a device again.")
        self.owner.playback.selected_output = speakers
        if speakers is None and self.values.get("speakers"):
            self.owner.playback.set_audio_enabled(False)
            self.owner.window.append_log("Selected speakers were removed; received audio muted.")

    def dialog(self):
        if self.owner.capture.sending:
            self.owner.window.show_error('Stop transmission before changing capture devices.')
            return
        self.cancel_capture_request()
        dialog = QDialog(self.owner.window)
        dialog.setWindowTitle("Camera, microphone and speakers")
        form = QFormLayout(dialog)
        combos = []
        groups = (QMediaDevices.videoInputs(), QMediaDevices.audioInputs(), QMediaDevices.audioOutputs())
        for key, devices in zip(("camera", "microphone", "speakers"), groups):
            combo = QComboBox()
            combo.addItem("Select a device…", "")
            for device in devices:
                combo.addItem(device.description(), device_id(device))
            combo.setCurrentIndex(max(0, combo.findData(self.values.get(key, ""))))
            form.addRow(key.capitalize(), combo)
            combos.append((key, combo))
        form.addRow(QLabel("Use headphones for calls. Acoustic echo cancellation is not included."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.owner.capture.stop()
            self.values.update({key: combo.currentData() for key, combo in combos})
            self.persist()
            self.changed()

    def persist(self):
        stored = load_settings()
        stored.update({f'{key}_{self.owner.station}': value for key, value in self.values.items()})
        save_settings(stored)

    def capture(self, transmit):
        if getattr(self, '_capture_pending', False):
            self.cancel_capture_request()
            return
        import sys
        if sys.platform == 'darwin':
            from .macos_launcher import has_usage_descriptions
            if not has_usage_descriptions():
                self.owner.window.show_error('macOS camera capture requires an application bundle. '
                    'Use the native Modem Conference.app, or run '
                    'modem-conference --install-macos-launcher and open the generated app. '
                    'This supplies usage descriptions for the normal macOS permission prompt.')
                return
        camera, microphone, _ = self.selected()
        if camera is None or transmit and microphone is None:
            self.dialog()
            camera, microphone, _ = self.selected()
        if camera is None or transmit and microphone is None:
            self.owner.window.show_error("Select an available camera and microphone in Devices first.")
            return
        self._capture_generation = getattr(self, '_capture_generation', 0)+1
        generation = self._capture_generation
        self._capture_pending = True
        self._pending_ui(True)
        requested_state = getattr(self.owner, 'state', None)
        def identity(device):
            return device_id(device) if hasattr(device, 'id') else id(device)
        requested_devices = (identity(camera), identity(microphone) if transmit else None)
        def current():
            if (not self._capture_pending or self._capture_generation != generation
                    or getattr(self.owner, 'closing', False)
                    or getattr(self.owner, 'state', None) != requested_state):
                return False
            source = getattr(self.owner.window, 'source_combo', None)
            if source is not None and source.currentData() != 'camera':
                return False
            selected_camera, selected_microphone, _ = self.selected()
            return (selected_camera is not None and (not transmit or selected_microphone is not None)
                    and (identity(selected_camera), identity(selected_microphone) if transmit else None) == requested_devices)
        permissions = [QCameraPermission()]
        if transmit:
            permissions.append(QMicrophonePermission())
        def granted(index=0):
            if not current():
                return
            if index == len(permissions):
                self.cancel_capture_request()
                self.owner.start_capture(camera, microphone, transmit)
                return
            app = QCoreApplication.instance()
            permission = permissions[index]
            state = app.checkPermission(permission)
            if state == Qt.PermissionStatus.Granted:
                granted(index+1)
            elif state == Qt.PermissionStatus.Denied:
                self.cancel_capture_request()
                self.owner.window.show_error("Capture permission denied. Enable camera/microphone access in system settings.")
            else:
                def answered(result):
                    if not current():
                        return
                    if result.status() == Qt.PermissionStatus.Granted:
                        granted(index+1)
                    else:
                        self.cancel_capture_request()
                        self.owner.window.show_error("Capture permission was not granted.")
                app.requestPermission(permission, self.owner, answered)
        granted()

    def _pending_ui(self, pending):
        method = getattr(self.owner.window, 'set_capture_pending', None)
        if method:
            method(pending)

    def cancel_capture_request(self):
        self._capture_generation = getattr(self, '_capture_generation', 0)+1
        self._capture_pending = False
        self._pending_ui(False)


def dependencies_dialog(window):
    values = load_settings()
    dialog = QDialog(window)
    dialog.setWindowTitle("FFmpeg dependencies")
    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    fields = {}
    for name in ("ffmpeg", "ffprobe"):
        edit = QLineEdit(values.get(name, ""))
        edit.setPlaceholderText("Search PATH")
        fields[name] = edit
        form.addRow(name, edit)
    layout.addLayout(form)
    status = QLabel("Install an FFmpeg build with H.263, G.723.1, MPEG-4, AAC and PNG.\n"
                    "macOS: brew install ffmpeg\nUbuntu: sudo apt install ffmpeg\n"
                    "Windows: download an FFmpeg build from ffmpeg.org and add its bin directory to PATH.")
    status.setWordWrap(True); layout.addWidget(status)
    check = QPushButton("Save and check")
    def run():
        values.update({name: field.text().strip() for name, field in fields.items()})
        save_settings(values)
        status.setText(dependencies.check().detail)
    check.clicked.connect(run); layout.addWidget(check)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    dialog.exec()
