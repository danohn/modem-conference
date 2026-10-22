# Hardware and continuous-capture acceptance

Run from a development environment with the client and library installed. The
script does not assume port names, phone numbers, local network equipment, or
particular camera/microphone identifiers.

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

The stress report records whole-picture video admission, audio continuity after
an intentional encoder restart, bounded input/parser buffers, encoder child
counts, peak **Python heap**, and sampled combined parent/encoder **RSS**. It
does not open camera/microphone hardware or prove modem control transport. The hardware modes
require media received on both channels at both stations, and clean worker and
capture shutdown. They save counts and diagnostics, with no encoded call recording.

Record OS/version, Python/Qt versions, modem chipset and driver, connection path,
camera/microphone devices, call direction, actual modem rates, underrun counts,
and whether audio/video played successfully. Supplement automated reports with
manual device unplugging, denied permissions, a busy camera, disconnects,
pause/resume, repeated sends, high-motion-to-quiet-scene recovery, and closing
during initialization/conversion.

Hardware results belong in release validation notes only after execution. A
passing synthetic stress test is not physical camera/microphone or Linux modem
validation.
