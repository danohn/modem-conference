"""Permission decisions exercise the actual callback/context contract, no devices."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCameraPermission, QMicrophonePermission, QObject, Qt

from modem_conference import devices


@pytest.fixture(autouse=True)
def bundled_permission_context(monkeypatch):
    monkeypatch.setattr('modem_conference.macos_launcher.has_usage_descriptions', lambda: True)


@pytest.mark.parametrize('transmit,permission_count', [(False,1), (True,2)])
def test_permission_callback_has_qobject_context_and_only_starts_after_grants(monkeypatch, transmit, permission_count):
    errors, starts, prompts = [], [], []
    owner = QObject()
    owner.window = SimpleNamespace(show_error=errors.append)
    owner.start_capture = lambda *args: starts.append(args)
    class App:
        def checkPermission(self, permission):
            return Qt.PermissionStatus.Undetermined
        # PySide6 6.12 requires this THREE-argument overload.
        def requestPermission(self, permission, context, callback):
            assert context is owner
            assert not starts
            prompts.append(type(permission))
            callback(SimpleNamespace(status=lambda: Qt.PermissionStatus.Granted))
    monkeypatch.setattr(devices, 'QCoreApplication', SimpleNamespace(instance=lambda: App()))
    selection = object.__new__(devices.DeviceSelection)
    selection.owner = owner
    camera, microphone = object(), object()
    selection.selected = lambda: (camera, microphone, None)
    selection.capture(transmit)
    assert len(prompts) == permission_count
    assert prompts[0] is QCameraPermission
    if transmit:
        assert prompts[1] is QMicrophonePermission
    assert starts == [(camera, microphone, transmit)]
    assert not errors


def test_denied_capture_permission_never_starts_or_substitutes(monkeypatch):
    errors, starts = [], []
    owner = QObject()
    owner.window = SimpleNamespace(show_error=errors.append)
    owner.start_capture = lambda *args: starts.append(args)
    app = SimpleNamespace(checkPermission=lambda permission: Qt.PermissionStatus.Denied)
    monkeypatch.setattr(devices, 'QCoreApplication', SimpleNamespace(instance=lambda: app))
    selection = object.__new__(devices.DeviceSelection)
    selection.owner = owner
    camera, microphone = object(), object()
    selection.selected = lambda: (camera, microphone, None)
    selection.capture(True)
    assert not starts
    assert errors and 'denied' in errors[0]


def test_active_transmission_blocks_device_reconfiguration():
    errors = []
    selection = object.__new__(devices.DeviceSelection)
    selection.owner = SimpleNamespace(capture=SimpleNamespace(sending=True),
                                      window=SimpleNamespace(show_error=errors.append))
    selection.dialog()
    assert errors == ['Stop transmission before changing capture devices.']


def test_device_settings_are_station_specific_and_preserve_other_settings(monkeypatch):
    saved = []
    original = {'ffmpeg':'tool', 'port_1':'usb:1:2:serial', 'camera_2':'other-camera'}
    monkeypatch.setattr(devices, 'load_settings', lambda: dict(original))
    monkeypatch.setattr(devices, 'save_settings', saved.append)
    selection = object.__new__(devices.DeviceSelection)
    selection.owner = SimpleNamespace(station='1')
    selection.values = {'camera':'my-camera', 'microphone':'my-mic', 'speakers':'my-speakers'}
    selection.persist()
    assert saved == [{**original, 'camera_1':'my-camera', 'microphone_1':'my-mic', 'speakers_1':'my-speakers'}]


@pytest.mark.parametrize('action', ['stop','disconnect','source','close','device'])
def test_late_permission_grant_cannot_restart_capture_after_cancellation(monkeypatch, action):
    from modem_conference.capture import Capture
    starts, callbacks, pending = [], [], []
    owner = QObject()
    mode = ['camera']
    owner.window = SimpleNamespace(show_error=lambda message: pytest.fail(message),
        source_combo=SimpleNamespace(currentData=lambda: mode[0]), set_capture_pending=pending.append)
    owner.state = 'connected'
    owner.closing = False
    owner.capture = Capture(owner)
    owner.start_capture = lambda *args: starts.append(args)
    app = SimpleNamespace(checkPermission=lambda permission: Qt.PermissionStatus.Undetermined,
        requestPermission=lambda permission, context, callback: callbacks.append(callback))
    monkeypatch.setattr(devices, 'QCoreApplication', SimpleNamespace(instance=lambda: app))
    selection = object.__new__(devices.DeviceSelection)
    selection.owner = owner
    selected = [object(), object(), None]
    selection.selected = lambda: tuple(selected)
    owner.capture.stopped.connect(selection.cancel_capture_request)
    selection.capture(True)
    assert pending[-1] is True
    assert len(callbacks) == 1
    if action == 'disconnect':
        owner.state = 'idle'
    elif action == 'source':
        mode[0] = 'file'
    elif action == 'close':
        owner.closing = True
    elif action == 'device':
        selected[0] = object()
    owner.capture.stop()
    callbacks[0](SimpleNamespace(status=lambda: Qt.PermissionStatus.Granted))
    assert not starts
    assert len(callbacks) == 1  # No subsequent microphone prompt either.
    assert pending[-1] is False


def test_second_preview_cancels_pending_permission_instead_of_prompting_twice(monkeypatch):
    from modem_conference.capture import Capture
    callbacks, starts = [], []
    owner = QObject()
    owner.window = SimpleNamespace(show_error=lambda message: pytest.fail(message))
    owner.capture = Capture(owner)
    owner.start_capture = lambda *args: starts.append(args)
    camera, microphone = object(), object()
    selection = object.__new__(devices.DeviceSelection)
    selection.owner = owner
    selection.selected = lambda: (camera, microphone, None)
    owner.capture.stopped.connect(selection.cancel_capture_request)
    app = SimpleNamespace(checkPermission=lambda permission: Qt.PermissionStatus.Undetermined,
        requestPermission=lambda permission, context, callback: callbacks.append(callback))
    monkeypatch.setattr(devices, 'QCoreApplication', SimpleNamespace(instance=lambda: app))
    selection.capture(False)
    selection.capture(False)
    callbacks[0](SimpleNamespace(status=lambda: Qt.PermissionStatus.Granted))
    assert not starts
    assert len(callbacks) == 1
