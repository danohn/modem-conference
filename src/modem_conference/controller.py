"""Qt coordinator; each station owns one isolated modem worker process."""
from __future__ import annotations

import base64
import datetime as dt
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
from serial.tools import list_ports

from .helper import command as helper_command
from .settings import load_settings, save_settings, serial_devices, device_identity, directories
from .dependencies import check as check_dependencies


def available_ports():
    """Show real device paths; identical USB serial numbers are not identities."""
    return [(p.device, f'{p.description} — {p.device}') for p in serial_devices()]


class StationController(QObject):
    closed = Signal()
    event_received = Signal(dict)

    def __init__(self, window, station, log_root, parent=None):
        super().__init__(parent)
        from modem_conference.playback import Playback
        from .capture import Capture
        from .devices import DeviceSelection, dependencies_dialog
        self.window, self.station = window, str(station)
        self.directory = Path(log_root) / f'station-{station}'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.log_file = (self.directory / 'controller.jsonl').open('a')
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._stdout)
        self.process.readyReadStandardError.connect(self._stderr)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.buffer = bytearray()
        self.pending_commands = []
        self.process.started.connect(self._started)
        self.preparer = QProcess(self)
        self.preparer.finished.connect(self._prepared)
        self.preparer.errorOccurred.connect(self._prepare_error)
        self.preparing_path = None
        self.bundle = None
        self.movie = None
        self.state = 'idle'
        self.closing = False
        self._closed = False
        self.call_number = 0
        self.call_directory = None
        self.received_files = {}
        self.playback = Playback(self)
        self.playback.video_frame.connect(window.set_video_frame)
        self.playback.audio_level.connect(window.set_audio_level)
        self.playback.error.connect(self._playback_error)
        self.capture = Capture(self)
        self.capture.frame.connect(window.set_preview_frame)
        self.capture.chunk.connect(self.live_chunk)
        self.capture.error.connect(self.capture_error)
        self.capture.status.connect(window.append_log)
        self.devices = DeviceSelection(self)
        self.raw_capture = False
        window.preview_requested.connect(self.preview_capture)
        self.capture.stopped.connect(lambda: window.preview_button.setText('Pre&view'))
        window.devices_requested.connect(self.devices.dialog)
        window.dependencies_requested.connect(self.configure_dependencies)
        self.check_dependencies()
        window.source_changed.connect(lambda _: self.capture.stop())
        self.preview = QMediaPlayer(self)
        self.preview_sink = QVideoSink(self)
        self.preview.setVideoSink(self.preview_sink)
        self.preview_sink.videoFrameChanged.connect(self._preview_frame)
        window.dial_requested.connect(lambda port, number: self.begin('dial', port, number))
        window.listen_requested.connect(lambda port: self.begin('listen', port))
        window.hangup_requested.connect(self.hangup)
        window.file_requested.connect(self.choose_file)
        window.send_requested.connect(self.send_movie)
        window.pause_requested.connect(self.pause)
        window.stop_requested.connect(self.stop_media)
        window.refresh_requested.connect(lambda: window.set_ports(available_ports()))
        window.mute_changed.connect(self.set_muted)
        window.closing.connect(self.shutdown)
        self.shutdown_timer = QTimer(self)
        self.shutdown_timer.setSingleShot(True)
        self.shutdown_timer.timeout.connect(self._shutdown_timeout)

    def log(self, event, **fields):
        if not self.log_file.closed:
            self.log_file.write(json.dumps(dict(time=dt.datetime.now(dt.timezone.utc).isoformat(),
                                               event=event, **fields)) + '\n')
            self.log_file.flush()

    def command(self, value):
        if self.closing and value['op'] not in ('shutdown', 'hangup'):
            return
        logged = {k: v for k, v in value.items() if k != 'payload'}
        self.log('command', command=logged)
        if self.process.state() == QProcess.ProcessState.NotRunning:
            if value['op'] in ('shutdown', 'hangup'):
                if self.closing:
                    self._maybe_finish_close()
                return
            self.pending_commands.append(value)
            program, arguments = helper_command('worker', ['--station', self.station])
            self.process.start(program, arguments)
        elif self.process.state() == QProcess.ProcessState.Starting:
            self.pending_commands.append(value)
        else:
            self.process.write((json.dumps(dict(protocol_version=1, **value)) + '\n').encode())

    def _started(self):
        for value in self.pending_commands:
            self.process.write((json.dumps(dict(protocol_version=1, **value)) + '\n').encode())
        self.pending_commands.clear()

    def begin(self, operation, port, number=None):
        if self.state not in ('idle', 'error') or self.closing:
            return
        if not port:
            self.window.show_error('Select a modem first, then choose Call or Answer.')
            return
        if number is not None:
            import re
            if not re.fullmatch(r'[0-9*#]+', number):
                self.window.show_error('Enter a telephone number using digits, * or #.')
                return
        settings = load_settings()
        device = next((d for d in serial_devices() if d.device == port), None)
        settings[f'port_{self.station}'] = device_identity(device) if device else f'path:{port}'
        if number is not None:
            settings[f'number_{self.station}'] = number
        save_settings(settings)
        self.call_number += 1
        self.call_directory = self.directory / f'call-{self.call_number:03d}'
        # Worker creates this new directory, owns its modem, and records cleanup.
        self._close_received()
        self.window.set_state('initializing', 'Initializing modem…')
        self.state = 'initializing'
        request = dict(op=operation, port=port, number=number, station=self.station)
        if self.raw_capture:
            request['log_dir'] = str(self.call_directory.resolve())
        self.command(request)

    def _stdout(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        if len(self.buffer) > 2_000_000:
            self.window.show_error('Modem worker sent an oversized response; ending the call.')
            self.buffer.clear()
            self.command({'op': 'hangup'})
            return
        while b'\n' in self.buffer:
            line, _, rest = self.buffer.partition(b'\n')
            self.buffer = bytearray(rest)
            if not line:
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict) or value.get('protocol_version') != 1 or not isinstance(value.get('event'), str):
                    raise ValueError('event object required')
                self.handle_event(value)
            except (ValueError, KeyError, TypeError) as exc:
                self.log('ipc_error', message=str(exc), line=line[:200].decode(errors='replace'))
                self.window.append_log(f'Worker response error: {exc}')

    def _stderr(self):
        data = bytes(self.process.readAllStandardError()).decode(errors='replace')
        for line in data.splitlines():
            self.log('worker_stderr', message=line)
            self.window.append_log(line)

    def handle_event(self, value):
        kind = value['event']
        if kind != 'media':
            self.log('worker_event', data=value)
        if kind == 'state':
            if value['state'] != self.state:
                self.devices.cancel_capture_request()
            self.state = value['state']
            self.window.set_state(self.state, value.get('message', ''))
            if self.state == 'connected':
                self.playback.start()
            elif self.state in ('idle', 'error', 'hanging_up', 'disconnecting'):
                self.preview.stop()
                self.capture.stop()
                self.playback.stop()
                self._close_received()
        elif kind == 'telemetry':
            telemetry = dict(value)
            telemetry.update(cd=value.get('carrier', False), tx=value.get('tx_active', False),
                             rx=value.get('rx_active', False),
                             sent_seconds=value.get('media_position_ms', 0) / 1000,
                             duration_seconds=value.get('media_duration_ms', 0) / 1000,
                             transmitting=value.get('media_transmitting', False))
            self.window.set_telemetry(telemetry)
        elif kind == 'media':
            lcn = int(value['lcn'])
            if lcn not in (1, 2):
                raise ValueError('unknown media channel')
            payload = base64.b64decode(value['payload'], validate=True)
            if not 0 < len(payload) <= 4096:
                raise ValueError('media payload outside bounds')
            if self.raw_capture and self.call_directory is not None:
                self.call_directory.mkdir(parents=True, exist_ok=True)
                if lcn not in self.received_files:
                    suffix = 'audio.g723' if lcn == 1 else 'video.h263'
                    self.received_files[lcn] = (self.call_directory / f'gui-received-{suffix}').open('ab')
                self.received_files[lcn].write(payload)
                self.received_files[lcn].flush()
            self.playback.feed(lcn, payload)
        elif kind == 'media_started':
            if self.window.source_combo.currentData() == 'file':
                self.preview.setPosition(0)
                self.preview.play()
            self.window.set_telemetry({'transmitting': True, 'paused': False})
        elif kind == 'media_finished':
            self.preview.pause()
            if self.capture.sending:
                self.capture.stop()
            self.window.set_telemetry({'transmitting': False, 'paused': False})
        elif kind == 'video_overload':
            self.capture.pause_video()
        elif kind == 'video_reset':
            self.capture.reset_video()
        elif kind == 'error':
            self.window.show_error(value.get('message', 'The modem worker reported an error.'))
        elif kind == 'log':
            self.window.append_log(value.get('message', ''))
        elif kind == 'closed':
            self._close_received()
        self.event_received.emit(value)

    def _close_received(self):
        for file in self.received_files.values():
            file.close()
        self.received_files.clear()

    def choose_file(self):
        from PySide6.QtWidgets import QFileDialog
        source, _ = QFileDialog.getOpenFileName(self.window, 'Open movie', '',
                                                'Movies (*.mp4 *.mov *.mkv *.avi *.webm *.h263);;All files (*)')
        if source:
            self.prepare_file(Path(source))

    def prepare_file(self, source):
        if self.preparer.state() != QProcess.ProcessState.NotRunning or self.closing:
            return
        name = dt.datetime.now(dt.timezone.utc).strftime('movie-%Y%m%dT%H%M%S%fZ')
        self.preparing_path = directories()['cache'] / f'station-{self.station}' / name
        self.window.set_preparing(True, 'Preparing movie for 14,400 bps…')
        self.log('preparation_started', source=str(source), output=str(self.preparing_path))
        program, arguments = helper_command('prepare', [str(source), str(self.preparing_path)])
        self.preparer.start(program, arguments)

    def _prepared(self, exit_code, exit_status):
        stdout = bytes(self.preparer.readAllStandardOutput()).decode(errors='replace')
        stderr = bytes(self.preparer.readAllStandardError()).decode(errors='replace')
        self.window.set_preparing(False)
        if self.closing:
            self._maybe_finish_close()
            return
        if exit_code != 0:
            self.log('preparation_failed', message=stderr or stdout)
            self.window.show_error((stderr or stdout or 'Movie preparation failed.').strip()[-1800:])
            return
        try:
            metadata = json.loads(stdout)
            self.set_bundle(self.preparing_path, metadata)
        except (ValueError, OSError) as exc:
            self.window.show_error(f'Could not read the prepared movie: {exc}')

    def set_bundle(self, path, metadata=None):
        path = Path(path).resolve()
        if metadata is None:
            metadata = json.loads((path / 'manifest.json').read_text())
        self.bundle, self.movie = path, metadata
        ui_metadata = dict(metadata, bundle_path=str(path))
        self.window.set_movie(ui_metadata)
        preview = path / 'preview.mp4'
        if preview.exists():
            self.preview.setSource(QUrl.fromLocalFile(str(preview)))
            self.preview.setPosition(0)
        poster = path / 'poster.png'
        if poster.exists():
            from PySide6.QtGui import QImage
            self.window.set_preview_frame(QImage(str(poster)))
        self.log('movie_ready', bundle=str(path), metadata=metadata)

    def _prepare_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.window.set_preparing(False)
            if self.closing:
                self._maybe_finish_close()
            else:
                self.window.show_error('Could not start the movie converter. Check the Python installation.')

    def send_movie(self):
        status = check_dependencies()
        if not status.ready:
            self.window.show_error(status.detail)
            return
        if self.window.source_combo.currentData() == 'camera':
            if self.state == 'connected':
                self.devices.capture(True)
            return
        if self.bundle is not None and self.state == 'connected':
            self.command(dict(op='send', bundle=str(self.bundle)))

    def pause(self, paused):
        self.capture.paused = paused
        self.command(dict(op='pause' if paused else 'resume'))
        if self.window.source_combo.currentData() == 'file':
            if paused:
                self.preview.pause()
            else:
                self.preview.play()

    def stop_media(self):
        self.capture.stop()
        if self.state == 'connected':
            self.command({'op': 'stop_media'})
        self.preview.stop()

    def hangup(self):
        self.capture.stop()
        self.command({'op':'hangup'})

    def set_muted(self, muted):
        self.playback.selected_output = self.devices.selected()[2]
        if not muted and self.devices.values.get('speakers') and self.playback.selected_output is None:
            self.window.append_log('Selected speakers are unavailable; choose an output in Devices.')
            self.window.set_muted(True)
            return
        self.playback.set_audio_enabled(not muted)

    def _preview_frame(self, frame):
        if frame.isValid():
            image = frame.toImage()
            if not image.isNull():
                self.window.set_preview_frame(image)

    def _playback_error(self, message):
        self.log('playback_error', message=message)
        self.window.append_log(f'Playback: {message}')

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.capture.stop()
            self.pending_commands.clear()
            self.state = 'error'
            self.window.set_state('error', 'Could not start modem worker')
            self.window.show_error(self.process.errorString())
            if self.closing:
                self._maybe_finish_close()

    def _finished(self, code, status):
        self.capture.stop()
        self._stdout()
        self._stderr()
        self._close_received()
        self.playback.stop()
        self.preview.stop()
        self.pending_commands.clear()
        self.buffer.clear()
        self.log('worker_finished', exit_code=code, exit_status=str(status))
        if self.closing:
            self._maybe_finish_close()
        elif code:
            self.state = 'error'
            self.window.set_state('error', f'Modem worker exited ({code})')
        else:
            self.state = 'idle'
            self.window.set_state('idle')

    def shutdown(self):
        if self.closing:
            return
        self.closing = True
        self.capture.stop()
        self.preview.stop()
        self.playback.stop()
        if self.preparer.state() != QProcess.ProcessState.NotRunning:
            self.preparer.write(b'cancel\n')
            self.preparer.closeWriteChannel()
        self.command({'op': 'shutdown'})
        self.shutdown_timer.start(20000)
        self._maybe_finish_close()

    def _maybe_finish_close(self):
        if self.closing and self.process.state() == QProcess.ProcessState.NotRunning and self.preparer.state() == QProcess.ProcessState.NotRunning:
            self._finish_close()

    def _finish_close(self):
        if self._closed:
            return
        self._closed = True
        self.shutdown_timer.stop()
        self._close_received()
        self.log('controller_closed')
        self.log_file.close()
        self.closed.emit()

    def _shutdown_timeout(self):
        # Terminate first: the worker handles SIGTERM with its modem cleanup.
        self.log('shutdown_timeout', message='Requesting worker termination after graceful shutdown timeout')
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
        if self.preparer.state() != QProcess.ProcessState.NotRunning:
            self.preparer.kill()
        self._maybe_finish_close()

    def start_capture(self, camera, microphone, transmit):
        if self.closing or self.window.source_combo.currentData() != 'camera' or transmit and self.state != 'connected':
            return
        if transmit:
            self.command({'op': 'live_start', 'label': 'Camera + microphone'})
            self.window.set_telemetry({'transmitting': True, 'paused': False})
        try:
            self.capture.start(camera, microphone, transmit=transmit)
            if not transmit:
                self.window.preview_button.setText('Stop pre&view')
        except (ValueError, OSError, RuntimeError, TypeError) as exc:
            self.capture_error(str(exc))

    def live_chunk(self, chunk):
        if self.state != 'connected' or not self.capture.sending:
            return
        if self.process.bytesToWrite() > 65536:
            self.capture_error('Modem worker input overloaded; capture stopped.')
            return
        value = dict(chunk)
        value['payload'] = base64.b64encode(value['payload']).decode('ascii')
        self.command(dict(op='live_chunk', **value))

    def capture_error(self, message):
        self.capture.stop()
        if self.state == 'connected':
            self.command({'op': 'live_stop'})
        self.window.set_telemetry({'transmitting': False, 'paused': False})
        self.window.show_error(message)

    def preview_capture(self):
        if self.capture.active:
            self.capture.stop()
        else:
            self.devices.capture(False)

    def check_dependencies(self):
        status = check_dependencies()
        self.window._dependencies_ready = status.ready
        self.window._sync_controls()
        if not status.ready:
            self.window.append_log(status.detail)
        return status

    def configure_dependencies(self):
        from .devices import dependencies_dialog
        dependencies_dialog(self.window)
        self.check_dependencies()
