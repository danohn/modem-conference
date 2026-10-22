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


def test_camera_pause_resume_never_plays_stale_movie_preview(app, tmp_path):
    window = StationWindow('1')
    controller = StationController(window, '1', tmp_path)
    window.source_combo.setCurrentIndex(1)
    commands, played = [], []
    controller.command = commands.append
    controller.preview.play = lambda: played.append(True)
    controller.capture.active = controller.capture.sending = True
    controller.pause(True)
    assert controller.capture.paused
    controller.pause(False)
    assert not controller.capture.paused
    assert commands == [{'op':'pause'}, {'op':'resume'}]
    assert not played
    controller.shutdown()
    assert not controller.capture.active


def test_worker_crash_releases_capture_and_unlocks_source(app, tmp_path):
    window = StationWindow('1')
    controller = StationController(window, '1', tmp_path)
    controller.capture.active = controller.capture.sending = True
    window.set_state('connected')
    window.set_telemetry({'transmitting':True})
    assert not window.source_combo.isEnabled()
    controller._finished(1, QProcess.ExitStatus.CrashExit)
    assert not controller.capture.active
    assert not controller.capture.sending
    assert window.source_combo.isEnabled()
    assert controller.state == 'error'
    controller.shutdown()


def test_hangup_and_remote_teardown_release_capture_before_modem_cleanup(app, tmp_path):
    window = StationWindow('1')
    controller = StationController(window, '1', tmp_path)
    commands = []
    controller.command = commands.append
    controller.capture.active = controller.capture.sending = True
    controller.hangup()
    assert not controller.capture.active
    assert commands == [{'op':'hangup'}]
    controller.capture.active = controller.capture.sending = True
    controller.handle_event({'event':'state','state':'hanging_up'})
    assert not controller.capture.active
    assert controller.state == 'hanging_up'
    controller.shutdown()


def test_stop_pending_preview_keeps_idle_modem_worker_unstarted(app, tmp_path):
    window = StationWindow('1')
    controller = StationController(window, '1', tmp_path)
    window.set_capture_pending(True)
    assert window.stop_button.isEnabled()
    controller.stop_media()
    assert not window._capture_pending
    assert controller.process.state() == QProcess.ProcessState.NotRunning
    controller.shutdown()


def test_shutdown_kills_windows_style_helpers_that_ignore_terminate(app, tmp_path, caplog):
    """No real subprocess or modem: exercise both bounded escalation stages."""
    window = StationWindow('1')
    controller = StationController(window, '1', tmp_path)
    class Unresponsive:
        def __init__(self):
            self.running = True
            self.terminated = self.killed = 0
            self.writes = []
        def state(self):
            return QProcess.ProcessState.Running if self.running else QProcess.ProcessState.NotRunning
        def write(self, data): self.writes.append(data)
        def closeWriteChannel(self): pass
        def terminate(self): self.terminated += 1  # Windows WM_CLOSE ignored.
        def kill(self):
            self.killed += 1
            self.running = False
    worker, converter = Unresponsive(), Unresponsive()
    controller.process, controller.preparer = worker, converter
    controller.shutdown()
    assert controller.shutdown_timer.interval() == 20000
    assert b'"op": "shutdown"' in worker.writes[0]
    assert converter.writes == [b'cancel\n']
    assert not controller._closed
    controller._shutdown_timeout()
    assert worker.terminated == converter.terminated == 1
    assert worker.killed == converter.killed == 0
    assert controller.shutdown_escalation_timer.interval() == 5000
    assert controller.shutdown_escalation_timer.isActive()
    controller._shutdown_kill()
    assert worker.killed == converter.killed == 1
    assert controller._closed and controller.shutdown_forced
    assert not controller.shutdown_escalation_timer.isActive()
    assert 'Cleanup was not confirmed' in caplog.text
    text = (controller.directory/'controller.jsonl').read_text()
    assert '"cleanup_confirmed": false' in text
