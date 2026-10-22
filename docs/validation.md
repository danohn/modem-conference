# Alpha validation record

Software installation, native launch, capture devices and physical modem calls
are separate checks. This record deliberately distinguishes them.

## Published alpha

[`0.1.0a1` on PyPI](https://pypi.org/project/modem-conference/0.1.0a1/) and the
[GitHub alpha release](https://github.com/danohn/modem-conference/releases/tag/v0.1.0a1)
were published from `a6273e8b421dfcedf321340b177f2e3de8c724c3` through the
[production workflow](https://github.com/danohn/modem-conference/actions/runs/39730464679).
The supported-runtime matrix used released `h324==0.1.0a1`; TestPyPI exact-wheel
verification and clean installation passed before all four native builds and
PyPI Trusted Publishing. A subsequent clean macOS installation from production
PyPI passed helper, worker, resources and offscreen GUI startup outside the
checkout in a path containing spaces.

The four released native archives passed relocation/startup, content audit and
independent checksum verification. Each manifest records the released-index
library dependency, Python 3.14 and Qt 6.12. Linux additionally passed the clean
Ubuntu 24.04 container without system Python, uv or FFmpeg executables. Public
Python distribution hashes match the audited immutable build; the GitHub
release supplies native archives, wheel/source distributions, individual native
checksums and a combined `SHA256SUMS`. Physical hardware boundaries and the
unresolved live-call delay below remain applicable.

## Software and hardware evidence

| Area | Current evidence |
|---|---|
| Core protocols and async API | [284 installed-wheel tests on all 12 OS/Python combinations](https://github.com/danohn/h324/actions/runs/39727978028) |
| Client tests | [All 11 supported OS/Python combinations passed, plus the separate installed Linux/Python 3.11 rejection check](https://github.com/danohn/modem-conference/actions/runs/39727877298) |
| Clean wheel installation | CLI, resources, helper and GUI launch passed outside both checkouts on Python 3.11 and 3.14 |
| macOS physical file/file call | Passed at reported 14,400 bps in both directions, including pause/resume and repeated sending |
| Camera/microphone hardware | Ten-minute physical macOS file/camera call passed after the pacing correction; both directions decoded audio/video and restored their modems |
| Continuous encoding | Ten minutes passed with 19,997 of 20,000 expected audio frames, bounded buffers and video recovery |
| Four native downloads | [All four corrected candidates passed compilation, relocated helper/GUI launch and archive audit](https://github.com/danohn/modem-conference/actions/runs/39728215208), using core `3547027` and client `812676b`; released-index artifacts remain a separate publishing check |
| Linux without system Python | [Candidate helper, worker and GUI passed in a minimal Ubuntu 24.04 container without Python, uv or FFmpeg executables](https://github.com/danohn/modem-conference/actions/runs/39720565872) |
| Windows physical modem/capture | Earlier endpoint logs confirm over 600 seconds of live audio/video at 14,400 bps and successful modem restoration. The corrected short retest passed on Mac; the Windows user confirmed Idle, no errors and stopped capture after remote hangup. The corrected Windows log has not been reviewed. |
| Linux physical modem/capture | **Unverified** until hardware is available |

The earlier client matrix passed 63 tests on macOS and 62 tests plus one
macOS-only skip on Windows/Linux. A [subsequent run](https://github.com/danohn/modem-conference/actions/runs/39723873005)
passed its test assertions but aborted during Python 3.11 finalization on Linux.
An isolated diagnostic reproduced reference-count corruption with PySide 6.12.0
signals without importing this project. The same minimal test on macOS Python
3.11 did not reproduce the loss. The selected support policy retains Qt 6.12
everywhere and requires Python 3.12–3.14 for the Linux client; macOS/Windows
support Python 3.11–3.14. An installed-package subprocess check verifies that
Linux/Python 3.11 launchers reject execution before importing Qt, with useful
upgrade guidance. The independent library remains tested on Python 3.11–3.14
on all target operating systems. The current macOS suite passes 82 tests; the
other supported platforms pass 81 with one macOS-only skip. A subprocess
regression checks repeated Qt signal emissions and clean interpreter exit on
every supported combination, including Windows/Python 3.11.

The macOS file call used two USB CX93001 modems on macOS 27.0.1 (Apple Silicon),
analogue FXS ports and a local telephone switch. Both received codec streams
matched their sources byte for byte. The receivers decoded 11 and 23 pictures
(one endpoint sent a second copy), and 96,000 and 192,000 bytes of PCM audio.
Both modems confirmed profile restoration and serial-port release.

The final file regression used client `eed05ea` and core `3bac341` with freshly
prepared clips, including native MPEG-4 local previews. Both G.723.1 and H.263
streams again matched byte for byte, including the second send; pause/resume was
observed. The complete operation took 71.22 seconds and both ports were checked
free afterward. Received encoded bytes and decoded-picture counts are separate:
the decoder can retain a final picture until further input, so the byte-exact
twelve-picture clip produced eleven displayed pictures at the first receiver.

A separate installed-library async API call also passed with byte-exact streams,
pause/resume, zero framing errors and zero active underruns. The client camera
test used the FaceTime HD Camera and MacBook Pro Microphone through a proper
macOS app bundle with normal permission handling. Ten seconds produced 318
G.723.1 frames, five admitted H.263 pictures and 257 preview frames, then released
both devices without errors.

The continuous synthetic encoder test ran for 600 seconds with alternating noisy
and quiet input and a deliberate video restart. It generated 599.98 seconds of
PCM and encoded 19,997 audio frames (99.985% of the expected 20,000), plus 1,044
admitted video pictures. Audio continued after video restart. Encoder children
never exceeded two, queued raw input peaked at 45,438 bytes, and encoded parser
storage peaked at 1,716 bytes. Sampled combined parent/FFmpeg RSS settled around
178 MB; the maximum was 178,651,136 bytes. This is encoder evidence, not a passing
physical ten-minute modem call.

The sustained physical file/camera attempt delivered 9,377 live audio frames and
157 incoming H.263 pictures before a local synchronous transmit underrun. The
peer then detected damaged framing. Both restored their modems and released the
capture devices. That attempt did **not** pass the required ten-minute criterion;
the release workflow was cancelled before TestPyPI upload for the pacing
investigation.

The next physical attempt, with per-call macOS activity protection active,
failed after approximately 254 seconds of live capture. It delivered 8,424
G.723.1 frames and 135 decoded H.263 pictures before a transmit underrun. Both
actual bearer rates were 14,400 bps, live audio production reached 99.47% of the
expected frame count, and both modems and capture devices were released. The
activity guard did not resolve the pacing issue. Combined application/worker/
FFmpeg RSS peaked at about 653 MB; this broader process set is distinct from
the synthetic encoder measurement above.

Further attempts established that activity protection and bounded catch-up
batching alone did not prevent underruns. Instrumented garbage-collection pauses
did not coincide with the fatal gap. After separate physical buffering tests,
the library moved serial transmission to an independent thread with a bounded
900-wire-octet prime and verified scheduling requests. See the
[core pacing record](https://github.com/danohn/h324/blob/main/docs/validation.md)
for the failed attempts and limits of that change.

The corrected physical file/camera call passed **600.04 seconds of actual camera
capture**, using core `4e864d8` and client `eed05ea`. The complete operation,
including negotiation and cleanup, took 653.62 seconds. Both modems explicitly
reported 14,400 bps in both directions. There were no active underruns, overruns,
framing errors or cleanup errors. The live encoder produced 19,953 G.723.1
frames (99.76% of the expected count) and admitted 344 complete H.263 pictures.
The receiver obtained 19,936 audio frames and decoded 343 pictures; a short
buffered tail remained when hangup began. The opposite endpoint also received
and decoded the complete file's audio and video.

Video overload paused/restarted the live encoder 164 times while audio
continued. Transmit queues peaked at 362 and 714 bytes, below their 8,192-byte
limit. Sampled combined application/worker/encoder/decoder RSS peaked at
656,687,104 bytes (about 657 MB). Mean RSS declined from approximately 636 MB
during seconds 120–180 to 532 MB during seconds 540–600. Both cameras/audio
resources and workers shut down, modem restoration was confirmed, and both
serial ports were independently checked free. This is one passing ten-minute
physical test on the stated macOS hardware, rather than a guarantee of unlimited
call duration or physical Windows/Linux verification.

The next call used **native applications on Windows 11 and macOS**, with one
CX93001 modem per computer. Both downloads were built from core `4e864d8` and
client `eed05ea`. The maintainer operated the Windows GUI on COM6 and confirmed
incoming picture and sound. The Mac also displayed received video and counted
21,093 incoming audio frames with 1,172 H.263 picture starts. Its outgoing
capture produced 20,287 consecutive 30 ms audio frames (608.610 encoded seconds,
608.611 seconds of command wall time) and 700 pictures. No audio timestamp
discontinuities or worker errors were recorded. Mac-side actual bearer evidence
was 14,400 bps, the transmit queue peaked at 685 bytes, and cleanup confirmed
profile restoration and release of the Mac serial port.

Combined Mac app/helper/FFmpeg RSS peaked at approximately 532 MiB in samples
collected from 167 seconds after source start. Early and late active sample means
were approximately 517 and 510 MiB; the earlier startup peak was not measured.
Windows memory was not sampled. The Windows OS build, modem driver and
capture-device identities remain unverified.

The subsequently supplied Windows diagnostic log confirmed actual 14,400 bps,
633.75 seconds of consecutive outgoing audio before hangup, 20,283 received audio
frames and 700 received H.263 picture starts. Windows modem restoration succeeded
and its thread priority/timer requests were released. However, it recorded one
H.223 abort sequence with a partial video SDU exactly when the Mac hung up.
Capture continued while an error dialog was open, followed by 246 stale
"No connected call" errors. The sustained media and both modem restorations
passed; orderly remote disconnect **failed in that attempt**.

Core `3547027` adds bounded media draining and H.245 channel/EndSession closure
before modem teardown. Client `812676b` stops capture before reporting a terminal
error, discards stale media and uses nonblocking, coalesced error dialogs. Its
shutdown wait derives from the shared worker cleanup limits. Delayed-transport,
cleanup-deadline and nested Qt event-loop regressions pass.

The corrected physical retest used the native Windows
`preview-20261022-2` candidate and a macOS source-app acceptance harness, both
running core `3547027` and client `812676b`. The Mac requested a 60-second camera
test and recorded 65.10 seconds of actual capture. Its acceptance report passed,
with an observed 14,400 bps bearer, 1,291 received audio frames and 129 received
video AL3 SDUs, and decoded output of 64 pictures and 589,440 PCM bytes. The Mac
initiated graceful hangup; its session both sent and received EndSession.
There were no reported worker errors, active underruns or framing errors. Mac
modem restoration succeeded in 7.657 seconds, its serial port was separately
confirmed free, and no forced shutdown was needed.

The Windows user confirmed that the GUI returned to **Idle**, displayed no
errors and stopped capture after that remote hangup. This is direct operator
confirmation of the corrected Windows behavior; the current Windows diagnostic
log has **not** been reviewed, so its internal close sequence, cleanup report and
counters are not independently established by this retest. The earlier failed
disconnect remains recorded above. This short retest also does not replace the
earlier ten-minute media evidence with a new ten-minute soak.

The maintainer reported that movements arrived several seconds late. Mac
connection logs also showed repeated local encoder budget pauses while audio
continued. Separate synthetic measurements found one-picture lookahead in both
the elementary H.263 encoder parser and decoder: approximately 0.5 seconds per
stage at 2 fps, increasing at lower picture rates and across overload pauses.
These are acknowledged latency limitations, not transport errors. The subsequent
encoder-only local AVI packet framing passed a separate 600-second synthetic
test: 599.993 seconds of supplied PCM, 19,997 of 20,000 expected audio frames,
and 1,128 complete pictures. Audio continued across encoder restarts. Encoder
children peaked at two, queued raw input at 39,128 bytes, sampled combined RSS at
182,960,128 bytes, and Python heap at 341,585 bytes. A single-frame regression
also requires an encoded picture before another input frame or EOF. The measured
sender saving is approximately one picture interval (about 0.5 seconds at 2 fps).
The corrected physical retest did **not** establish an end-to-end latency gain:
the maintainer still reported both audio and video arriving several seconds
late. Mac capture produced 2,117 audio frames but admitted only six video
pictures, with 29 local video-budget pauses during the 65.10-second interval.
The visible pause status therefore reflects substantial congestion in this
scene. Receiver lookahead and congestion/restart delays remain limitations;
the cause and size of the reported audio delay have not been isolated. Passing
transport integrity and orderly hangup do not establish low media latency.

An earlier attempt failed during initial framing acquisition. It was retained as
a known startup-reliability issue, and the application restored both modems. The
successful retry does not make that failed attempt disappear. See the
[core record](https://github.com/danohn/h324/blob/main/docs/validation.md).

The original local lab archive and its 191 passing tests are preserved. Portable
client and protocol tests were moved to their owning packages; historical PBX,
V.34 and capture-analysis experiments remain in the archive.

Use the [manual acceptance instructions](hardware-testing.md) to record a new
modem, OS and driver combination. Reports may contain device names and telephone
numbers; review them before sharing. Raw media capture is opt-in and local
acceptance recordings are not part of the public distributions.
