"""Console-capable helper shared by source and frozen GUI installations."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def command(operation: str, arguments=()) -> tuple[str, list[str]]:
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        suffix = ".exe" if sys.platform == "win32" else ""
        if Path(sys.executable).stem == 'modem-conference-helper':
            return sys.executable, [operation, *map(str, arguments)]
        base = Path(sys.executable).parent
        candidate = (base.parent / "Helpers/modem-conference-helper.dist/modem-conference-helper"
                     if sys.platform == "darwin" else
                     base / "helper" / f"modem-conference-helper{suffix}")
        if not candidate.is_file():
            raise FileNotFoundError(f"Bundled helper is missing: {candidate}")
        return str(candidate), [operation, *map(str, arguments)]
    return sys.executable, ["-u", "-m", "modem_conference.helper", operation, *map(str, arguments)]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--self-test"]:
        from importlib.resources import files
        from . import __version__
        from h324.activity import CallActivity
        import json
        activity = CallActivity()
        try:
            started = activity.start()
        finally:
            released = activity.close()
        print(json.dumps({"version": __version__, "helper": True,
                          "asset": files("modem_conference").joinpath("assets/combo-arrow.svg").is_file(),
                          "activity": {"started":started, "released":released}}))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("worker", "prepare", "acceptance"))
    args = parser.parse_args(argv[:1])
    remaining = argv[1:]
    sys.argv = [sys.argv[0], *remaining]
    if args.operation == "worker":
        from h324.worker import main as run
    elif args.operation == "prepare":
        from .media import main as run
    else:
        from .acceptance import main as run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
