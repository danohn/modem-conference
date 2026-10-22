"""Bounded streaming admission and real incremental encoder checks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import shutil
import time
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QProcess

from modem_conference.capture import Capture, VideoBudget


def test_stopping_capture_discards_partial_local_container_state():
    capture = Capture()
    assert capture.video_parser.feed(b'RIFF') == []
    assert capture.video_parser.buffered_bytes == 4
    capture.stop()
    assert capture.video_parser.buffered_bytes == 0


def test_high_motion_whole_picture_rejected_then_low_motion_recovers():
    bucket = VideoBudget()
    assert not bucket.admit(1800, 0)
    assert bucket.admit(400, 2)
    assert not bucket.admit(400, 2.1)
    assert bucket.admit(200, 2.6)
    assert bucket.credit >= 0


def test_audio_state_slot_avoids_qt_alias_conversion_and_queries_source():
    capture = Capture()
    assert capture.metaObject().indexOfSlot('_audio_state()') >= 0
    states = []
    capture.audio_state.connect(states.append)
    capture.audio = SimpleNamespace(state=lambda: SimpleNamespace(name='ActiveState'))
    capture._audio_state()
    assert states == ['ActiveState']
    capture.audio = None


def test_late_camera_and_microphone_callbacks_cannot_enter_restarted_capture():
    capture = Capture()
    old_generation = capture._generation
    capture.stop()
    capture.active = True
    class Unexpected:
        def isValid(self):
            pytest.fail('Stale camera frame inspected after restart')
        def readAll(self):
            pytest.fail('Stale microphone read after restart')
    capture.audio_io = Unexpected()
    capture._frame(Unexpected(), old_generation)
    capture._audio_ready(old_generation, capture.audio_io)
    capture._audio_ready(capture._generation, Unexpected())
    capture.stop()
    capture._audio_ready()  # Queued callback after audio_io was released.


def test_retired_camera_error_and_frame_signals_do_not_affect_new_preview(monkeypatch):
    import modem_conference.capture as module
    class Signal:
        def __init__(self): self.callbacks = []
        def connect(self, callback): self.callbacks.append(callback)
        def emit(self, *args):
            for callback in self.callbacks: callback(*args)
    class Camera:
        def __init__(self, *args): self.errorOccurred = Signal()
        def start(self): pass
        def stop(self): pass
        def deleteLater(self): pass
    class Session:
        def __init__(self, *args): self.sink = None
        def setCamera(self, camera): pass
        def setVideoSink(self, sink): self.sink = sink
        def deleteLater(self): pass
    class Sink:
        def __init__(self, *args): self.videoFrameChanged = Signal()
    monkeypatch.setattr(module, 'QCamera', Camera)
    monkeypatch.setattr(module, 'QMediaCaptureSession', Session)
    monkeypatch.setattr(module, 'QVideoSink', Sink)
    capture = Capture()
    errors = []
    capture.error.connect(errors.append)
    capture.start(object(), None, transmit=False)
    retired_camera, retired_sink = capture.camera, capture.session.sink
    capture.stop()
    capture.start(object(), None, transmit=False)
    retired_camera.errorOccurred.emit(None, 'retired camera error')
    retired_sink.videoFrameChanged.emit(object())
    assert capture.active
    assert not errors
    capture.camera.errorOccurred.emit(None, 'current camera error')
    assert errors == ['current camera error']
    assert not capture.active


def test_video_pause_clears_only_after_an_admitted_picture_then_stop():
    capture = Capture()
    states = []
    capture.video_state.connect(states.append)
    capture.active = True
    capture.pause_video()
    assert states == ['paused']
    capture.reset_video()
    assert states == ['paused']  # Deadline reset alone is not an actual picture.
    process = SimpleNamespace(readAllStandardOutput=lambda: b'encoded')
    capture.video_parser = SimpleNamespace(feed=lambda data:[b'picture'], reset=lambda:None)
    capture.encoders[2] = process
    capture._encoded(2, process, capture._generation)
    assert states == ['paused','resumed']
    capture.encoders.clear()
    capture.stop()
    assert states[-1] == 'stopped'


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg required')
def test_first_encoded_picture_is_delivered_without_another_frame_or_eof():
    app = QApplication.instance() or QApplication([])
    capture = Capture()
    capture.active = capture.sending = True
    capture.started_at = time.monotonic()
    chunks, errors = [], []
    capture.chunk.connect(chunks.append)
    capture.error.connect(errors.append)
    capture._video_encoder()
    deadline = time.monotonic()+5
    try:
        encoder = capture.encoders[2]
        while encoder.state() != QProcess.ProcessState.Running:
            app.processEvents(); time.sleep(.005)
            assert time.monotonic() < deadline
        encoder.write(bytes([64,96,128])*(128*96))
        # The old elementary-picture parser could never pass this assertion:
        # it withheld this picture until another picture start or stream EOF.
        while not chunks:
            app.processEvents(); time.sleep(.005)
            assert time.monotonic() < deadline, errors
        assert len(chunks) == 1
        assert chunks[0]['lcn'] == 2
        assert chunks[0]['payload'][:2] == b'\0\0'
        assert not chunks[0]['payload'].startswith(b'RIFF')
        assert encoder.state() == QProcess.ProcessState.Running
        assert not errors
    finally:
        capture.stop()
        end = time.monotonic()+.7
        while time.monotonic()<end:
            app.processEvents(); time.sleep(.005)


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg required')
def test_actual_incremental_camera_encoders_and_video_restart_keep_audio_alive():
    app = QApplication.instance() or QApplication([])
    capture = Capture()
    capture.active = capture.sending = True
    capture.started_at = time.monotonic()
    chunks, errors = [], []
    capture.chunk.connect(chunks.append); capture.error.connect(errors.append)
    capture._video_encoder()
    capture._encoder(1, ['-f','s16le','-ar','8000','-ac','1','-i','pipe:0',
                          '-c:a','g723_1','-b:a','6300','-f','g723_1','-flush_packets','1','pipe:1'])
    deadline = time.monotonic()+5
    try:
        while any(p.state() != QProcess.ProcessState.Running for p in capture.encoders.values()):
            app.processEvents(); time.sleep(.005)
            assert time.monotonic() < deadline
        audio = capture.encoders[1]
        audio.write(b'\0'*(8000*2*3))
        capture.encoders[2].write(bytes([64,96,128])*(128*96*4))
        while not any(c['lcn']==1 for c in chunks) or not any(c['lcn']==2 for c in chunks):
            app.processEvents(); time.sleep(.005)
            assert time.monotonic() < deadline, (errors, chunks)
        before = sum(c['lcn']==1 for c in chunks)
        capture.pause_video('overload')
        assert capture.encoders[1] is audio
        assert 2 not in capture.encoders
        audio.write(b'\0'*(8000*2*3))
        capture.reset_video(); capture._video_encoder()
        while sum(c['lcn']==1 for c in chunks) <= before:
            app.processEvents(); time.sleep(.005)
            assert time.monotonic() < deadline
        assert not errors
        assert all(len(c['payload'])==24 for c in chunks if c['lcn']==1)
        assert all(c['payload'].startswith(b'\0\0') for c in chunks if c['lcn']==2)
    finally:
        capture.stop()
        end = time.monotonic()+1
        while time.monotonic()<end:
            app.processEvents(); time.sleep(.005)
