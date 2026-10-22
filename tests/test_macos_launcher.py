import plistlib
import subprocess
import sys
import pytest

from modem_conference.macos_launcher import create


def test_source_launcher_copies_interpreter_and_declares_permissions(tmp_path):
    source = tmp_path/'original python'
    source.write_bytes(b'original-interpreter')
    app = create(tmp_path/'Example App.app', executable=source, prefix=tmp_path/'Python home',
                 paths=[tmp_path/'site packages'])
    assert source.read_bytes() == b'original-interpreter'
    assert (app/'Contents/MacOS/python').read_bytes() == source.read_bytes()
    assert not (app/'Contents/MacOS/python').is_symlink()
    info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
    assert info['NSCameraUsageDescription']
    assert info['NSMicrophoneUsageDescription']
    script = (app/'Contents/MacOS/modem-conference').read_text()
    assert "export PYTHONHOME='" in script
    assert 'exec "$app_dir/python" -m modem_conference "$@"' in script
    assert '-m modem_conference' in script


def test_mac_source_cli_reexecutes_bundle_before_creating_qapplication(monkeypatch, tmp_path):
    from modem_conference import __main__ as entry
    from modem_conference import macos_launcher
    monkeypatch.setattr(entry.sys, 'platform', 'darwin')
    monkeypatch.setattr(macos_launcher, 'has_usage_descriptions', lambda: False)
    monkeypatch.setattr(macos_launcher, 'create', lambda: tmp_path/'App With Spaces.app')
    calls = []
    def execute(program, arguments):
        calls.append((program, arguments))
        raise RuntimeError('reexec test boundary')
    monkeypatch.setattr(entry.os, 'execv', execute)
    arguments = ['--pair','--port','/dev/fake port','--number','*123#']
    with pytest.raises(RuntimeError, match='reexec test boundary'):
        entry.main(arguments)
    target = str(tmp_path/'App With Spaces.app/Contents/MacOS/modem-conference')
    assert calls == [(target, [target, *arguments])]


@pytest.mark.skipif(sys.platform != 'darwin', reason='Actual macOS app-bundle discovery')
def test_generated_mac_bundle_imports_and_does_not_relaunch_recursively(tmp_path):
    app = create(tmp_path/'App With Spaces.app')
    script = '''
from modem_conference import __main__ as entry, macos_launcher
assert macos_launcher.has_usage_descriptions()
def must_not_create():
    raise AssertionError('Already bundled process tried to create another app')
macos_launcher.create = must_not_create
class ReachedApplication(Exception):
    pass
class Application:
    @staticmethod
    def instance():
        raise ReachedApplication()
entry.QApplication = Application
try:
    entry.main([])
except ReachedApplication:
    pass
else:
    raise AssertionError('Did not reach application startup')
from modem_conference.helper import command
import subprocess
program, arguments = command('worker', ['--self-test'])
child = subprocess.run([program, *arguments], capture_output=True, text=True, timeout=20, check=True)
assert '"ready": true' in child.stdout
print('bundle, environment, and helper verified')
'''
    child = subprocess.run([str(app/'Contents/MacOS/modem-conference'), '--python', '-c', script],
                           capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, child.stderr
    assert 'bundle, environment, and helper verified' in child.stdout
