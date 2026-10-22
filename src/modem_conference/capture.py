"""Explicit Qt camera/microphone capture and bounded incremental encoding.

Only complete encoded video pictures leave this object. Raw camera frames may
be dropped before encoding. Congestion restarts the encoder, yielding INTRA.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, QProcess, QTimer, Qt, Signal, Slot
from PySide6.QtMultimedia import (QAudioFormat, QAudioSource, QCamera,
                                 QMediaCaptureSession, QVideoSink)

from .dependencies import binary
from h324.media import AviPictureParser



class VideoBudget:
    """Conservative codec-byte bucket beneath the 4,800 bit/s capability."""
    def __init__(self):
        self.credit = 600.0
        self.updated = None

    def admit(self, size, now):
        if self.updated is not None:
            self.credit = min(600., self.credit + max(0., now-self.updated)*450.)
        self.updated = now
        if size > self.credit:
            return False
        self.credit -= size
        return True


class Capture(QObject):
    frame = Signal(object)
    chunk = Signal(dict)
    error = Signal(str)
    status = Signal(str)
    stopped = Signal()
    audio_state = Signal(str)
    video_state = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera = None
        self.audio = None
        self.session = None
        self.audio_io = None
        self.encoders = {}
        self.video_parser = AviPictureParser()
        self.audio_bytes = bytearray()
        self.budget = VideoBudget()
        self.sending = False
        self.paused = False
        self.started_at = 0.
        self.last_frame = 0.
        self.video_paused_until = 0.
        self.audio_index = 0
        self.active = False
        self._video_paused = False
        self._generation = 0

    def start(self, camera_device, audio_device, *, transmit=False):
        self.stop()
        self._generation += 1
        self.active, self.sending = True, transmit
        self.started_at = time.monotonic()
        generation = self._generation
        self.last_frame = 0
        self.audio_index = 0
        self.budget = VideoBudget()
        self.session = QMediaCaptureSession(self)
        self.camera = QCamera(camera_device, self)
        camera = self.camera
        self.camera.errorOccurred.connect(lambda _code, message:
            self._fail(message) if generation == self._generation and self.active and self.camera is camera else None)
        self.session.setCamera(self.camera)
        sink = QVideoSink(self.session)
        sink.videoFrameChanged.connect(lambda frame: self._frame(frame, generation))
        self.session.setVideoSink(sink)
        if transmit:
            self._video_encoder()
            fmt = audio_device.preferredFormat()
            formats = {QAudioFormat.SampleFormat.UInt8: "u8",
                       QAudioFormat.SampleFormat.Int16: "s16le",
                       QAudioFormat.SampleFormat.Int32: "s32le",
                       QAudioFormat.SampleFormat.Float: "f32le"}
            raw = formats.get(fmt.sampleFormat())
            if not raw:
                self._fail("Microphone sample format is unsupported")
                return
            self._encoder(1, ["-f", raw, "-ar", str(fmt.sampleRate()), "-ac", str(fmt.channelCount()),
                             "-i", "pipe:0", "-ac", "1", "-ar", "8000", "-c:a", "g723_1",
                             "-b:a", "6300", "-f", "g723_1", "-flush_packets", "1", "pipe:1"])
            self.audio = QAudioSource(audio_device, fmt, self)
            self.audio.setBufferSize(max(4096, fmt.bytesForDuration(120_000)))
            self.audio.stateChanged.connect(self._audio_state)
            self.audio_io = self.audio.start()
            if self.audio_io is None:
                self._fail("Cannot start the selected microphone")
                return
            audio_io = self.audio_io
            self.audio_io.readyRead.connect(lambda: self._audio_ready(generation, audio_io))
        self.camera.start()

    def _encoder(self, channel, args):
        process = QProcess(self)
        process.setProgram(binary("ffmpeg"))
        process.setArguments(["-hide_banner", "-loglevel", "error", "-nostdin", "-probesize", "32", "-analyzeduration", "0", "-threads", "1", *args])
        generation = self._generation
        process.readyReadStandardOutput.connect(lambda: self._encoded(channel, process, generation))
        process.readyReadStandardError.connect(lambda: self._stderr(process, generation))
        process.errorOccurred.connect(lambda _code: self._fail(process.errorString()) if generation == self._generation and self.encoders.get(channel) is process else None)
        process.finished.connect(lambda code, _status: self._fail(f"Capture encoder exited ({code})")
                                 if generation == self._generation and self.active and self.encoders.get(channel) is process else None)
        process.finished.connect(process.deleteLater)
        self.encoders[channel] = process
        process.start()

    def _video_encoder(self):
        self.video_parser = AviPictureParser()
        self._encoder(2, ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "128x96", "-r", "2",
                          "-i", "pipe:0", "-an", "-c:v", "h263", "-pix_fmt", "yuv420p",
                          "-b:v", "3500", "-maxrate", "4800", "-bufsize", "4800",
                          "-qmin", "12", "-qmax", "31", "-g", "12", "-threads", "1",
                          "-tag:v", "H263", "-f", "avi", "-flush_packets", "1", "pipe:1"])

    def _frame(self, frame, generation=None):
        if not self.active or generation is not None and generation != self._generation or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self.frame.emit(image)
        now = time.monotonic()
        if not self.sending or self.paused or now < self.video_paused_until or now-self.last_frame < .5:
            return
        process = self.encoders.get(2)
        if not process:
            self._video_encoder()
            process = self.encoders[2]
        if process.state() != QProcess.ProcessState.Running or process.bytesToWrite() > 128*96*3:
            return  # Drop stale RAW frame, never an encoded fragment.
        from PySide6.QtGui import QImage
        image = image.scaled(128, 96, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_RGB888)
        raw = bytes(image.constBits())
        # RGB888 row alignment is exact at width 128.
        process.write(raw[:128*96*3])
        self.last_frame = now

    def _audio_ready(self, generation=None, audio_io=None):
        if (not self.active or self.audio_io is None
                or generation is not None and generation != self._generation
                or audio_io is not None and audio_io is not self.audio_io):
            return
        data = bytes(self.audio_io.readAll())
        process = self.encoders.get(1)
        if not process or self.paused:
            return
        if process.bytesToWrite() + len(data) > 256_000:
            self._fail("Microphone encoder fell behind; transmission stopped")
            return
        process.write(data)

    def _encoded(self, channel, process, generation):
        data = bytes(process.readAllStandardOutput())
        if generation != self._generation or not self.active or self.encoders.get(channel) is not process:
            return
        if channel == 1:
            self.audio_bytes.extend(data)
            while len(self.audio_bytes) >= 24:
                payload = bytes(self.audio_bytes[:24]); del self.audio_bytes[:24]
                self.chunk.emit(dict(lcn=1, payload=payload, timestamp_ms=self.audio_index*30, duration_ms=30))
                self.audio_index += 1
        else:
            try:
                for picture in self.video_parser.feed(data):
                    if not self.budget.admit(len(picture), time.monotonic()):
                        self.pause_video("Picture exceeds dial-up budget; video paused, audio continues")
                        break
                    if self._video_paused:
                        self._video_paused = False
                        self.video_state.emit('resumed')
                    self.chunk.emit(dict(lcn=2, payload=picture,
                                         timestamp_ms=round((time.monotonic()-self.started_at)*1000), duration_ms=500))
            except ValueError as exc:
                self.pause_video(str(exc))

    def _stderr(self, process, generation):
        detail = bytes(process.readAllStandardError()).decode(errors="replace").strip()
        if detail and generation == self._generation:
            self.status.emit(detail[:500])

    @Slot()
    def _audio_state(self):
        # PySide6 6.12 cannot marshal QAudio::State into a dynamic Python slot
        # on all backends. A registered zero-argument slot avoids converting
        # that alias; query the owning source for state/error instead.
        sender = self.sender()
        if sender is not None and sender is not self.audio:
            return
        if self.audio:
            self.audio_state.emit(self.audio.state().name)
        if self.active and self.audio and self.audio.error().value:
            self._fail(f"Microphone error: {self.audio.error().name}")

    def pause_video(self, message="Video congested; waiting for a fresh picture"):
        self.video_paused_until = time.monotonic()+2
        self._video_paused = True
        self.video_state.emit('paused')
        self.status.emit(message)
        process = self.encoders.pop(2, None)
        if process:
            process.closeWriteChannel()
            process.terminate()
            QTimer.singleShot(500, process, process.kill)
        self.video_parser = AviPictureParser()

    def reset_video(self):
        self.video_paused_until = time.monotonic()

    def _fail(self, message):
        self.error.emit(message)
        self.stop()

    def stop(self):
        self.active = self.sending = self.paused = False
        self._video_paused = False
        self.video_state.emit('stopped')
        self._generation += 1
        if self.camera:
            self.camera.stop()
            self.camera.deleteLater()
        if self.audio:
            self.audio.stop()
            self.audio.deleteLater()
        if self.session:
            self.session.deleteLater()
        self.camera = self.audio = self.session = self.audio_io = None
        for process in self.encoders.values():
            process.closeWriteChannel()
            process.terminate()
            QTimer.singleShot(500, process, process.kill)
        self.encoders.clear()
        self.audio_bytes.clear()
        self.video_parser.reset()
        self.stopped.emit()
