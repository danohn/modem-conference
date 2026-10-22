"""Unsupported client runtimes must fail before importing Qt extensions."""
import os
import subprocess
import sys

import pytest

from modem_conference.runtime import unsupported_reason


@pytest.mark.parametrize('platform,version,supported', [
    ('linux', (3, 11), False), ('linux', (3, 12), True),
    ('linux', (3, 14), True), ('darwin', (3, 11), True),
    ('win32', (3, 11), True), ('darwin', (3, 10), False),
])
def test_platform_python_support_policy(platform, version, supported):
    assert (unsupported_reason(platform, version) is None) == supported


@pytest.mark.parametrize('operation', [
    "import modem_conference.__main__",
    "from modem_conference.helper import main; main(['--self-test'])",
    "from modem_conference.helper import main; main(['acceptance', '--list-devices'])",
    "import modem_conference.acceptance",
])
def test_linux_311_entrypoints_reject_before_any_qt_import(operation):
    code = '''
import builtins, sys
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.')[0] in ('PySide6', 'shiboken6'):
        raise AssertionError('Qt was imported on an unsupported runtime')
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
sys.platform = 'linux'
sys.version_info = (3, 11, 0)
''' + operation
    result = subprocess.run([sys.executable, '-c', code], capture_output=True,
                            text=True, timeout=10, env=os.environ.copy())
    assert result.returncode == 2, result.stderr
    assert 'requires Python 3.12 or later on Linux' in result.stderr
    assert 'Upgrade Python' in result.stderr
    assert 'Qt was imported' not in result.stderr
