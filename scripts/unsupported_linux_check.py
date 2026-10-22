"""Verify installed Linux/Python 3.11 client rejection without importing Qt."""
from __future__ import annotations

import argparse
import importlib.resources
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


BLOCK_QT = '''
import importlib.abc, sys
class NoQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'PySide6', 'shiboken6'}:
            raise AssertionError('Unsupported runtime attempted a Qt import: ' + fullname)
sys.meta_path.insert(0, NoQt())
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'linux' or sys.version_info[:2] != (3, 11):
        raise RuntimeError('This installed-runtime check requires Linux Python 3.11')
    import h324
    import modem_conference
    for module in (h324, modem_conference):
        path = Path(module.__file__).resolve()
        if path.is_relative_to(args.checkout.resolve()):
            raise RuntimeError(f'Expected an installed package outside the checkout: {path}')
    if not importlib.resources.files('h324').joinpath('data/MULTIMEDIA-SYSTEM-CONTROL.asn').is_file():
        raise RuntimeError('Installed headless library is missing its schema')
    if not importlib.resources.files('modem_conference').joinpath('assets/combo-arrow.svg').is_file():
        raise RuntimeError('Installed client is missing its packaged asset')
    if any(name.split('.')[0] in {'PySide6', 'shiboken6'} for name in sys.modules):
        raise RuntimeError('Package metadata/resources unnecessarily imported Qt')
    with tempfile.TemporaryDirectory(prefix='client runtime guard ') as temporary:
        path = Path(temporary)
        (path / 'sitecustomize.py').write_text(BLOCK_QT, encoding='utf-8')
        environment = dict(os.environ, PYTHONPATH=temporary)
        scripts = Path(sys.executable).parent
        commands = [
            [str(scripts / 'modem-conference'), '--help'],
            [str(scripts / 'modem-conference-helper'), '--self-test'],
            [sys.executable, '-m', 'modem_conference', '--help'],
            [sys.executable, '-m', 'modem_conference.helper', 'acceptance', '--list-devices'],
            [sys.executable, '-m', 'modem_conference.acceptance', '--list-devices'],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=temporary, env=environment,
                                    capture_output=True, text=True, timeout=10)
            message = result.stdout + result.stderr
            print(json.dumps(dict(command=command[1:], returncode=result.returncode,
                                  stdout=result.stdout, stderr=result.stderr)), flush=True)
            if result.returncode != 2 or 'Linux' not in message or '3.12' not in message:
                raise RuntimeError('Unsupported Linux client did not provide its Python 3.12 guidance')
            if 'Unsupported runtime attempted a Qt import' in message:
                raise RuntimeError('The runtime guard ran after a Qt import')
        for module, arguments in (('h324', ['--help']), ('h324.worker', ['--self-test'])):
            result = subprocess.run([sys.executable, '-m', module, *arguments],
                                    cwd=temporary, env=environment, capture_output=True,
                                    text=True, timeout=15)
            if result.returncode:
                raise RuntimeError('The headless h324 library must remain usable on Python 3.11: ' + result.stderr)
    print('Linux Python 3.11 rejects client entrypoints before Qt; resources and h324 remain usable.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
