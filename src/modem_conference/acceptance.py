#!/usr/bin/env python
"""Explicit, portable manual hardware acceptance and camera-encoder stress.

Run with the project environment: uv run --no-sync scripts/manual_acceptance.py
--help. Hardware mode opens only the ports/devices explicitly requested here.
Reports contain counts and diagnostics, never received media recordings.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import json
import os
from pathlib import Path
import random
import sys
import subprocess
import time
import tracemalloc

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication, QLabel

from modem_conference.capture import Capture
from modem_conference.controller import StationController, available_ports
from modem_conference.theme import apply_theme
from modem_conference.window import StationWindow


def accepted_bearer(inband_rate, carrier_report):
    """Accept actual rate evidence, preserving its origin rather than a setting."""
    if inband_rate is not None:
        if inband_rate != 14400:
            return None
        return {'source': 'V.80 in-band', 'tx_bps': 14400, 'rx_bps': 14400}
    if not isinstance(carrier_report, dict):
        return None
    required = {'source': 'AT+MRR', 'validated': True, 'phase': 'connect',
                'modulation': 'V32B', 'tx_bps': 14400, 'rx_bps': 14400, 'connect_bps': 14400}
    if any(carrier_report.get(key) != value for key, value in required.items()):
        return None
    # Revalidate the literal carrier reports independently of the worker flag.
    from h324.modem import parse_carrier_report
    parsed = parse_carrier_report([carrier_report.get(key, '')
                                   for key in ('raw_mcr', 'raw_mrr', 'raw_connect')])
    if parsed != carrier_report:
        return None
    return dict(carrier_report)


class CaptureMetrics:
    """Counters and bounded diagnostic history, without retaining media."""
    def __init__(self):
        self.preview_frames = 0
        self.outgoing_frames = {1: 0, 2: 0}
        self.outgoing_bytes = {1: 0, 2: 0}
        self.status_counts = Counter()
        self.status_history = deque(maxlen=100)
        self.overload_status_count = 0
        self.worker_video_overloads = 0
        self.started_at = None
        self.ended_at = None

    def preview(self, _image):
        self.preview_frames += 1

    def outgoing(self, chunk, started_at):
        self.started_at = self.started_at if self.started_at is not None else started_at
        channel = int(chunk['lcn'])
        self.outgoing_frames[channel] += 1
        self.outgoing_bytes[channel] += len(chunk['payload'])

    def status(self, message):
        text = str(message)[:500]
        key = text if text in self.status_counts or len(self.status_counts) < 32 else '[other statuses]'
        self.status_counts[key] += 1
        self.status_history.append(text)
        if any(word in text.lower() for word in ('overload', 'budget', 'congest')):
            self.overload_status_count += 1

    def snapshot(self):
        return {'audio_frames':self.outgoing_frames[1], 'video_pictures':self.outgoing_frames[2]}

    def summary(self):
        duration = max(0., self.ended_at-self.started_at) if self.ended_at is not None and self.started_at is not None else 0.
        expected = int(duration*1000/30)
        return {'preview_frames':self.preview_frames, 'outgoing_frames':dict(self.outgoing_frames),
                'outgoing_bytes':dict(self.outgoing_bytes), 'status_counts':dict(self.status_counts),
                'status_history':list(self.status_history), 'overload_status_count':self.overload_status_count,
                'worker_video_overloads':self.worker_video_overloads, 'capture_duration_seconds':duration,
                'expected_audio_frames':expected,
                'audio_output_ratio':self.outgoing_frames[1]/max(1, expected)}


def rss_bytes(pids):
    """Sample parent and encoder RSS, with no optional Python dependency."""
    if sys.platform != 'win32':
        try:
            values = subprocess.check_output(['ps', '-o', 'rss=', '-p', ','.join(map(str, pids))],
                                             stderr=subprocess.DEVNULL, timeout=2)
            return sum(int(value)*1024 for value in values.split())
        except (OSError, subprocess.SubprocessError):
            return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                    *[(name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    total, measured = 0, False
    for pid in pids:
        handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if handle:
            counters = Counters(); counters.cb = ctypes.sizeof(counters)
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                total += counters.WorkingSetSize; measured = True
            kernel.CloseHandle(handle)
    return total if measured else None


def stress(args, app):
    """Exercise actual FFmpeg encoders without requesting an OS capture device."""
    capture = Capture()
    progress = QLabel('Modem Conference encoder acceptance\nGenerated RGB/PCM · no capture devices opened')
    progress.setWindowTitle('Continuous encoder acceptance')
    progress.resize(460, 90)
    progress.show()
    capture.active = capture.sending = True
    capture.started_at = time.monotonic()
    capture._video_encoder()
    capture._encoder(1, ['-f','s16le','-ar','8000','-ac','1','-i','pipe:0',
                          '-c:a','g723_1','-b:a','6300','-f','g723_1',
                          '-flush_packets','1','pipe:1'])
    counts = {1: 0, 2: 0}
    report = {'mode': 'synthetic-encoder-stress', 'seconds': args.seconds,
              'hardware_devices_opened': False, 'control_transport_tested': False,
              'errors': [], 'statuses': [], 'max_encoder_children': 0,
              'max_pending_input_bytes': 0, 'max_encoded_parser_bytes': 0,
              'rss_samples': [], 'peak_combined_rss_bytes': 0}
    report['audio_input_pcm_bytes'] = 0
    tracemalloc.start()
    def chunk(value):
        counts[value['lcn']] += 1
    capture.chunk.connect(chunk)
    capture.error.connect(report['errors'].append)
    capture.status.connect(lambda value: report['statuses'].append(value) if len(report['statuses']) < 1000 else None)
    began = time.monotonic()
    last_video = began
    audio_before_recovery = None
    rng = random.Random(324)
    forced = False
    last_rss = 0
    def tick():
        nonlocal last_video, forced, audio_before_recovery, last_rss
        now = time.monotonic()
        elapsed = now-began
        if elapsed >= args.seconds or report['errors']:
            capture.stop()
            progress.close()
            timer.stop()
            QTimer.singleShot(700, app.quit)
            return
        audio = capture.encoders.get(1)
        if audio and audio.state() == QProcess.ProcessState.Running:
            # Cumulative sample clock: timer jitter must not silently reduce the
            # simulated microphone rate. Catch up bounded gaps or fail visibly.
            expected_bytes = int(min(elapsed, args.seconds)*8000)*2
            missing = expected_bytes-report['audio_input_pcm_bytes']
            if missing > 16000 or audio.bytesToWrite()+missing > 64000:
                report['errors'].append('Synthetic microphone clock fell over one second behind or input queue overflowed')
                return
            if missing > 0:
                written = audio.write(b'\0'*missing)
                if written != missing:
                    report['errors'].append('Could not enqueue all generated PCM samples')
                    return
                report['audio_input_pcm_bytes'] += written
        if elapsed > 3 and not forced:
            forced = True
            audio_before_recovery = counts[1]
            capture.pause_video('Deliberate overload/restart acceptance probe')
        if 2 not in capture.encoders and now >= capture.video_paused_until:
            capture._video_encoder()
        video = capture.encoders.get(2)
        if video and video.state() == QProcess.ProcessState.Running and now-last_video >= .5:
            # Alternate high motion and a quiet scene so recovery is observable.
            data = (rng.randbytes(128*96*3) if 10 <= elapsed % 60 < 12
                    else bytes([64,96,128])*(128*96))
            if video.bytesToWrite() < 128*96*3:
                video.write(data)
            last_video = now
        children = capture.findChildren(QProcess)
        report['max_encoder_children'] = max(report['max_encoder_children'], len(children))
        report['max_pending_input_bytes'] = max(report['max_pending_input_bytes'],
                                                sum(p.bytesToWrite() for p in capture.encoders.values()))
        report['max_encoded_parser_bytes'] = max(report['max_encoded_parser_bytes'], len(capture.video_parser.data))
        if now-last_rss >= 5:
            last_rss = now
            rss = rss_bytes([os.getpid(), *[int(p.processId()) for p in capture.encoders.values() if p.processId()]])
            report['rss_samples'].append({'elapsed': round(elapsed, 1), 'combined_rss_bytes': rss})
            report['peak_combined_rss_bytes'] = max(report['peak_combined_rss_bytes'], rss or 0)
            progress.setText(f'Encoder acceptance: {elapsed:.0f} / {args.seconds:g} seconds\n'
                             f'Audio frames: {counts[1]:,} · Video pictures: {counts[2]:,}')
    timer = QTimer()
    timer.timeout.connect(tick); timer.start(10)
    app.exec()
    _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    report.update(audio_frames=counts[1], video_pictures=counts[2],
                  audio_continued_after_restart=audio_before_recovery is not None and counts[1] > audio_before_recovery,
                  peak_python_heap_bytes=peak, elapsed_seconds=time.monotonic()-began,
                  note='Python heap plus sampled parent/FFmpeg combined RSS; inspect RSS trend for long-run growth.')
    report['audio_input_duration_seconds'] = report['audio_input_pcm_bytes']/16000
    report['expected_audio_frames'] = int(args.seconds*1000/30)
    report['audio_output_ratio'] = counts[1]/max(1, report['expected_audio_frames'])
    report['passed'] = (not report['errors'] and counts[1] > 0 and counts[2] > 0
                        and report['audio_continued_after_restart']
                        and report['audio_output_ratio'] >= .90
                        and report['max_encoder_children'] <= 4
                        and report['max_pending_input_bytes'] < 256_000)
    return report


def hardware(args, app):
    if not args.caller_port or not args.answerer_port or not args.number:
        raise ValueError('Hardware mode requires --caller-port, --answerer-port and --number.')
    if args.caller_port == args.answerer_port:
        raise ValueError('The stations need separate serial ports.')
    modes = args.mode.split('/')
    if args.exercise_video_overload and 'camera' not in modes:
        raise ValueError('--exercise-video-overload requires at least one camera source.')
    bundles = [args.bundle1, args.bundle2]
    for mode, bundle in zip(modes, bundles):
        if mode == 'file' and not bundle:
            raise ValueError('Provide a prepared --bundle1/--bundle2 for every file source.')
    report = {'mode': args.mode, 'errors': [], 'stations': {}, 'seconds': args.seconds,
              'received': {'1': {1: 0, 2: 0}, '2': {1: 0, 2: 0}},
              'decoded': {'1': {'audio_bytes':0, 'video_frames':0}, '2': {'audio_bytes':0, 'video_frames':0}},
              'rates': {}, 'inband_rates': {}, 'carrier_reports': {}, 'bearers': {}, 'cleanup': {},
              'capture': {}, 'forced_video_probes': {}, 'peak_combined_rss_bytes':0}
    capture_metrics = {label:CaptureMetrics() for label in ('1','2')}
    rss_history = deque(maxlen=200)
    events = deque(maxlen=2000)
    root = args.output.parent / (args.output.stem+'-diagnostics')
    controllers = []
    windows = []
    for index, port in enumerate((args.caller_port, args.answerer_port)):
        label = str(index+1)
        window = StationWindow(label, available_ports())
        window.set_initial_connection(port, args.number if index == 0 else '')
        window.show_error = lambda message, station=label: report['errors'].append({'station':station,'message':message})
        controller = StationController(window, label, root)
        controller.set_muted(True); window.set_muted(True)
        if modes[index] == 'file':
            controller.set_bundle(bundles[index])
        else:
            window.source_combo.setCurrentIndex(1)
            for name in ('camera', 'microphone'):
                value = getattr(args, f'{name}{index+1}')
                if value:
                    controller.devices.values[name] = value
        def event(value, label=label):
            if value['event'] == 'media':
                report['received'][label][int(value['lcn'])] += 1
            else:
                events.append({'station': label, **value})
            if value['event'] in ('telemetry', 'cleanup'):
                if 'rate' in value:
                    report['inband_rates'][label] = value['rate']
                if value.get('carrier_report') is not None:
                    report['carrier_reports'][label] = value['carrier_report']
                evidence = accepted_bearer(report['inband_rates'].get(label),
                                            report['carrier_reports'].get(label))
                report['bearers'][label] = evidence
                report['rates'][label] = evidence['tx_bps'] if evidence else None
            if value['event'] == 'cleanup':
                report['cleanup'][label] = value
            elif value['event'] == 'video_overload':
                capture_metrics[label].worker_video_overloads += 1
        controller.event_received.connect(event)
        def audio(data, label=label):
            report['decoded'][label]['audio_bytes'] += len(data)
        def video(_image, label=label):
            report['decoded'][label]['video_frames'] += 1
        controller.playback.audio_decoded.connect(audio)
        controller.playback.video_frame.connect(video)
        metrics = capture_metrics[label]
        controller.capture.frame.connect(metrics.preview)
        controller.capture.status.connect(metrics.status)
        controller.capture.chunk.connect(lambda chunk, c=controller, m=metrics: m.outgoing(chunk, c.capture.started_at))
        controllers.append(controller); windows.append(window)
        window.show()
    started = time.monotonic()
    transmitting = None
    closing = False
    completed_duration = False
    last_rss = 0.
    def close():
        nonlocal closing
        if not closing:
            closing = True
            for controller in controllers:
                capture_metrics[controller.station].ended_at = time.monotonic()
                controller.shutdown()
    def tick():
        nonlocal transmitting, completed_duration, last_rss
        now = time.monotonic()
        if closing:
            if all(c._closed for c in controllers):
                timer.stop(); app.quit()
            return
        if report['errors'] or now-started > 100+args.seconds:
            if not report['errors']:
                report['errors'].append({'message':'Call setup or transmission timed out'})
            close(); return
        if transmitting is None and all(c.state == 'connected' for c in controllers):
            transmitting = now
            for controller in controllers:
                controller.send_movie()
        if now-last_rss >= 5:
            last_rss = now
            pids = {os.getpid()}
            for c in controllers:
                processes = [c.process, c.preparer, *c.capture.encoders.values(), *c.playback._processes.values()]
                pids.update(int(p.processId()) for p in processes if p.processId())
            rss = rss_bytes(sorted(pids))
            rss_history.append({'elapsed':round(now-started, 1), 'combined_rss_bytes':rss})
            report['peak_combined_rss_bytes'] = max(report['peak_combined_rss_bytes'], rss or 0)
        if args.exercise_video_overload and transmitting is not None and now-transmitting >= 10:
            for c in controllers:
                label = c.station
                metrics = capture_metrics[label]
                probe = report['forced_video_probes'].get(label)
                if c.capture.sending and probe is None:
                    report['forced_video_probes'][label] = {
                        'forced':True, 'elapsed':now-transmitting, 'before':metrics.snapshot()}
                    c.capture.pause_video('Forced acceptance video overload probe; audio must continue')
                elif probe is not None and 'after' not in probe and now-transmitting >= probe['elapsed']+5:
                    probe['after'] = metrics.snapshot()
                    probe['audio_continued'] = probe['after']['audio_frames'] > probe['before']['audio_frames']
                    probe['video_recovered'] = probe['after']['video_pictures'] > probe['before']['video_pictures']
        if transmitting is not None and now-transmitting >= args.seconds:
            completed_duration = True
            close()
        elif transmitting is not None and any(c.state in ('idle','error') for c in controllers):
            report['errors'].append({'message':'Call disconnected before the requested duration'})
            close()
    previous_hook = sys.excepthook
    def qt_exception(kind, value, traceback):
        report['errors'].append({'message': f'Unhandled Qt callback: {kind.__name__}: {value}'})
        QTimer.singleShot(0, close)
    sys.excepthook = qt_exception
    timer = QTimer(); timer.timeout.connect(tick); timer.start(100)
    controllers[1].begin('listen', args.answerer_port)
    def dial_when_listening(value):
        if value.get('event') == 'state' and value.get('state') == 'listening':
            controllers[0].begin('dial', args.caller_port, args.number)
    controllers[1].event_received.connect(dial_when_listening)
    try:
        app.exec()
    finally:
        sys.excepthook = previous_hook
    for c in controllers:
        report['stations'][c.station] = {'closed':c._closed, 'state':c.state,
                                         'capture_active':c.capture.active}
        report['capture'][c.station] = capture_metrics[c.station].summary()
    report['events'] = list(events)
    report['rss_samples'] = list(rss_history)
    report['completed_duration'] = completed_duration
    report['passed'] = (completed_duration and not report['errors']
                        and all(c._closed and not c.capture.active for c in controllers)
                        and all(count > 0 for channels in report['received'].values() for count in channels.values())
                        and all(count > 0 for channels in report['decoded'].values() for count in channels.values())
                        and all(report['rates'].get(label) == 14400 for label in ('1','2'))
                        and all(report['bearers'].get(label) is not None for label in ('1','2'))
                        and all(report['capture'][str(index+1)]['audio_output_ratio'] >= .90
                                for index, mode in enumerate(modes) if mode == 'camera')
                        and (not args.exercise_video_overload or
                             all(report['forced_video_probes'].get(str(index+1), {}).get('audio_continued')
                                 and report['forced_video_probes'].get(str(index+1), {}).get('video_recovered')
                                 for index, mode in enumerate(modes) if mode == 'camera'))
                        and all(report['cleanup'].get(label, {}).get('cleanup_ok') is True for label in ('1','2')))
    report['elapsed_seconds'] = time.monotonic()-started
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('file/file','file/camera','camera/camera','stress'), default='stress')
    parser.add_argument('--seconds', type=float, default=600)
    parser.add_argument('--exercise-video-overload', action='store_true',
                        help='force one labeled camera-video pause after 10 seconds and require audio continuity/video recovery')
    parser.add_argument('--caller-port'); parser.add_argument('--answerer-port'); parser.add_argument('--number')
    parser.add_argument('--bundle1', type=Path); parser.add_argument('--bundle2', type=Path)
    for index in (1, 2):
        parser.add_argument(f'--camera{index}', help='explicit camera ID hex from Qt device enumeration')
        parser.add_argument(f'--microphone{index}', help='explicit microphone ID hex')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.seconds <= 5:
        parser.error('--seconds must exceed 5 to exercise recovery')
    if args.exercise_video_overload and args.seconds < 20:
        parser.error('--exercise-video-overload requires at least 20 seconds.')
    app = QApplication([]); app.setQuitOnLastWindowClosed(False); apply_theme(app)
    try:
        report = stress(args, app) if args.mode == 'stress' else hardware(args, app)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('events','statuses')}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
