# Hardware and continuous-capture acceptance

Run from a development environment with the client and library installed. The
script does not assume port names, phone numbers, local network equipment, or
particular camera/microphone identifiers.

Native Windows downloads need no Python for these checks. From PowerShell in
the extracted application directory, use the console helper (quote paths with spaces):

```powershell
& '.\helper\modem-conference-helper.exe' prepare 'C:\Movies\Test clip.mp4' 'C:\Movies\Prepared clip'
& '.\helper\modem-conference-helper.exe' acceptance --mode file/file --caller-port COM3 --answerer-port COM4 --number NUMBER --bundle1 'C:\Movies\Prepared clip' --bundle2 'C:\Movies\Prepared clip' --seconds 30 --output '.\acceptance-file-file.json'
& '.\helper\modem-conference-helper.exe' acceptance --mode stress --seconds 600 --output '.\acceptance-stress.json'
```

## One modem on Windows, one modem on another computer

Each computer runs **one local station**. It owns only the explicitly supplied
port and exchanges media with the remote endpoint over the telephone connection.
No shared filesystem or network control connection is required.

On Windows, list ports and device IDs without opening a modem or capture device:

```powershell
& '.\helper\modem-conference-helper.exe' acceptance --list-devices
```

Then start the answering endpoint, replacing `COM7` with its actual modem port:

```powershell
& '.\helper\modem-conference-helper.exe' acceptance --mode station --role answer --port COM7 --source camera --seconds 600 --timeout 180 --output '.\windows-station.json'
```

Choose the camera, microphone and optional speakers in the Devices dialog before
the modem starts listening. The console prints **READY listening** after the
modem is ready. Use headphones. Received audio starts muted; uncheck **Mute
audio** in the window to listen. Device IDs can instead be supplied explicitly
with `--camera HEX_ID --microphone HEX_ID`.

After READY, start the other computer's dialing station with its local port
and the telephone number reaching the Windows modem. For example, through a
macOS source-install launcher:

```sh
'PATH_TO_APP/Contents/MacOS/modem-conference' --python -m modem_conference.helper acceptance \
  --mode station --role dial --port LOCAL_MODEM_PORT --number REMOTE_NUMBER \
  --source camera --seconds 600 --timeout 180 --output mac-station.json
```

For native macOS/Linux, invoke the bundled helper with the same `acceptance`
arguments. A file source uses `--source file --bundle PREPARED_DIRECTORY`.
The answering endpoint does not need a number. Both roles allow 180 seconds to
connect and require inbound encoded/decoded audio and video, observed bearer
rate, outgoing media, and confirmed cleanup. Each report covers its own endpoint;
review both reports for the full cross-platform result.

Live timing begins after local capture has produced encoded media and requires
the complete requested capture interval. A single station leaves five extra
seconds before initiating hangup to accommodate small start-time differences.
A remote hangup can pass only after the local requested duration has actually
completed; early hangups fail. Grant permissions before retrying a run if a
first-use prompt delayed one side beyond the other side's grace period.

For file/camera, change `--mode file/camera`, omit `--bundle2`, and select the
camera and microphone when prompted. Use headphones; camera/microphone access
must be enabled for desktop applications in Windows privacy settings. Linux
native downloads use `./helper/modem-conference-helper acceptance ...`.

For actual macOS camera capture, run the script through the source-install app
bundle so the OS sees the camera/microphone usage descriptions. First run
`modem-conference --install-macos-launcher`, then invoke the printed app's
`Contents/MacOS/modem-conference --python scripts/manual_acceptance.py ...`.
The `--python` switch is a developer entry point in this generated launcher;
it preserves that Python environment and normal macOS authorization prompts.
Bare Python is suitable for the synthetic stress test, which opens no devices.

```sh
# Continuous real FFmpeg encoding with generated RGB/PCM, no OS devices opened:
uv run --no-sync scripts/manual_acceptance.py --mode stress --seconds 600 --output /tmp/encoder-stress.json

# Two physical modems; supply actual values for all placeholders:
uv run --no-sync scripts/manual_acceptance.py --mode file/file \
  --caller-port PORT_A --answerer-port PORT_B --number NUMBER \
  --bundle1 PREPARED_BUNDLE_A --bundle2 PREPARED_BUNDLE_B \
  --seconds 30 --output acceptance-file-file.json

# Camera/microphone permissions are requested explicitly. Choose devices in
# the dialog, or pass --camera2 HEX_ID and --microphone2 HEX_ID:
uv run --no-sync scripts/manual_acceptance.py --mode file/camera \
  --caller-port PORT_A --answerer-port PORT_B --number NUMBER \
  --bundle1 PREPARED_BUNDLE_A --seconds 600 --output acceptance-file-camera.json
```

For `camera/camera`, provide distinct available cameras/microphones for both
stations. One hardware camera may refuse to be opened twice. Device IDs are the
hex-encoded Qt device IDs; use the application's Devices dialog for ordinary
manual selection. Prepare file bundles by opening files in the application, or
with `python -m modem_conference.helper prepare INPUT_FILE OUTPUT_BUNDLE`.

Add `--exercise-video-overload` to a camera hardware test of at least 20
seconds. At ten seconds the tool deliberately pauses each active camera encoder
once, labels the event as a **forced acceptance probe**, and checks five seconds
later that audio continued and complete video pictures resumed. This exercises
restart/recovery; the separate high-motion synthetic test measures natural
bandwidth rejection.

The stress report records whole-picture video admission, audio continuity after
an intentional encoder restart, bounded input/parser buffers, encoder child
counts, peak **Python heap**, and sampled combined parent/encoder **RSS**. It
does not open camera/microphone hardware or prove modem control transport. The hardware modes
require media received on both channels at both stations, and clean worker and
capture shutdown. They save counts and diagnostics, with no encoded call recording.
Camera reports also require at least 90% of the expected 30 ms audio frames
over a full requested capture interval. The live-test clock starts after every
camera source has produced encoded media, so time spent granting permissions
does not shorten the capture run. File-only runs keep their send-time clock.
Reports record local preview counts, outgoing encoded
frame/picture and byte counts, bounded capture-status histories, local and
worker video-overload counters, and sampled parent/worker/encoder/decoder RSS.
RSS measurements are observations for trend inspection, not an enforced
machine-independent absolute-memory acceptance limit. Queue and encoder-child
bounds are checked separately by the synthetic stress test.

Bearer acceptance records both the raw V.80 in-band rate and the separately
validated carrier report. It accepts 14,400 bps from either explicit in-band
evidence or a consistent `+MCR: V32B`, `+MRR: 14400,14400`, `CONNECT 14400`
triple reported by the modem during connection. The report names the source;
an unspecified in-band rate remains unspecified. Requested/configured rates
never substitute for observed bearer evidence. A previous stricter report may
therefore remain failed while its recorded carrier lines support a separately
identified post-call check.

Record OS/version, Python/Qt versions, modem chipset and driver, connection path,
camera/microphone devices, call direction, actual modem rates, underrun counts,
and whether audio/video played successfully. Supplement automated reports with
manual device unplugging, denied permissions, a busy camera, disconnects,
pause/resume, repeated sends, high-motion-to-quiet-scene recovery, and closing
during initialization/conversion.

Hardware results belong in release validation notes only after execution. A
passing synthetic stress test is not physical camera/microphone or Linux modem
validation.
