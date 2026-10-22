# Third-party notices

Original Modem Conference source is MIT licensed. Dependencies, runtime libraries
and standards resources retain their own licenses. This file does not relicense
them. Inspect the exact installed versions and included license texts when
redistributing an application build.

| Component | License / SPDX | Upstream source |
|---|---|---|
| h324 | MIT for original code; separately documented ITU H.245 ASN.1 resource | <https://github.com/danohn/h324> |
| PySide6 / Shiboken6 and the used Qt modules | LGPL-3.0-only, or applicable GPL/commercial alternative, per file/module | <https://code.qt.io/pyside/pyside-setup.git/> and <https://code.qt.io/qt/> |
| platformdirs | MIT | <https://github.com/tox-dev/platformdirs> |
| pySerial (through h324) | BSD-3-Clause | <https://github.com/pyserial/pyserial> |
| asn1tools (through h324) | MIT | <https://github.com/eerimoq/asn1tools> |
| bitstruct (through asn1tools) | MIT | <https://github.com/eerimoq/bitstruct> |
| pyparsing (through asn1tools) | MIT | <https://github.com/pyparsing/pyparsing> |
| CPython, included only in native downloads | Python-2.0 and bundled third-party notices in Python's license | <https://www.python.org/downloads/source/> |

The application uses Qt Core, Gui, Widgets, Network, Multimedia and
MultimediaWidgets. Their corresponding Qt/PySide source headers and license texts
control the applicable licensing choices; the MIT license for this project does
not replace them. See [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html).

Native previews dynamically link Qt/PySide shared libraries and retain them as
separate files. Included license texts and notices are under `notices/`, or
`Contents/Resources/notices/` on macOS. Users may replace these libraries with
compatible modified versions under the applicable licenses. No restriction on
reverse engineering for debugging such modifications is imposed by this project.
Rebuild instructions and the exact tool versions are in `native/` and
`docs/release.md`; source is public in this repository. Corresponding upstream
Qt 6.12 source archives are available at
<https://download.qt.io/archive/qt/6.12/> and PySide sources at
<https://download.qt.io/official_releases/QtForPython/pyside6/>.

The native build copies license files distributed with each installed runtime
dependency. `h324`'s included notices describe the provenance and separate terms
of its ASN.1 definitions. No ITU recommendation PDF or lab capture is distributed.

Nuitka, ordered-set, zstandard and (on Linux) patchelf are build tools, not shipped
as command-line tools in the application. Nuitka's compiler license and runtime
exception apply to its own material; compiling does not change the license of
our application. See <https://nuitka.net/pages/overview.html#license>.

FFmpeg and ffprobe **executables** are external dependencies and are not bundled
in these downloads. Their license depends on the independently installed build
and enabled codecs; obtain source and license information from that distributor
and <https://ffmpeg.org/legal.html>. Qt Multimedia's separately licensed FFmpeg
backend can include LGPL FFmpeg shared libraries as part of Qt's runtime. Those
libraries and their notices are distinct from the external command-line encoder.
The Qt 6.12 wheel backend reports FFmpeg 9.0.1 (LGPL-2.1-or-later); corresponding
FFmpeg source is at <https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz>.

Test media is generated synthetically. Fixture provenance and generation details
are in the corresponding test-data manifest. No historic product artwork, font,
logo or third-party video recording is included; the theme is our own rendering
of period desktop conventions.
