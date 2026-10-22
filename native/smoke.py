"""Relocate and smoke-test a native preview without Python/uv/FFmpeg in PATH."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application", type=Path)
    args = parser.parse_args()
    source = args.application.resolve()
    with tempfile.TemporaryDirectory(prefix="Modem Conference native smoke ") as directory:
        relocated = Path(directory) / source.name
        shutil.copytree(source, relocated, symlinks=True)
        if sys.platform == "darwin":
            main_exe = relocated / "Contents" / "MacOS" / "modem-conference"
            helper = relocated / "Contents" / "Helpers" / "modem-conference-helper.dist" / "modem-conference-helper"
        else:
            suffix = ".exe" if sys.platform == "win32" else ""
            main_exe = relocated / f"modem-conference{suffix}"
            helper = relocated / "helper" / f"modem-conference-helper{suffix}"
        for executable in (main_exe, helper):
            if not executable.is_file():
                raise RuntimeError(f"Missing native executable: {executable.relative_to(relocated)}")
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("PYTHON", "VIRTUAL_ENV", "UV_"))
                       and key not in {"QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"}}
        # The application must not discover build-machine Python or FFmpeg. Qt
        # may still load platform-provided system libraries by absolute path.
        empty_path = Path(directory) / "empty PATH"
        empty_path.mkdir()
        environment["PATH"] = str(empty_path)
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["MODEM_CONFERENCE_SMOKE_TEST"] = "1"
        environment["MODEM_CONFERENCE_CONFIG_DIR"] = str(Path(directory) / "settings")
        for argv in ([str(helper), "--self-test"], [str(main_exe), "--smoke-test"]):
            result = subprocess.run(argv, cwd=directory, env=environment, timeout=45,
                                    capture_output=True, text=True)
            print(json.dumps({"executable": Path(argv[0]).name, "returncode": result.returncode,
                              "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}))
            if result.returncode:
                raise RuntimeError(f"Native smoke failed: {Path(argv[0]).name}")
        print("Native GUI/helper relocated smoke passed; no modem or capture device opened.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
