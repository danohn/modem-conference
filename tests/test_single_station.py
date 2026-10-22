"""Run the complete one-endpoint report lifecycle with simulated Qt/worker I/O."""
from types import SimpleNamespace

import pytest

import modem_conference.acceptance as acceptance


@pytest.mark.parametrize('role', ['answer','dial'])
@pytest.mark.parametrize('early_disconnect', [False,True])
def test_single_station_uses_one_controller_and_requires_full_exchange(monkeypatch, tmp_path, role, early_disconnect):
    clock = [0.]
    controllers, timers, begins = [], [], []
    class Signal:
        def __init__(self): self.callbacks = []
        def connect(self, callback): self.callbacks.append(callback)
        def emit(self, *args):
            for callback in self.callbacks: callback(*args)
    class Timer:
        def __init__(self): self.timeout = Signal(); self.active = False; timers.append(self)
        def start(self, interval): self.active = True
        def stop(self): self.active = False
        @staticmethod
        def singleShot(interval, callback): callback()
    class Window:
        def __init__(self, *args): pass
        def set_initial_connection(self, *args): pass
        def set_muted(self, *args): pass
        def show(self): pass
    class Process:
        def processId(self): return 0
    class Controller:
        def __init__(self, window, label, root):
            self.station, self.state, self.window = label, 'idle', window
            self._closed = self.shutdown_forced = False
            self.event_received = Signal()
            self.capture = SimpleNamespace(frame=Signal(), status=Signal(), chunk=Signal(), stopped=Signal(),
                                           active=False, sending=False, encoders={}, started_at=0.)
            self.playback = SimpleNamespace(audio_decoded=Signal(), video_frame=Signal(), _processes={})
            self.process = self.preparer = Process()
            controllers.append(self)
        def set_muted(self, value): pass
        def set_bundle(self, path): self.bundle = path
        def begin(self, operation, port, number=None):
            begins.append((operation, port, number))
            self.state = 'listening' if operation == 'listen' else 'dialing'
            self.event_received.emit({'event':'state','state':self.state})
        def send_movie(self):
            self.event_received.emit({'event':'media_started'})
        def shutdown(self):
            self.event_received.emit({'event':'cleanup','cleanup_ok':True,'rate':14400,
                                      'session':{'counts':{'tx_media_bytes':100}}})
            self.state, self._closed = 'idle', True
    class App:
        stopped = False
        def quit(self): self.stopped = True
        def exec(self):
            c = controllers[0]
            c.state = 'connected'
            c.event_received.emit({'event':'state','state':'connected'})
            c.event_received.emit({'event':'telemetry','rate':14400})
            for _ in range(200):
                clock[0] += .1
                if not c._closed:
                    for channel in (1,2):
                        c.event_received.emit({'event':'media','lcn':channel})
                    c.playback.audio_decoded.emit(b'pcm')
                    c.playback.video_frame.emit(object())
                if early_disconnect and clock[0] >= 2. and not c._closed:
                    c.state = 'hanging_up'
                    c.event_received.emit({'event':'state','state':'hanging_up'})
                for timer in timers:
                    if timer.active: timer.timeout.emit()
                if self.stopped: return 0
            pytest.fail('Simulated endpoint did not close within bounded time')
    monkeypatch.setattr(acceptance, 'QTimer', Timer)
    monkeypatch.setattr(acceptance, 'StationWindow', Window)
    monkeypatch.setattr(acceptance, 'StationController', Controller)
    monkeypatch.setattr(acceptance, 'available_ports', lambda: [('COM7','Simulated modem')])
    monkeypatch.setattr(acceptance.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(acceptance, 'rss_bytes', lambda pids: 1024)
    args = SimpleNamespace(mode='station', role=role, port='COM7', number='5550123' if role=='dial' else None,
                           source='file', bundle=tmp_path/'prepared', exercise_video_overload=False,
                           seconds=6., timeout=180., output=tmp_path/'report.json')
    report = acceptance.hardware(args, App())
    assert len(controllers) == 1
    assert begins == [('dial' if role=='dial' else 'listen', 'COM7', args.number)]
    assert report['passed'] is (not early_disconnect)
    assert report['completed_duration'] is (not early_disconnect)
    assert set(report['received']) == {'1'}
    assert report['cleanup']['1']['cleanup_ok']
    assert controllers[0]._closed
