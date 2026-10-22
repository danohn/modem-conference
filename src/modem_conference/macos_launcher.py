"""Create an explicit source-install app bundle for normal macOS permissions.

Qt requires usage-description keys in the executable's application bundle.
This copies the selected Python executable; it never edits the interpreter or
changes system permission databases. Native release downloads already include
the required bundle and do not need this development/source launcher.
"""
from __future__ import annotations

import os
from pathlib import Path
import plistlib
import shlex
import shutil
import sys

from platformdirs import user_data_path


def create(destination: Path | None = None, *, executable=None, prefix=None, paths=None) -> Path:
    destination = destination or user_data_path('modem-conference', appauthor=False) / 'Modem Conference.app'
    destination = Path(destination).expanduser().resolve()
    executable = Path(executable or sys.executable).resolve()
    prefix = str(prefix or sys.base_prefix)
    paths = [str(Path(item).resolve()) for item in (sys.path if paths is None else paths) if item]
    contents = destination / 'Contents'
    binaries = contents / 'MacOS'
    binaries.mkdir(parents=True, exist_ok=True)
    target = binaries / 'python'
    if target.resolve() != executable:
        temporary = binaries / '.python.new'
        shutil.copy2(executable, temporary)
        os.replace(temporary, target)
    target.chmod(target.stat().st_mode | 0o111)
    info = {
        'CFBundleIdentifier': 'org.danohn.modem-conference.source',
        'CFBundleName': 'Modem Conference',
        'CFBundleDisplayName': 'Modem Conference',
        'CFBundleExecutable': 'modem-conference',
        'CFBundlePackageType': 'APPL',
        'CFBundleShortVersionString': '0.1.0a1',
        'NSHighResolutionCapable': True,
        'NSCameraUsageDescription': 'Send your camera picture to the other modem station after you choose Preview or Transmit.',
        'NSMicrophoneUsageDescription': 'Send your voice to the other modem station after you choose Transmit.',
    }
    (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
    launcher = binaries / 'modem-conference'
    # All installation paths are runtime-discovered and shell-quoted. The app is
    # tied to this Python installation; regenerate it after moving the venv.
    launcher.write_text('#!/bin/sh\n'
        f'export PYTHONHOME={shlex.quote(prefix)}\n'
        f'export PYTHONPATH={shlex.quote(os.pathsep.join(paths))}\n'
        'app_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        'if [ "$1" = "--python" ]; then\n'
        '  shift\n'
        '  exec "$app_dir/python" "$@"\n'
        'fi\n'
        'exec "$app_dir/python" -m modem_conference "$@"\n', encoding='utf-8')
    launcher.chmod(0o755)
    return destination


def has_usage_descriptions() -> bool:
    """Find the containing executable bundle without importing Cocoa bindings."""
    executable = Path(sys.executable).resolve()
    for parent in executable.parents:
        if parent.suffix == '.app':
            try:
                info = plistlib.loads((parent / 'Contents/Info.plist').read_bytes())
                return bool(info.get('NSCameraUsageDescription') and info.get('NSMicrophoneUsageDescription'))
            except (OSError, ValueError):
                return False
    return False
