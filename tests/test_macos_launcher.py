import plistlib
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
