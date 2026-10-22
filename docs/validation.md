# Alpha validation record

Software installation, native launch, capture devices and physical modem calls
are separate checks. This record deliberately distinguishes them.

| Area | Current evidence |
|---|---|
| Core protocols and async API | [227 installed-wheel tests on all 12 OS/Python combinations](https://github.com/danohn/h324/actions/runs/39722947196) |
| Client tests | [63 tests passed on macOS; 62 passed and one macOS-only check skipped on Windows/Linux, across all 12 OS/Python combinations](https://github.com/danohn/modem-conference/actions/runs/39722014594) |
| Clean wheel installation | CLI, resources, helper and GUI launch passed outside both checkouts on Python 3.11 and 3.14 |
| macOS physical file/file call | Passed at reported 14,400 bps in both directions, including pause/resume and repeated sending |
| Camera/microphone hardware | Ten-minute physical macOS file/camera call passed after the pacing correction; both directions decoded audio/video and restored their modems |
| Continuous encoding | Ten minutes passed with 19,997 of 20,000 expected audio frames, bounded buffers and video recovery |
| Four native downloads | All four candidate builds passed compilation, relocated helper/GUI launch and archive audit; final source revision must be rebuilt |
| Linux without system Python | [Candidate helper, worker and GUI passed in a minimal Ubuntu 24.04 container without Python, uv or FFmpeg executables](https://github.com/danohn/modem-conference/actions/runs/39720565872) |
| Windows physical modem/capture | Awaiting maintainer-run acceptance script |
| Linux physical modem/capture | **Unverified** until hardware is available |

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
