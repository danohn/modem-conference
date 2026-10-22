"""Integration checks for Qt process ownership and converter failure handling."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import sys
import time

import pytest
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

from modem_conference.controller import StationController
from modem_conference.window import StationWindow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def until(app, predicate, seconds=5):
    end = time.monotonic() + seconds
    while not predicate() and time.monotonic() < end:
        app.processEvents()
        time.sleep(.005)
    assert predicate()


def test_close_waits_for_running_preparer(app, tmp_path):
    window = StationWindow('1001')
    controller = StationController(window, '1001', tmp_path)
    observed = []
    controller.closed.connect(lambda: observed.append(controller.preparer.state()))
    controller.preparer.start(sys.executable, ['-c', 'import sys; sys.stdin.readline()'])
    until(app, lambda: controller.preparer.state() == QProcess.ProcessState.Running)
    controller.shutdown()
    until(app, lambda: bool(observed))
    assert observed == [QProcess.ProcessState.NotRunning]
    assert controller.log_file.closed
    assert controller.process.state() == QProcess.ProcessState.NotRunning


def test_failed_conversion_preserves_selected_movie(app, tmp_path):
    window = StationWindow('1001')
    errors = []
    window.show_error = errors.append
    controller = StationController(window, '1001', tmp_path)
    old_bundle = tmp_path/'existing-bundle'
    controller.set_bundle(old_bundle, {'source':'previous.mov','duration_ms':6000})
    controller.prepare_file(tmp_path/'missing-video.mp4')
    until(app, lambda: bool(errors))
    assert controller.bundle == old_bundle.resolve()
    assert window.filename_label.text() == 'previous.mov'
    assert 'Preparing' not in window.movie_details.text()
    assert not window._preparing
    assert controller.process.state() == QProcess.ProcessState.NotRunning
    controller.shutdown()
    until(app, lambda: controller.log_file.closed)


def test_idle_start_does_not_open_modem_or_launch_worker(app, tmp_path):
    window = StationWindow('1002', [('/dev/test-modem','Test modem')])
    controller = StationController(window, '1002', tmp_path)
    assert controller.process.state() == QProcess.ProcessState.NotRunning
    assert not controller.call_directory
    assert window.selected_port() == ''
    controller.shutdown()
    assert controller.log_file.closed
