"""Explicit FFmpeg tools, PATH fallback, and required codec checks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from .settings import load_settings


def binary(name: str) -> str:
    explicit = load_settings().get(name)
    result = str(Path(explicit).expanduser()) if explicit else shutil.which(name)
    if not result or not Path(result).is_file():
        raise ValueError(f"{name} was not found. Install FFmpeg and set its path in Options → Dependencies.")
    return result


@dataclass(frozen=True)
class Status:
    ready: bool
    detail: str


def check() -> Status:
    try:
        ffmpeg, ffprobe = binary("ffmpeg"), binary("ffprobe")
        def run(*args):
            child = subprocess.run([ffmpeg, "-hide_banner", *args], capture_output=True,
                                   text=True, timeout=10)
            if child.returncode:
                raise ValueError(child.stderr.strip()[:500])
            return child.stdout
        encoders, decoders, muxers = run("-encoders"), run("-decoders"), run("-muxers")
        for codec in ("h263", "g723_1", "mpeg4", "aac", "png"):
            if not any(codec == token for token in encoders.split()):
                raise ValueError(f"FFmpeg lacks required encoder {codec}.")
        for codec in ("h263", "g723_1"):
            if not any(codec == token for token in decoders.split()):
                raise ValueError(f"FFmpeg lacks required decoder {codec}.")
        if 'avi' not in muxers.split():
            raise ValueError('FFmpeg lacks the required AVI muxer for packet-framed camera encoding.')
        subprocess.run([ffprobe, "-version"], capture_output=True, timeout=10, check=True)
        return Status(True, f"Ready\nFFmpeg: {ffmpeg}\nFFprobe: {ffprobe}")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return Status(False, str(exc))
