from types import SimpleNamespace
import sys

from modem_conference.settings import device_identity, restore_port, save_settings, load_settings, directories
from modem_conference import helper


def test_toml_roundtrip_and_duplicate_identity_requires_selection(tmp_path):
    path = tmp_path/'settings.toml'
    values = {'ffmpeg': r'C:\Program Files\FFmpeg\ffmpeg.exe', 'number_1': '*123#'}
    save_settings(values, path)
    assert load_settings(path) == values
    a = SimpleNamespace(device='COM3', vid=1, pid=2, serial_number='duplicate')
    b = SimpleNamespace(device='COM4', vid=1, pid=2, serial_number='duplicate')
    assert restore_port(device_identity(a), [a]) == 'COM3'
    assert restore_port(device_identity(a), [a,b]) == ''
    assert restore_port('missing', [a]) == ''


def test_source_helper_is_module_not_checkout_path():
    program, args = helper.command('worker', ['--station', '1'])
    assert program == sys.executable
    assert args == ['-u','-m','modem_conference.helper','worker','--station','1']


def test_frozen_windows_helper_does_not_pass_python_module_flags(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys, 'executable', str(tmp_path/'Modem Conference.exe'))
    binary = tmp_path/'helper/modem-conference-helper.exe'
    binary.parent.mkdir(); binary.touch()
    program, args = helper.command('prepare', ['source with spaces.mp4', 'bundle'])
    assert program == str(binary)
    assert args == ['prepare', 'source with spaces.mp4', 'bundle']


def test_frozen_acceptance_helper_reuses_own_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'platform', 'win32')
    executable = str(tmp_path/'helper/modem-conference-helper.exe')
    monkeypatch.setattr(sys, 'executable', executable)
    program, arguments = helper.command('worker', ['--station','1'])
    assert program == executable
    assert arguments == ['worker','--station','1']


def test_explicit_user_directories_isolate_config_cache_and_logs(monkeypatch, tmp_path):
    for kind in ('CONFIG', 'CACHE', 'LOG'):
        monkeypatch.setenv(f'MODEM_CONFERENCE_{kind}_DIR', str(tmp_path/kind.lower()))
    assert directories() == {'config': tmp_path/'config', 'cache':tmp_path/'cache', 'logs':tmp_path/'log'}
    save_settings({'number_1':'*123#'})
    assert load_settings() == {'number_1':'*123#'}
    assert (tmp_path/'config/settings.toml').exists()


def test_helper_self_test_releases_native_activity_without_opening_devices(capsys):
    import json
    assert helper.main(['--self-test']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['helper'] and report['asset']
    assert report['activity']['released']['active'] is False
    assert report['activity']['started']['supported'] is (sys.platform == 'darwin')
