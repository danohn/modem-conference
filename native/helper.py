"""Console-capable frozen helper, never a Python-interpreter replacement."""
from modem_conference.helper import main

if __name__ == "__main__":
    raise SystemExit(main())
