"""Permission decisions exercise the actual callback/context contract, no devices."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCameraPermission, QMicrophonePermission, QObject, Qt

from modem_conference import devices


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
    selection.selected = lambda: (object(), object(), None)
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
