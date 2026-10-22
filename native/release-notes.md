Modem Conference is an experimental H.324 dial-up video conferencing preview,
with a 1990s-style desktop interface. Expect interoperability limits and rough
edges; this alpha is intended for modem enthusiasts and testing.

## What is included

- Movie-file transmission and camera/microphone calling, with incoming picture,
  outgoing preview, meters and connection information.
- One station by default; **New Station** or `--pair` opens another independently
  configured station for a local two-modem setup.
- A separately packaged `h324` protocol library and a dedicated modem worker.
- The explicitly supported **CX93001/V.80, V32bis at 14,400 bps** profile. The
  initial media profile is H.263 at 128×96, up to 2 fps, with G.723.1 mono audio.
  Compatibility with other modems or conferencing products is not established.

Use headphones for microphone calls. Acoustic echo cancellation is outside this
preview. Ports and destination numbers must be configured before calling.

## Choose a download

| Computer | Download | Minimum target |
|---|---|---|
| Mac with Apple Silicon | `macos-arm64.zip` | macOS 14.4 |
| Mac with Intel processor | `macos-x64.zip` | macOS 14.4 |
| Windows PC, x64 | `windows-x64.zip` | Windows 10/11 |
| Linux PC, x64 | `linux-x64.tar.gz` | Ubuntu 24.04 or newer |

These names are suffixes of the versioned assets below. Download the matching
`.sha256` file and verify the archive before opening it. Extract the entire
archive and keep its helper executable and shared libraries together. Native
downloads include Python and Qt; Python and `uv` are not installation
requirements.

For source installations, use Python 3.11–3.14 on macOS/Windows or Python
3.12–3.14 on Linux. Qt 6.12 is used throughout. Linux Python 3.11 client
launchers exit with upgrade guidance before importing Qt because of a confirmed
upstream signal-reference defect. The independent `h324` library retains Python
3.11 support on Linux. Package installation alone does not establish that the
client runtime is supported; see the [runtime policy](https://github.com/danohn/modem-conference/blob/main/docs/release.md#supported-python-runtimes).

The external **FFmpeg and ffprobe executables are required for media processing**
and are not bundled. Select them in settings or install them on PATH, then check
the dependency-status dialog for required codecs. Qt Multimedia's own runtime
may include FFmpeg backend shared libraries; their separate licenses and source
links are included in the bundled notices.

## Opening the unsigned preview

- **macOS:** extract the ZIP and move the app to Applications. After checking
  the source and checksum, use right-click → Open or Privacy & Security → Open
  Anyway if Gatekeeper blocks it. The app is not Developer ID signed or
  notarized. Allow camera/microphone access when prompted if using live capture.
- **Windows:** extract the ZIP before running `modem-conference.exe`.
  SmartScreen may display an unsigned-publisher warning. Keep `helper/` and the
  DLLs alongside the executable.
- **Linux:** extract the archive and run
  `./ModemConference/modem-conference`. Serial-port access may require your
  system's device-group permissions; the application does not change them.

See the [installation and opening instructions](https://github.com/danohn/modem-conference/blob/main/docs/release.md#opening-unsigned-previews)
for details. Original code uses MIT; bundled dependencies retain their own
licenses. Notices are in `notices/`, or `Contents/Resources/notices/` on macOS.

## Validation and known limits

Automated protocol tests, installed-package checks and native startup checks
cover different things from physical modem and capture-device compatibility.
Consult the [current validation record](https://github.com/danohn/modem-conference/blob/main/docs/validation.md)
for exact source revisions, test runs, physical-device results and unresolved
issues. Build success does not imply that every modem, driver or media device
has been tested. Linux physical modem and capture-device validation remains
**unverified**.

The [corrected four-platform native candidates](https://github.com/danohn/modem-conference/actions/runs/39728215208)
built from core `3547027` and client `812676b` passed compilation, relocated
helper/GUI launch and archive audits. A short physical camera retest with the
native Windows GUI and macOS source-app harness then passed on the Mac at an
observed 14,400 bps, including graceful EndSession and confirmed Mac modem
restoration. The Windows user
confirmed Idle, no error dialogs and stopped capture after the Mac hung up.
The corrected Windows diagnostic log has not been reviewed; its internal
cleanup sequence and counters remain unverified. Earlier logs separately
establish over ten minutes of media transmission and modem restoration, but
that earlier build failed normal remote disconnect.

**Audio and video can still arrive several seconds late.** The maintainer
reported this in the corrected physical retest. The Mac source admitted only
six video pictures and paused video for the local bandwidth budget 29 times
during 65.10 seconds of capture, while audio continued. Local AVI packet framing
removes one sender picture interval in software tests; a physical end-to-end
latency improvement has not been established. Receiver lookahead, video
congestion/restarts and the unresolved audio delay remain preview limits.

For a new modem/driver/OS combination, follow the
[manual acceptance instructions](https://github.com/danohn/modem-conference/blob/main/docs/hardware-testing.md).
Please review reports for personal device names and telephone numbers before
sharing them, and do not attach raw recordings unless you intend to share them.
