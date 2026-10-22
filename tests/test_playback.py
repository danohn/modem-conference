"""Audio starts independently of video, without opening actual output devices."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from modem_conference.playback import Playback


class Decoded:
    def __init__(self, data): self.data = data
    def readAllStandardOutput(self):
        data, self.data = self.data, b''
        return data


def test_audio_before_video_plays_and_later_video_still_displays(monkeypatch):
    app = QApplication.instance() or QApplication([])
    playback = Playback(audio_enabled=True)
    playback._running = True
    writes, opened, pictures = [], [], []
    class Output:
        def write(self, data): writes.append(data); return len(data)
    class Sink:
        def bytesFree(self): return 4096
        def stop(self): pass
        def deleteLater(self): pass
    def open_fake():
        if not playback._audio_enabled:
            return
        opened.append(True)
        playback._sink, playback._audio_device = Sink(), Output()
    monkeypatch.setattr(playback, '_open_audio', open_fake)
    playback.video_frame.connect(pictures.append)
    pcm = b'\x01\0'*240
    playback._decoded(1, Decoded(pcm), playback._generation)
    assert opened == [True]
    assert playback._playing
    assert not playback._frames
    playback._playout()
    assert writes == [pcm]  # No video was ever needed to begin audio.
    playback._frames.append(QImage(128, 96, QImage.Format.Format_RGB888))
    playback._playout()
    assert len(pictures) == 1
    assert opened == [True]
    playback.stop()


def test_muted_audio_without_video_can_be_unmuted_without_waiting_for_video(monkeypatch):
    app = QApplication.instance() or QApplication([])
    playback = Playback(audio_enabled=False)
    playback._running = True
    opened = []
    monkeypatch.setattr(playback, '_open_audio', lambda: opened.append(playback._audio_enabled))
    playback._decoded(1, Decoded(b'\0\0'*240), playback._generation)
    assert playback._playing
    assert not playback._pcm  # Muted playback retains no queued sound.
    assert not opened
    playback.set_audio_enabled(True)
    assert opened[-1] is True
    assert not playback._frames
    playback.stop()
