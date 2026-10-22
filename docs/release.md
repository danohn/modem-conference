# Releasing Modem Conference

The preview uses the separately released `h324` package. Publish and verify the
core library first. Development CI may build an explicitly selected core Git ref;
release CI and native release downloads resolve the pinned dependency from PyPI.

Current platform and physical-device evidence is tracked in
[validation.md](validation.md).

## Supported Python runtimes

Source installations use **Python 3.11–3.14 on macOS and Windows**, and
**Python 3.12–3.14 on Linux**, with Qt/PySide 6.12 on every supported platform.
The Linux PySide6 6.12.0 wheel loses boolean references during signal emission
on Python 3.11; the isolated [diagnostic reproducer](https://github.com/danohn/modem-conference/actions/runs/39725773187)
records the resulting interpreter shutdown failure. Client launchers reject
that unsupported combination before importing Qt and explain how to use a
supported interpreter. An older Qt release is not selected automatically.

Python package metadata retains `Requires-Python >=3.11` because it cannot express
this operating-system-specific minimum. Installation on Linux Python 3.11 can
therefore complete; client execution is deliberately refused. The independent
`h324` library still supports Python 3.11–3.14 on all three operating systems.

Normal client CI runs eleven supported OS/Python combinations. A separate
Linux Python 3.11 installed-wheel check verifies the rejection message before
any Qt import, package resources and continued headless `h324` use. It does not
run GUI tests on that unsupported runtime. Core CI retains all twelve
OS/Python combinations. Native downloads continue to bundle Python 3.14 and
Qt 6.12, so they do not depend on the receiving machine's Python installation.

## Publishing setup

Configure protected GitHub environments `testpypi`, `pypi` and `release`, requiring
maintainer approval and restricting production to version tags. Configure pending
or existing Trusted Publishers separately on TestPyPI and PyPI:

| Field | Value |
|---|---|
| Owner | `danohn` |
| Repository | `modem-conference` |
| Workflow | `release.yml` |
| Environment | `testpypi` on TestPyPI; `pypi` on PyPI |

No PyPI password or long-lived token is stored in the repository. Only the publish
jobs have OIDC permission. GitHub release creation has its own environment and
contents-write permission. See [PyPI's publishing documentation](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## Build and release

1. Review source, third-party notices and platform claims. Run all package and
   installed-wheel tests. Update both the static client version and pinned core
   dependency when needed.
2. Dispatch **Publish Python and native release** with `publish_pypi=false`.
   Tests install the released core dependency. TestPyPI receives audited wheel
   and sdist artifacts; a separate job retrieves the exact wheel, compares its
   SHA-256 and launches the installed helper and GUI from outside the checkout.
3. Push `vVERSION` at the reviewed commit and dispatch on that tag with
   `publish_pypi=true`. After TestPyPI verification, all four native builds must
   compile and pass relocated smoke tests before PyPI publishing can proceed.
   Approve `pypi`, then `release`, to publish the package and attach unsigned
   archives plus individual SHA-256 files to a GitHub prerelease.

TestPyPI retries can reuse an existing artifact only if its exact wheel bytes
match the current build. Use a new version after changing an uploaded release.

## Native download contract

| Build | Runner | Archive |
|---|---|---|
| macOS Apple Silicon | macos-15 | `.app` in ZIP |
| macOS Intel | macos-15-intel | `.app` in ZIP |
| Windows x64 | windows-2022 | portable directory in ZIP |
| Linux x64 | ubuntu-24.04 | application directory in `.tar.gz` |

Native builds use CPython 3.14, Qt/PySide 6.12 and pinned Nuitka tools.
`native/build.py` generates a `pyside6-deploy` standalone specification, compiles
the GUI, compiles a separate console helper and places the helper inside the
distribution. This avoids interpreting a frozen executable as `python -m`.
See [Qt deployment options](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html)
and the [Nuitka standalone manual](https://nuitka.net/user-documentation/user-manual.html).

Downloads include Python, Qt shared libraries, application resources and license
notices. They require neither Python nor `uv` on the receiving machine. FFmpeg
and ffprobe remain external and must be selected in settings or available on
PATH. No FFmpeg executable is bundled. Qt Multimedia may include LGPL FFmpeg
shared libraries for its own backend; the bundled notices cover them separately.
Qt shared libraries remain replaceable;
third-party license notices and source links are included under `notices` (macOS:
`Contents/Resources/notices`). Compilation reports are CI diagnostic artifacts,
not part of the public native archive.

Each build moves a copy into a path containing spaces and launches the helper
and GUI with an empty PATH and cleared Python/Qt build environment variables.
The smoke check opens no modem, camera or microphone. A successful smoke test
does not establish device compatibility or full desktop integration.

Linux additionally runs the staged application read-only in an Ubuntu 24.04
container with desktop OS libraries and fonts only. The required check verifies
that Python, uv, ffmpeg and ffprobe executables and Python packages are absent,
then runs the helper, protocol/schema initialization and GUI with networking
disabled. The application supplies its own bundled runtime. macOS and Windows
use the relocated empty-PATH check; independent machine validation is reported
separately. `clean-runtime.yml` can repeat the Linux check against a previously
built native artifact without recompiling it.

## Opening unsigned previews

- **macOS 14.4+:** extract the ZIP and move the app to Applications. Gatekeeper
  may require right-click → Open, or Privacy & Security → Open Anyway after
  inspecting the source and checksum. The app is not Developer ID signed or
  notarized. Camera/microphone access still requires explicit OS permission.
- **Windows 10/11 x64:** extract the whole ZIP before running
  `modem-conference.exe`. Keep `helper/` and the DLLs alongside it. SmartScreen
  may show an unsigned-publisher prompt; inspect the checksum and source first.
- **Ubuntu 24.04+ x64:** extract the whole archive and run
  `./ModemConference/modem-conference`. Keep shared libraries and `helper/` in
  place. Serial devices may require group permissions; the app reports access
  failures and does not change system permissions itself.

## Validation labels

Report separately: package installation, automated protocol/media tests, native
launch, capture-device validation, and physical modem calls. CI lacks analogue
modems and must not claim hardware validation. Linux physical modem and capture
device behavior remain unverified until tested on real hardware. Record Windows
and macOS modem/driver/OS combinations, the negotiated bearer rate, call cleanup,
and results of sustained live capture separately. Do not tag the alpha as stable.
