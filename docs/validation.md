# Alpha validation record

Software installation, native launch, capture devices and physical modem calls
are separate checks. This record deliberately distinguishes them.

| Area | Current evidence |
|---|---|
| Core protocols and async API | [165 installed-wheel tests on all 12 OS/Python combinations](https://github.com/danohn/h324/actions/runs/39717829292) |
| Client source tests | 31 tests passed locally on macOS; cross-platform CI is being completed |
| Clean wheel installation | CLI, resources, helper and GUI launch passed outside both checkouts on Python 3.11 and 3.14 |
| macOS physical file/file call | Passed at reported 14,400 bps in both directions, including pause/resume and repeated sending |
| Camera/microphone hardware | Pending app-bundle permission and sustained-capture validation |
| Four native downloads | Build and relocated-launch checks in progress |
| Windows physical modem/capture | Awaiting maintainer-run acceptance script |
| Linux physical modem/capture | **Unverified** until hardware is available |

The macOS file call used two USB CX93001 modems on macOS 27.0.1 (Apple Silicon),
analogue FXS ports and a local telephone switch. Both received codec streams
matched their sources byte for byte. The receivers decoded 11 and 23 pictures
(one endpoint sent a second copy), and 96,000 and 192,000 bytes of PCM audio.
Both modems confirmed profile restoration and serial-port release.

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
