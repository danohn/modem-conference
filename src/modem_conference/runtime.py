"""Check the supported client runtime before loading Qt extensions."""
from __future__ import annotations

import sys


def unsupported_reason(platform=None, version=None):
    platform = sys.platform if platform is None else platform
    version = sys.version_info[:2] if version is None else version[:2]
    minimum = (3, 12) if platform.startswith('linux') else (3, 11)
    if tuple(version) >= minimum:
        return None
    requirement = 'Python 3.12 or later on Linux' if platform.startswith('linux') else 'Python 3.11 or later'
    return (f'Modem Conference requires {requirement} with Qt 6.12. '
            'Upgrade Python or use a native Modem Conference download. '
            'The h324 protocol library continues to support Python 3.11.')


def require_supported_runtime():
    reason = unsupported_reason()
    if reason:
        print(reason, file=sys.stderr)
        raise SystemExit(2)
