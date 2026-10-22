"""Launch independent period-themed H.324 stations."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .controller import StationController, available_ports
from .settings import directories, load_settings, restore_port
from .theme import apply_theme
from .window import StationWindow


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', action='store_true', help='open two independent station windows')
    parser.add_argument('--station', default='1', help='local station label')
    parser.add_argument('--port', help='explicit modem serial device path or COM port')
    parser.add_argument('--second-port', help='explicit modem for the second window')
    parser.add_argument('--number', help='initial dialed telephone number')
    parser.add_argument('--logs', type=Path, help='application diagnostics directory')
    parser.add_argument('--capture', action='store_true', help='opt in to recording received encoded media')
    parser.add_argument('--smoke-test', action='store_true', help='show UI briefly and exit without opening devices')
    args = parser.parse_args(argv)
    if args.pair and args.port and args.port == args.second_port:
        parser.error('Each station requires a different modem port.')
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName('Modem Conference')
    app.setOrganizationName('danohn')
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    directory = args.logs or directories()['logs'] / dt.datetime.now(dt.timezone.utc).strftime('app-%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    windows, controllers = [], []
    live = set()

    def add_station(station=None, port=None, number=None):
        station = station or str(len(windows)+1)
        window = StationWindow(station, available_ports())
        controller = StationController(window, station, directory, app)
        controller.raw_capture = args.capture
        windows.append(window); controllers.append(controller); live.add(controller)
        window.new_station_requested.connect(lambda: add_station())
        remembered = restore_port(settings.get(f'port_{station}', ''))
        window.set_initial_connection(port or remembered, number if number is not None else settings.get(f'number_{station}', ''))
        offset = (len(windows)-1)*30
        window.move(40+offset, 40+offset)
        window.show()
        controller.set_muted(len(windows)>1)
        window.set_muted(len(windows)>1)
        def closed():
            live.discard(controller)
            if not live:
                app.quit()
        controller.closed.connect(closed)

    add_station(args.station, args.port, args.number)
    if args.pair:
        add_station('2', args.second_port)
    timer = QTimer(app)
    timer.timeout.connect(lambda: None); timer.start(250)
    def stop(*_):
        for window, controller in zip(windows, controllers):
            window.hide(); controller.shutdown()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    if args.smoke_test:
        QTimer.singleShot(300, stop)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
