"""Prepare bounded, genuine baseline H.324 media for the desktop stations.

Run ``python -m modem_conference.media SOURCE OUTPUT`` in a separate process. Successful
stdout contains one JSON object; errors go to stderr. FFmpeg performs the real
codec work. Video remains SQCIF / 2 fps, matching our negotiated H.245 profile.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

from h324.media import PROFILE, MediaSDU, budget, g723_frames, h263_pictures, load_fixture
from .dependencies import binary

MAX_DURATION_SECONDS = 60
LINE_BPS = 14400
CONTROL_RESERVE_BPS = 1000
MAX_VIDEO_BPS = 4800
MAX_LATE_MS = 1500
CODEC_FILES = ('audio.g723', 'video.h263')
CANCELLED = threading.Event()


class PreparationCancelled(Exception):
    """Raised by the CLI's SIGTERM handler so normal cleanup can unwind."""


def _cancel(_signal_number, _frame) -> None:
    # A second termination request must not interrupt child/tempfile cleanup.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise PreparationCancelled('Movie preparation was cancelled.')


def _stop_child(process: subprocess.Popen) -> None:
    """Reap only the converter we launched; never signal a process group."""
    if process.poll() is None:
        process.terminate()
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=2)


def _binary(name: str) -> str:
    return binary(name)


def _run(command: list[str]) -> bytes:
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.monotonic() + 180
    try:
        while True:
            if CANCELLED.is_set():
                raise PreparationCancelled('Movie preparation was cancelled.')
            if time.monotonic() >= deadline:
                raise ValueError('Media conversion exceeded its three-minute limit.')
            try:
                stdout, stderr = process.communicate(timeout=.1)
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            _stop_child(process)
    if process.returncode:
        detail = stderr.decode(errors='replace').strip()[-1600:]
        raise ValueError(f'Media conversion failed: {detail}')
    return stdout


def _file_info(path: Path) -> dict:
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def _validate(directory: Path) -> tuple[list[MediaSDU], dict]:
    sdus = load_fixture(directory, max_video_sdu=96)
    audio = [s for s in sdus if s.lcn == 1]
    pictures = h263_pictures((directory / 'video.h263').read_bytes())
    if not audio or not pictures:
        raise ValueError('Both audio and video streams must be nonempty.')
    if any(len(s.payload) != 24 or s.payload[0] & 3 for s in audio):
        raise ValueError('Audio must use the negotiated G.723.1 6.3 kbit/s mode.')
    duration_ms = len(audio) * 30
    if duration_ms != len(pictures) * 500 or duration_ms > MAX_DURATION_SECONDS * 1000:
        raise ValueError('Audio/video durations must match and be at most 60 seconds.')
    report = budget(sdus, LINE_BPS, CONTROL_RESERVE_BPS)
    reserved = budget(sdus, LINE_BPS - CONTROL_RESERVE_BPS, 0)
    report['reserved_fifo_max_completion_lateness_ms'] = reserved['offline_fifo_max_completion_lateness_ms']
    report['video_codec_bps'] = (directory / 'video.h263').stat().st_size * 8000 / duration_ms
    report['fits_video_capability'] = report['video_codec_bps'] <= MAX_VIDEO_BPS
    report['fits_burst_budget'] = reserved['offline_fifo_max_completion_lateness_ms'] <= MAX_LATE_MS
    if not (report['fits_average_budget'] and report['fits_video_capability'] and report['fits_burst_budget']):
        raise ValueError('This clip exceeds the 14,400 bps profile or its 1.5-second burst allowance.')
    return sdus, report


def load_bundle(path: str | Path) -> list[MediaSDU]:
    """Validate codec bytes, manifest integrity and line budget before loading.

    Existing checked lab fixtures are accepted too; a desktop bundle additionally
    records its source and conversion parameters. Paths come from the caller,
    never from manifest filenames.
    """
    directory = Path(path).expanduser().resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    for name in CODEC_FILES:
        expected = manifest.get('files', {}).get(name)
        if not expected or _file_info(directory / name) != expected:
            raise ValueError(f'{name} is missing or does not match the bundle manifest.')
    sdus, _ = _validate(directory)
    actual_ms = max(s.timestamp_ms + s.duration_ms for s in sdus)
    if manifest.get('duration_ms') != actual_ms:
        raise ValueError('Bundle duration does not match the codec streams.')
    return sdus


def prepare_file(source: Path, output: Path, max_duration: float = MAX_DURATION_SECONDS) -> dict:
    """Convert a video file, progressively reducing detail until it fits.

    Clips longer than the explicit limit are rejected rather than silently cut.
    Short tails are padded to a 1.5-second audio/video alignment. Missing audio
    becomes real encoded silence. Conversion happens in a temporary directory;
    a failed conversion leaves an existing bundle intact.
    """
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if not source.is_file():
        raise ValueError('Choose an existing video file.')
    if not 0 < max_duration <= MAX_DURATION_SECONDS:
        raise ValueError('Maximum duration must be between zero and 60 seconds.')
    if output == source.parent or output == source or source.is_relative_to(output):
        raise ValueError('The bundle directory must be separate from the source file.')
    ffmpeg, ffprobe = _binary('ffmpeg'), _binary('ffprobe')
    probe = json.loads(_run([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(source)]))
    streams = probe.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
    if video is None:
        raise ValueError('The selected file has no video stream.')
    raw_duration = video.get('duration') or probe.get('format', {}).get('duration')
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError) as exc:
        raise ValueError('The selected file needs a known, finite duration.') from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('The selected file needs a positive, finite duration.')
    if duration > max_duration + 0.001:
        raise ValueError(f'Choose a clip of at most {max_duration:g} seconds; this one is {duration:.1f} seconds.')
    duration_ms = math.ceil((duration * 1000 - 0.001) / 1500) * 1500
    if duration_ms > MAX_DURATION_SECONDS * 1000:
        raise ValueError('The aligned clip would exceed the 60-second limit.')
    has_audio = any(s.get('codec_type') == 'audio' for s in streams)
    output.parent.mkdir(parents=True, exist_ok=True)
    commands: list[list[str]] = []
    with tempfile.TemporaryDirectory(prefix='.h324-prepare-', dir=output.parent) as temporary:
        directory = Path(temporary)
        common = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y']
        def run(arguments: list[str]) -> None:
            commands.append(common + arguments)
            _run(common + arguments)
        seconds = f'{duration_ms / 1000:.3f}'
        audio_input = ['-i', str(source), '-map', '0:a:0'] if has_audio else ['-f', 'lavfi', '-i', 'anullsrc=r=8000:cl=mono']
        run(audio_input + ['-vn', '-af', 'aresample=8000,apad', '-t', seconds,
            '-ac', '1', '-ar', '8000', '-c:a', 'g723_1', '-b:a', '6300', '-f', 'g723_1', str(directory / 'audio.g723')])
        last_error = None
        chosen_q = None
        for quantizer in (12, 18, 24, 28, 31):
            run(['-i', str(source), '-map', '0:v:0', '-an', '-vf',
                 'fps=2,scale=128:96:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                 'pad=128:96:(ow-iw)/2:(oh-ih)/2,setsar=1,tpad=stop_mode=clone:stop_duration=1.5',
                 '-t', seconds, '-pix_fmt', 'yuv420p', '-c:v', 'h263', '-q:v', str(quantizer),
                 '-g', '12', '-f', 'h263', str(directory / 'video.h263')])
            try:
                sdus, report = _validate(directory)
                chosen_q = quantizer
                break
            except ValueError as exc:
                last_error = exc
        if chosen_q is None:
            raise ValueError('This video is too complex for the dial-up profile even at minimum detail. '
                             'Try a quieter scene or a simpler clip. ' + str(last_error))
        # Local previews are decoded from the actual prepared elementary streams.
        run(['-f', 'g723_1', '-i', str(directory / 'audio.g723'), '-r', '2', '-i', str(directory / 'video.h263'),
             '-map', '1:v:0', '-map', '0:a:0', '-c:v', 'mpeg4', '-pix_fmt', 'yuv420p',
             '-c:a', 'aac', '-movflags', '+faststart', '-shortest', str(directory / 'preview.mp4')])
        run(['-i', str(directory / 'video.h263'), '-frames:v', '1', str(directory / 'poster.png')])
        manifest = {
            'schema': 'h324-desktop-media-v1', 'source': str(source), 'title': source.name,
            'bundle_path': str(output), 'preview': 'preview.mp4', 'poster': 'poster.png',
            'duration_ms': duration_ms, 'source_duration_ms': round(duration * 1000),
            'audio_synthesized': not has_audio, 'video_quantizer': chosen_q,
            'profile': {**PROFILE, 'video_send_buffer': 4096}, 'budget': report,
            'audio': {'codec': 'g723_1', 'frames': len(g723_frames((directory / 'audio.g723').read_bytes())),
                      'sample_rate': 8000, 'channels': 1},
            'video': {'codec': 'h263', 'width': 128, 'height': 96, 'fps': 2,
                      'pictures': len(h263_pictures((directory / 'video.h263').read_bytes()))},
            'files': {name: _file_info(directory / name) for name in (*CODEC_FILES, 'preview.mp4', 'poster.png')},
            'commands': commands,
            'limitations': 'Finite pre-encoded clip; average and burst model excludes retransmissions and host timing.'}
        (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        output.mkdir(parents=True, exist_ok=True)
        for name in (*CODEC_FILES, 'preview.mp4', 'poster.png', 'manifest.json'):
            shutil.copy2(directory / name, output / name)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    CANCELLED.clear()
    def listen():
        pending = b''
        while True:
            data = os.read(sys.stdin.fileno(), 1024)
            if not data:
                break
            pending = (pending + data)[-4096:]
            if b'cancel\n' in pending:
                CANCELLED.set()
                break
    threading.Thread(target=listen, daemon=True).start()
    previous_termination = signal.signal(signal.SIGTERM, _cancel)
    try:
        print(json.dumps(prepare_file(args.source, args.output)))
    except PreparationCancelled as exc:
        print(str(exc), file=sys.stderr)
        return 128 + signal.SIGTERM
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_termination)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
