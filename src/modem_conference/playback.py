"""Incremental FFmpeg decoders and bounded Qt playout for received codec bytes.

Only elementary G.723.1 / H.263 bytes enter this class, after AL CRC and sequence
checks. Each decoder has a permanently open input pipe while a call is active;
small explicit probe sizes are essential at dial-up rates. No decoder waits for
the whole selected file. Audio output defaults to muted to avoid two stations
playing on the same Mac simultaneously.
"""
from __future__ import annotations

from array import array
from collections import deque
import math
import shutil
import sys
import time

from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

WIDTH, HEIGHT, RGB_BYTES = 128, 96, 128 * 96 * 3
MAX_ENCODED_BUFFER = 32768
MAX_PCM_BUFFER = 32000  # two seconds, signed 16-bit mono / 8 kHz
MAX_VIDEO_FRAMES = 6   # three seconds; overload is visible, never unbounded


class Playback(QObject):
    video_frame = Signal(QImage)
    audio_level = Signal(float)
    error = Signal(str)
    # Useful for diagnostics/tests; emitted even when speakers are muted.
    audio_decoded = Signal(bytes)

    def __init__(self, parent: QObject | None = None, *, audio_enabled: bool = False):
        super().__init__(parent)
        self._processes: dict[int, QProcess] = {}
        self._pending: dict[int, bytearray] = {1: bytearray(), 2: bytearray()}
        self._video_bytes = bytearray()
        self._audio_bytes = bytearray()
        self._frames: deque[QImage] = deque()
        self._pcm = bytearray()
        self._sink: QAudioSink | None = None
        self._audio_device = None
        self.selected_output = None
        self._audio_enabled = audio_enabled
        self._playing = False
        self._running = False
        self._generation = 0
        self._next_picture = 0.0
        self._reported: set[str] = set()
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._playout)

    @property
    def buffered_bytes(self) -> int:
        return (sum(len(v) for v in self._pending.values()) + len(self._video_bytes) + len(self._pcm)
                + len(self._audio_bytes)
                + len(self._frames) * RGB_BYTES
                + sum(p.bytesToWrite() for p in self._processes.values()))

    @property
    def running(self) -> bool:
        return self._running

    def _report(self, message: str) -> None:
        if message not in self._reported:
            self._reported.add(message)
            self.error.emit(message)

    def set_audio_enabled(self, enabled: bool) -> None:
        self._audio_enabled = bool(enabled)
        if not enabled:
            self._close_audio()
            self._pcm.clear()
        elif self._playing:
            self._open_audio()

    def start(self) -> None:
        if self._running:
            return
        from .dependencies import binary as find_binary
        try:
            binary = find_binary('ffmpeg')
        except ValueError:
            binary = None
        if not binary:
            self._report('FFmpeg was not found; received media cannot be decoded.')
            return
        self._generation += 1
        generation = self._generation
        self._running = True
        self._reported.clear()
        self._playing = False
        self._next_picture = 0
        for lcn, demux in ((1, 'g723_1'), (2, 'h263')):
            process = QProcess(self)
            process.setProgram(binary)
            output = (['-vn', '-f', 's16le', '-ac', '1', '-ar', '8000'] if lcn == 1 else
                      ['-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-fps_mode', 'passthrough'])
            process.setArguments(['-hide_banner', '-loglevel', 'error', '-f', demux,
                '-probesize', '32', '-analyzeduration', '0', '-i', 'pipe:0',
                '-threads', '1', *output, '-flush_packets', '1', 'pipe:1'])
            process.readyReadStandardOutput.connect(
                lambda channel=lcn, child=process, gen=generation: self._decoded(channel, child, gen))
            process.readyReadStandardError.connect(
                lambda channel=lcn, child=process, gen=generation: self._stderr(channel, child, gen))
            process.started.connect(lambda channel=lcn, gen=generation: self._flush_pending(channel, gen))
            process.errorOccurred.connect(
                lambda _code, child=process, gen=generation: self._process_error(child, gen))
            process.finished.connect(
                lambda code, _status, channel=lcn, child=process, gen=generation:
                    self._finished(channel, child, gen, code))
            self._processes[lcn] = process
            process.start()
        self._timer.start()

    def feed(self, lcn: int, payload: bytes) -> None:
        if lcn not in (1, 2):
            raise ValueError('Playback accepts only audio LCN 1 or video LCN 2.')
        if not payload:
            return
        process = self._processes.get(lcn)
        if self._running and process and process.state() == QProcess.ProcessState.Running:
            if process.bytesToWrite() + len(payload) > MAX_ENCODED_BUFFER:
                self._report('Decoder input overloaded; received media was dropped.')
                return
            process.write(bytes(payload))
        else:
            pending = self._pending[lcn]
            if len(pending) + len(payload) > MAX_ENCODED_BUFFER:
                self._report('Decoder startup buffer is full; received media was dropped.')
                return
            pending.extend(payload)

    def _flush_pending(self, lcn: int, generation: int) -> None:
        if generation != self._generation or not self._running:
            return
        pending = self._pending[lcn]
        if pending:
            self._processes[lcn].write(bytes(pending))
            pending.clear()

    def _decoded(self, lcn: int, process: QProcess, generation: int) -> None:
        data = bytes(process.readAllStandardOutput())
        if generation != self._generation or not self._running:
            return
        if lcn == 2:
            self._video_bytes.extend(data)
            while len(self._video_bytes) >= RGB_BYTES:
                frame = bytes(self._video_bytes[:RGB_BYTES])
                del self._video_bytes[:RGB_BYTES]
                if len(self._frames) == MAX_VIDEO_FRAMES:
                    self._frames.popleft()
                    self._report('Video playback fell behind; the oldest decoded frame was dropped.')
                self._frames.append(QImage(frame, WIDTH, HEIGHT, WIDTH * 3, QImage.Format.Format_RGB888).copy())
        else:
            self._audio_bytes.extend(data)
            count = len(self._audio_bytes) // 2 * 2
            data = bytes(self._audio_bytes[:count])
            del self._audio_bytes[:count]
            if not data:
                return
            if sys.byteorder == 'big':
                converted = array('h'); converted.frombytes(data); converted.byteswap()
                data = converted.tobytes()
            self.audio_decoded.emit(data)
            samples = array('h'); samples.frombytes(data[:len(data) // 2 * 2])
            level = math.sqrt(sum(s * s for s in samples) / max(1, len(samples))) / 32768
            self.audio_level.emit(min(1.0, level))
            if self._audio_enabled:
                self._pcm.extend(data)
                if len(self._pcm) > MAX_PCM_BUFFER:
                    del self._pcm[:len(self._pcm) - MAX_PCM_BUFFER]
                    self._report('Audio playback fell behind; old decoded samples were dropped.')

    def _stderr(self, lcn: int, process: QProcess, generation: int) -> None:
        detail = bytes(process.readAllStandardError()).decode(errors='replace').strip()
        if generation == self._generation and self._running and detail:
            self._report(f'{"Audio" if lcn == 1 else "Video"} decoder: {detail[:600]}')

    def _process_error(self, process: QProcess, generation: int) -> None:
        if generation == self._generation and self._running:
            self._report(f'Media decoder failed: {process.errorString()}')

    def _finished(self, lcn: int, process: QProcess, generation: int, code: int) -> None:
        self._decoded(lcn, process, generation)
        if generation == self._generation and self._running and code:
            self._report(f'Media decoder exited with status {code}.')
        if self._processes.get(lcn) is process:
            self._processes.pop(lcn)
        process.deleteLater()

    def _open_audio(self) -> None:
        if self._sink or not self._audio_enabled:
            return
        device = self.selected_output or QMediaDevices.defaultAudioOutput()
        if device.isNull():
            self._report('No speaker output is available; received audio remains muted.')
            self._audio_enabled = False
            self._pcm.clear()
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(8000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            self._report('Speaker output does not support 8 kHz mono PCM; received audio remains muted.')
            self._audio_enabled = False
            self._pcm.clear()
            return
        self._sink = QAudioSink(device, fmt, self)
        self._sink.setBufferSize(8000)
        self._sink.setVolume(0.6)
        self._audio_device = self._sink.start()

    def _close_audio(self) -> None:
        if self._sink:
            self._sink.stop()
            self._sink.deleteLater()
        self._sink = None
        self._audio_device = None

    def _playout(self) -> None:
        if not self._running:
            return
        now = time.monotonic()
        if self._frames and (not self._playing or now >= self._next_picture):
            if not self._playing:
                self._playing = True
                self._open_audio()
            self.video_frame.emit(self._frames.popleft())
            self._next_picture = now + 0.5
        if self._playing and self._audio_enabled and self._audio_device and self._sink and self._pcm:
            count = min(self._sink.bytesFree(), len(self._pcm))
            count -= count % 2
            if count:
                written = self._audio_device.write(bytes(self._pcm[:count]))
                if written > 0:
                    del self._pcm[:written]

    def finish(self) -> None:
        """Flush a completed stream without blocking; a future stream needs start().

        A continuous call normally leaves input open. H.263's final picture is
        decoded when another picture starts; finish supplies EOF at call end.
        """
        for process in self._processes.values():
            process.closeWriteChannel()

    def stop(self) -> None:
        self._running = False
        self._generation += 1
        self._timer.stop()
        self._playing = False
        self._close_audio()
        self._pcm.clear()
        self._frames.clear()
        self._video_bytes.clear()
        self._audio_bytes.clear()
        for pending in self._pending.values():
            pending.clear()
        for process in self._processes.values():
            process.closeWriteChannel()
            if process.state() != QProcess.ProcessState.NotRunning:
                process.terminate()
                QTimer.singleShot(500, process, process.kill)
        self._processes.clear()
        self.audio_level.emit(0.0)
