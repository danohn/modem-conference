import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

from modem_conference.media import load_bundle, prepare_file
from modem_conference.playback import MAX_ENCODED_BUFFER, Playback
from h324.media import g723_frames, h263_pictures

FIXTURE = Path(__file__).resolve().parents[1] / 'tests/data'


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def wait_for(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.005)
    app.processEvents()
    return predicate()


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg is required')
def test_prepare_silent_source_real_codecs_budget_and_integrity(tmp_path):
    source = tmp_path / 'short.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-r', '2',
                    '-i', str(FIXTURE / 'video.h263'), '-t', '1.5', '-c:v', 'mpeg4', str(source)], check=True)
    target = tmp_path / 'bundle'
    manifest = prepare_file(source, target)
    assert manifest['audio_synthesized'] is True
    assert manifest['duration_ms'] == 1500
    assert manifest['video']['pictures'] == 3
    assert manifest['audio']['frames'] == 50
    assert manifest['budget']['fits_average_budget']
    assert manifest['budget']['fits_video_capability']
    assert manifest['budget']['fits_burst_budget']
    sdus = load_bundle(target)
    assert len([s for s in sdus if s.lcn == 1]) == 50
    assert (target / 'preview.mp4').stat().st_size > 0
    assert (target / 'poster.png').stat().st_size > 0
    (target / 'audio.g723').write_bytes(b'\0' * 24)
    with pytest.raises(ValueError, match='manifest'):
        load_bundle(target)


def test_existing_fixture_load_and_manifest_duration_validation(tmp_path):
    for name in ('audio.g723', 'video.h263', 'manifest.json'):
        shutil.copy(FIXTURE / name, tmp_path / name)
    assert len(load_bundle(tmp_path)) == 215
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    manifest['duration_ms'] += 1500
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='duration'):
        load_bundle(tmp_path)


def test_prepare_rejects_missing_and_nonvideo_source(tmp_path):
    with pytest.raises(ValueError, match='existing'):
        prepare_file(tmp_path / 'missing', tmp_path / 'bundle')
    with pytest.raises(ValueError, match='no video'):
        import wave
        source = tmp_path / 'tone.wav'
        with wave.open(str(source), 'wb') as wav:
            wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0' * 16000)
        prepare_file(source, tmp_path / 'bundle')


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg is required')
def test_incremental_tiny_stream_decodes_before_eof_and_restarts(app):
    playback = Playback(audio_enabled=False)
    frames, audio, errors = [], [], []
    playback.video_frame.connect(lambda image: frames.append(image.copy()))
    playback.audio_decoded.connect(audio.append)
    playback.error.connect(errors.append)
    pictures = h263_pictures((FIXTURE / 'video.h263').read_bytes())
    sound = g723_frames((FIXTURE / 'audio.g723').read_bytes())
    # Exercise the bounded pre-start queue and genuinely fragmented AL payloads.
    playback.feed(2, pictures[0][:7])
    playback.start()
    playback.feed(2, pictures[0][7:])
    for frame in sound[:12]:
        playback.feed(1, frame)
    playback.feed(2, pictures[1])
    assert wait_for(app, lambda: bool(frames) and sum(map(len, audio)) >= 480)
    assert frames[0].width() == 128 and frames[0].height() == 96
    assert all(p.state() == QProcess.ProcessState.Running for p in playback._processes.values())
    # No closeWriteChannel()/finish()/EOF occurred before these assertions.
    assert not errors
    playback.stop()
    assert playback.buffered_bytes == 0
    assert wait_for(app, lambda: not playback._processes)
    playback.start()
    playback.feed(2, pictures[0] + pictures[1])
    assert wait_for(app, lambda: len(frames) >= 2)
    playback.stop()
    wait_for(app, lambda: False, .15)


def test_prestart_buffer_is_bounded_and_stop_discards_old_call(app):
    playback = Playback()
    errors = []
    playback.error.connect(errors.append)
    playback.feed(2, b'x' * MAX_ENCODED_BUFFER)
    playback.feed(2, b'overflow')
    assert playback.buffered_bytes == MAX_ENCODED_BUFFER
    assert errors and 'buffer is full' in errors[0]
    playback.stop()
    assert playback.buffered_bytes == 0
    with pytest.raises(ValueError):
        playback.feed(0, b'control')


def test_converter_cancellation_reaps_its_child_and_removes_temporary_files(tmp_path):
    """Use a sleeping stand-in, not an expensive FFmpeg conversion."""
    marker = tmp_path / 'child.pid'
    child = ('import os, pathlib, sys, time; '
             'pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)')
    wrapper = f'''
import sys, tempfile
from pathlib import Path
from modem_conference import media
def fake_prepare(source, output):
    with tempfile.TemporaryDirectory(prefix='active-', dir={str(tmp_path)!r}):
        return media._run([sys.executable, '-c', {child!r}, {str(marker)!r}])
media.prepare_file = fake_prepare
sys.argv = ['media', 'source', 'output']
raise SystemExit(media.main())
'''
    process = subprocess.Popen([sys.executable, '-c', wrapper], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert marker.exists(), 'stand-in converter did not start'
        child_pid = int(marker.read_text())
        process.stdin.write(b'cancel\n')
        process.stdin.flush()
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 128 + signal.SIGTERM
        assert stdout == b''
        assert b'cancelled' in stderr
        assert not list(tmp_path.glob('active-*'))
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
