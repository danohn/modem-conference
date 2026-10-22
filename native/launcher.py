"""Thin executable entry point; application imports remain in the installed wheel."""
from modem_conference.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
