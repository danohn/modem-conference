"""Bounded streaming admission and real incremental encoder checks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import shutil
import time
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QProcess

from modem_conference.capture import Capture, PictureParser, VideoBudget


def test_picture_parser_keeps_last_picture_until_next_start():
    parser = PictureParser()
    first, second = b'\0\0\x80abc', b'\0\0\x81def'
    assert parser.feed(first[:2]) == []
    assert parser.feed(first[2:]+second[:2]) == []
    assert parser.feed(second[2:]) == [first]
    assert bytes(parser.data) == second
    with pytest.raises(ValueError):
        parser.feed(b'x'*8192)
    assert not parser.data


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
