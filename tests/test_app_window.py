"""Exercise state-bound UI controls without touching serial devices."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from modem_conference.theme import apply_theme
from modem_conference.window import StationWindow


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    apply_theme(instance)
    return instance


@pytest.fixture
def window(app):
    widget = StationWindow('1001', [('/dev/modem-a', 'USB modem A'),
                                    ('/dev/modem-b', 'USB modem B')])
    yield widget
    widget.close()


def test_independent_station_commands_and_no_port_guard(app):
    first = StationWindow('1001')
    second = StationWindow('1002', [('/dev/b', 'Modem B')])
    assert not first.call_button.isEnabled()
    assert not first.answer_button.isEnabled()
    assert second.number_edit.text() == ''
    second.set_initial_connection('/dev/b', '5550123')
    calls = QSignalSpy(second.dial_requested)
    listens = QSignalSpy(second.listen_requested)
    second.call_button.click()
    second.answer_button.click()
    assert calls.at(0) == ['/dev/b', '5550123']
    assert listens.at(0) == ['/dev/b']
    assert first._state == second._state == 'idle'
    first.close()
    second.close()


def test_lifecycle_blocks_reconfiguration_and_enables_media_only_when_ready(window):
    window.set_initial_connection('/dev/modem-a', '5550123')
    assert window.call_button.isEnabled()
    assert not window.transmit_button.isEnabled()
    window.set_state('initializing')
    assert not window.call_button.isEnabled()
    assert not window.port_combo.isEnabled()
    assert window.hangup_button.isEnabled()
    window.set_state('connected')
    assert not window.transmit_button.isEnabled()
    window.set_preparing(True, 'Converting selected movie…')
    assert not window.browse_button.isEnabled()
    assert window.movie_progress.maximum() == 0
    window.set_movie({'path': '/tmp/example.mov', 'duration_ms': 6500})
    assert not window.transmit_button.isEnabled()
    window.set_preparing(False)
    assert window.transmit_button.isEnabled()
    assert '00:06' in window.movie_details.text()
    window.set_telemetry({'media_transmitting': True, 'paused': False})
    assert not window.transmit_button.isEnabled()
    assert not window.browse_button.isEnabled()
    assert window.pause_button.isEnabled()
    pauses = QSignalSpy(window.pause_requested)
    window.pause_button.click()
    assert pauses.at(0) == [True]
    window.set_telemetry({'paused': True})
    assert window.pause_button.text() == '&Resume'
    window.pause_button.click()
    assert pauses.at(1) == [False]
    window.set_state('hanging_up')
    assert not window.hangup_button.isEnabled()
    window.set_state('idle')
    assert window.port_combo.isEnabled()
    assert not window.stop_button.isEnabled()
    assert not window.pause_button.isEnabled()


def test_actual_telemetry_and_reset_without_invented_counters(window):
    assert window.rate_label.text() == '— bps'
    assert not any(lamp.active for lamp in window.lamps.values())
    window.set_state('connected')
    window.set_movie({'name': 'clip.mov', 'duration_ms': 6000})
    window.set_telemetry({'rate': 14400, 'elapsed': 78, 'carrier': True,
                          'tx_active': False, 'rx_active': True,
                          'media_transmitting': True, 'media_position_ms': 3000,
                          'media_duration_ms': 6000, 'audio_level': 0.5})
    assert window.rate_label.text() == '14,400 bps'
    assert window.time_label.text() == '00:01:18'
    assert window.lamps['cd'].active and window.lamps['rx'].active
    assert not window.lamps['tx'].active
    assert window.movie_progress.value() == 500
    assert window.audio_meter.level == 0.5
    assert '00:03 / 00:06' in window.movie_details.text()
    window.set_telemetry({'rate': None})
    assert window.rate_label.text() == '— bps'
    window.set_state('error', 'Line disconnected')
    assert window.connection_label.text() == 'Line disconnected'
    assert window.rate_label.text() == '— bps'
    assert window.time_label.text() == '00:00:00'
    assert not any(lamp.active for lamp in window.lamps.values())
    assert window.audio_meter.level == 0


def test_port_refresh_retains_choice_and_image_is_copied(window):
    window.select_port('/dev/modem-b')
    window.set_ports([('/dev/modem-c', 'C'), ('/dev/modem-b', 'B')])
    assert window.selected_port() == '/dev/modem-b'
    image = QImage(128, 96, QImage.Format.Format_RGB32)
    image.fill(QColor('red'))
    window.set_video_frame(image)
    image.fill(QColor('blue'))
    assert window.remote_video.image.pixelColor(0, 0) == QColor('red')
    assert '128 × 96' in window.video_details.text()
    window.set_audio_level(float('nan'))
    assert window.audio_meter.level == 0


def test_connection_information_is_nonmodal_and_receives_updates(window):
    window.show_connection_information()
    assert window._diagnostics is not None
    window.set_telemetry({'rate': 14400, 'tx_bytes': 321})
    assert '321' in window._diagnostics.toPlainText()
    assert '14400' in window._diagnostics.toPlainText()
    window._diagnostics.window().close()


def test_programmatic_mute_does_not_emit_user_intent(window):
    changes = QSignalSpy(window.mute_changed)
    window.set_muted(True)
    assert window.mute_checkbox.isChecked()
    assert window.mute_action.isChecked()
    assert changes.count() == 0
    window.mute_checkbox.click()
    assert changes.at(0) == [False]


def test_explicit_unavailable_port_is_visible_instead_of_falling_back(window):
    window.set_initial_connection('/dev/missing-modem', '4321')
    assert window.selected_port() == '/dev/missing-modem'
    assert 'Unavailable modem' in window.port_combo.currentText()
    assert window.number_edit.text() == '4321'


def test_conversion_failure_restores_previous_movie_description(window):
    window.set_movie({'title': 'existing.mov', 'duration_ms': 6000,
                      'description': '128 × 96 pixels'})
    window.set_preparing(True, 'Preparing replacement…')
    assert window.movie_details.text() == 'Preparing replacement…'
    window.set_preparing(False)
    assert window.movie_details.text() == '00:06 · 128 × 96 pixels'
    assert window.filename_label.text() == 'existing.mov'
    window.set_movie(None)
    window.set_preparing(True, 'Preparing first movie…')
    window.set_preparing(False)
    assert window.movie_details.text() == 'Select a movie to prepare it for this connection.'


def test_preview_caption_tracks_runtime_transmission_and_pause(window):
    window.set_movie({'title': 'clip.mov', 'duration_ms': 6000})
    window.set_state('connected')
    window.set_telemetry({'media_transmitting': True})
    assert window.outgoing_label.text() == 'Sending to '
    window.set_telemetry({'paused': True})
    assert window.outgoing_label.text() == 'Paused'
    window.set_telemetry({'media_transmitting': False, 'paused': False})
    assert window.outgoing_label.text() == 'Ready to transmit'
