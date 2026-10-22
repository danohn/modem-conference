# Modem Conference

An experimental, Windows 95 inspired H.324 conferencing application. Two
stations can send a prepared movie or live camera/microphone stream through
separate compatible dial-up modems, simultaneously in both directions.

This client uses the separately published [`h324`](https://github.com/danohn/h324)
library. It contains no copy of the modem protocol stack. Version **0.1.0a1**
is an alpha: the supported modem profile is CX93001 V.80, V32bis at 14,400 bps.
Other modems and independent H.324 terminals need interoperability testing.

## Install and start

Use Python **3.11–3.14 on macOS/Windows**, or **3.12–3.14 on Linux**, with an
external FFmpeg installation:

```sh
pip install modem-conference==0.1.0a1
modem-conference
# Two independent station windows on one computer:
modem-conference --pair
```

Native preview downloads bundle Python and Qt. They still require FFmpeg and
FFprobe. Use **Options → Dependencies** to configure explicit executable paths
or use PATH. A suitable build must encode H.263, G.723.1, MPEG-4, AAC and PNG,
and decode H.263 and G.723.1, and provide the AVI muxer for local live-encoder
packet framing. No AVI container data crosses the modem link. No libx264 encoder
is required.

On macOS, the Python-installed launcher creates a small per-user **Modem
Conference.app** and starts through it automatically. This supplies the
camera/microphone usage descriptions required for normal macOS permission
prompts. It copies the selected Python executable and references the current
Python installation; it does not modify Python's global bundle or system
privacy settings. Recreate it with `modem-conference --install-macos-launcher`
after moving a virtual environment. Native release apps already provide their
own bundle. See [Qt's permission requirements](https://doc.qt.io/qt-6/permissions.html).
The source launcher has been checked with uv's standalone Python and Homebrew
framework Python on macOS. Other interpreter distributions, including
python.org installers, still need validation; the native app is recommended
when the interpreter cannot run after being copied into its local app bundle.

- macOS: `brew install ffmpeg`
- Ubuntu: `sudo apt install ffmpeg`
- Windows: obtain an FFmpeg build linked from [ffmpeg.org](https://ffmpeg.org/download.html)
  and add its `bin` directory to PATH.

## Make a call

1. Select a modem in each station. No modem or phone number is selected by default.
2. Click **Answer** at one station, then enter its telephone number and **Call** at the other.
3. After connection, select **Movie file**, open a short clip and wait for preparation,
   or select **Camera + microphone** and choose devices.
4. Click **Transmit**. Both stations can transmit together. Pause, Resume and Stop
   operate on the current source. Stop permits selecting another source.
5. **Hang up** or close the station to restore and release its modem.

Use **File → New Station** for an additional window. A port can only be owned by
one station. Remembered USB identities that match multiple ports are left
unselected so identical adapters cannot silently swap.

Camera/microphone capture starts only after **Preview** or **Transmit**. Preview
opens the camera without opening a microphone. Permission denial, device removal,
and device contention produce errors; another camera or microphone is never
substituted automatically. Use **Devices** to select cameras, microphones and speakers,
including USB devices. **Use headphones**: acoustic echo cancellation is not included.

## Quality and limits

The initial wire profile carries H.263 at 128 × 96 pixels, up to two frames per
second, and G.723.1 mono audio. Ordinary footage requires substantial detail
reduction. Files are limited to 60 seconds and rejected if their encoded streams
exceed the line or burst budget. Camera capture has no file-duration limit.

Live video drops stale raw camera frames before encoding. Whole encoded pictures
are admitted within a bounded bandwidth budget. Video overload pauses video and
restarts with a fresh INTRA picture, while audio and modem control continue.
High-motion scenes may therefore show intermittent pictures. Received video has
one picture of parser delay; this is a prototype rather than a low-latency video phone.
The sender uses local packet lengths to avoid waiting for another encoded
picture. See the [measured latency and packet-framing limits](docs/video-packet-framing.md).

Settings, cache and logs use platform-standard user directories. Raw received
media recording is **off** unless `--capture` is supplied. Logs may include port
names and dialed numbers; inspect them before sharing.

## Platform status

Targets: macOS 14.4+ (Apple Silicon/Intel), Windows 10/11 x64, and Ubuntu 24.04+
x64, using Qt/PySide6 6.12. Software CI coverage and actual hardware validation are
different. Physical Linux modem and capture-device operation are **unverified**
until tested on hardware; see the release notes for other tested combinations.
Linux source installations require Python 3.12 or newer because the official
PySide6 6.12.0 Linux package fails a signal reference-count check on Python 3.11.
Installation on Linux/Python 3.11 may complete, but the client refuses to start
before importing Qt and explains how to upgrade. Native downloads include Python
3.14. The separate `h324` library supports Python 3.11–3.14 on every target OS.
On Linux the account needs serial-device access (commonly membership in `dialout`),
and desktop camera/audio permissions. Install the applicable modem driver first.

## Development

```sh
uv sync --group dev
uv run pytest
uv run -m modem_conference --smoke-test
uv run -m modem_conference.helper --self-test
```

For an unpublished local `h324` checkout, install both editable projects with
`uv pip install -e ../h324 -e .` in a virtual environment. Public metadata always
depends on the released `h324==0.1.0a1`; no local path is embedded in the package.

Our original code and synthetic test fixtures are MIT licensed. Qt/PySide6,
FFmpeg and other dependencies retain their own licenses. See the release
third-party notices. The external FFmpeg and ffprobe executables are not
bundled; Qt Multimedia may include separately licensed FFmpeg shared libraries
as part of its runtime.
