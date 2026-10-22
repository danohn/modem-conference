"""Build an unsigned, relocatable application plus its isolated worker helper.

Run using the Python environment containing the *installed* client wheel and
native/requirements-build.txt. No source checkout is put on PYTHONPATH.
"""
from __future__ import annotations

import argparse
import configparser
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str], **kwargs) -> None:
    print("+", subprocess.list2cmdline(argv), flush=True)
    subprocess.run(argv, check=True, **kwargs)


def copy_notices(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        source = ROOT / name
        if not source.is_file():
            raise RuntimeError(f"Required notice is missing: {name}")
        shutil.copy2(source, destination / name)
    if not (ROOT / "LICENSES" / "manifest.json").is_file():
        raise RuntimeError("Vendored native-runtime license manifest is missing")
    shutil.copytree(ROOT / "LICENSES", destination / "upstream", dirs_exist_ok=True)
    # Include runtime dependency licenses plus Nuitka's linked C runtime and
    # Runtime Library Exception. The compiler executable is not distributed.
    for name in ("modem-conference", "h324", "PySide6", "PySide6_Essentials",
                 "PySide6_Addons", "shiboken6", "pyserial", "asn1tools",
                 "bitstruct", "pyparsing", "platformdirs", "Nuitka"):
        dist = metadata.distribution(name)
        for file in dist.files or ():
            if name == "Nuitka" and file.suffix == ".j2":
                continue  # A license-report code template is not a license text.
            if any(part.lower() in {"licenses", "license", "copying"} for part in file.parts) or (
                file.name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))
            ):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = destination / name / str(file).replace("..", "_")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    (destination / "RUNTIME.md").write_text(
        "# Native preview runtime\n\nPython and Qt are included; FFmpeg is external.\n"
        "Qt/PySide shared libraries remain separate for replacement under their licenses.\n"
        "Source: https://github.com/danohn/modem-conference\n"
        "Qt source: https://download.qt.io/archive/qt/6.12/\n"
        "PySide source: https://download.qt.io/official_releases/QtForPython/pyside6/\n"
        "CPython source: https://www.python.org/downloads/source/\n"
        "See the included license files and third-party notices.\n",
        encoding="utf-8",
    )
    import sysconfig
    python_license = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, destination / "PYTHON-LICENSE.txt")


def archive_tree(staged: Path, output: Path, stem: str) -> Path:
    if sys.platform == "linux":
        archive = output / f"{stem}.tar.gz"
        with tarfile.open(archive, "w:gz") as stream:
            stream.add(staged, arcname=staged.name)
    else:
        archive = output / f"{stem}.zip"
        # ditto preserves framework symlinks and executable permissions on macOS.
        if sys.platform == "darwin":
            run(["ditto", "-c", "-k", "--keepParent", str(staged), str(archive)])
        else:
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as stream:
                for file in staged.rglob("*"):
                    if file.is_file():
                        stream.write(file, str(file.relative_to(staged.parent)))
    return archive


def make_icon(work: Path) -> Path:
    """Render our own period-style artwork; do not ship Qt's template logo."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(str(ROOT / "native" / "icon.svg"))
    if not renderer.isValid():
        raise RuntimeError("Invalid application icon")
    def render(size: int, destination: Path) -> None:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        if not image.save(str(destination)):
            raise RuntimeError(f"Cannot write icon: {destination.name}")
    if sys.platform == "darwin":
        iconset = work / "ModemConference.iconset"
        iconset.mkdir(exist_ok=True)
        for size in (16, 32, 128, 256, 512):
            render(size, iconset / f"icon_{size}x{size}.png")
            render(size * 2, iconset / f"icon_{size}x{size}@2x.png")
        icon = work / "ModemConference.icns"
        run(["iconutil", "-c", "icns", "-o", str(icon), str(iconset)])
    elif sys.platform == "win32":
        icon = work / "ModemConference.ico"
        render(64, icon)
    else:
        icon = work / "ModemConference.png"
        render(256, icon)
    return icon


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Generate/inspect GUI deployment command only")
    parser.add_argument("--jobs", type=int, default=2, help="Maximum parallel C compilations")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    import PySide6
    if PySide6.__version__ != "6.12.0":
        raise RuntimeError("Native previews require Qt/PySide 6.12.0 to match their notices")
    version = metadata.version("modem-conference")
    work = ROOT / "build" / "native"
    output = ROOT / "dist" / "native"
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    gui = work / "gui"
    gui.mkdir(exist_ok=True)
    launcher = gui / "launcher.py"
    shutil.copy2(ROOT / "native" / "launcher.py", launcher)
    spec_path = gui / "pysidedeploy.spec"
    deploy = shutil.which("pyside6-deploy")
    if not deploy:
        raise RuntimeError("pyside6-deploy is missing from the active environment")
    run([deploy, str(launcher), "--init", "--force", "-c", str(spec_path)], cwd=gui)
    spec = configparser.ConfigParser()
    spec.read(spec_path)
    spec["app"].update(title="ModemConference", project_dir=str(gui),
                       input_file=str(launcher), exec_directory=str(work / "gui-output"))
    spec["app"]["icon"] = str(make_icon(work))
    spec["python"]["packages"] = "Nuitka==4.3.1,ordered-set==4.1.0,zstandard==0.25.0"
    if sys.platform == "linux":
        spec["python"]["packages"] += ",patchelf==0.19.1.0"
    spec["qt"]["modules"] = "Core,Gui,Widgets,Multimedia,MultimediaWidgets,Network"
    spec["qt"]["plugins"] = "multimedia"
    extra = ["--assume-yes-for-downloads", f"--jobs={args.jobs}",
             "--include-package=modem_conference", "--include-package=h324",
             "--include-package-data=h324", "--include-package-data=modem_conference",
             "--include-distribution-metadata=modem-conference",
             "--include-distribution-metadata=h324", "--output-filename=modem-conference",
             "--report=compilation-report.xml", "--noinclude-qt-translations"]
    if sys.platform == "win32":
        extra += ["--msvc=latest", "--windows-console-mode=disable"]
    if sys.platform == "darwin":
        extra += ["--macos-app-name=Modem Conference",
                  "--macos-app-version=0.1.0", "--macos-signed-app-name=org.modemconference.preview",
                  "--macos-app-macos-min-version=14.4"]
    spec["nuitka"]["mode"] = "standalone"
    spec["nuitka"]["extra_args"] = subprocess.list2cmdline(extra) if sys.platform == "win32" else __import__("shlex").join(extra)
    spec["nuitka"]["macos.permissions"] = (
        "NSCameraUsageDescription:Transmit camera video during a modem call,"
        "NSMicrophoneUsageDescription:Transmit microphone audio during a modem call"
    ) if sys.platform == "darwin" else ""
    with spec_path.open("w", encoding="utf-8") as stream:
        spec.write(stream)
    command = [deploy, "--force", "--no-install", "--keep-deployment-files", "-c", str(spec_path)]
    if args.dry_run:
        run(command + ["--dry-run"], cwd=gui)
        return 0
    run(command, cwd=gui)
    candidates = list((work / "gui-output").glob("*.app" if sys.platform == "darwin" else "*.dist"))
    if len(candidates) != 1:
        raise RuntimeError(f"Expected exactly one GUI output directory, found {candidates}")
    stage = work / "stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    staged = stage / ("Modem Conference.app" if sys.platform == "darwin" else "ModemConference")
    shutil.copytree(candidates[0], staged, symlinks=True)
    helper_output = work / "helper-output"
    helper_command = [sys.executable, "-m", "nuitka", "--mode=standalone",
                      "--enable-plugin=pyside6", "--assume-yes-for-downloads",
                      f"--jobs={args.jobs}", "--output-filename=modem-conference-helper",
                      f"--output-dir={helper_output}", "--include-package=h324",
                      "--include-package-data=h324", "--include-package-data=modem_conference",
                      "--include-distribution-metadata=h324", "--include-distribution-metadata=modem-conference",
                      "--report=helper-compilation-report.xml"]
    if sys.platform == "win32":
        helper_command += ["--msvc=latest", "--windows-console-mode=force"]
    run(helper_command + [str(ROOT / "native" / "helper.py")], cwd=work)
    helper_candidates = list(helper_output.glob("*.dist"))
    if len(helper_candidates) != 1:
        raise RuntimeError(f"Expected one helper output, found {helper_candidates}")
    if sys.platform == "darwin":
        helper_target = staged / "Contents" / "Helpers" / "modem-conference-helper.dist"
        notices = staged / "Contents" / "Resources" / "notices"
        plist = staged / "Contents" / "Info.plist"
        data = plistlib.loads(plist.read_bytes())
        data["LSMinimumSystemVersion"] = "14.4"
        data["NSCameraUsageDescription"] = "Transmit camera video during a modem call."
        data["NSMicrophoneUsageDescription"] = "Transmit microphone audio during a modem call."
        plist.write_bytes(plistlib.dumps(data))
    else:
        helper_target = staged / "helper"
        notices = staged / "notices"
    helper_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(helper_candidates[0], helper_target, symlinks=True)
    # Installer-local wheel URLs have no runtime purpose and can expose the
    # build checkout. Keep version/license metadata and our public provenance.
    for installer_record in staged.rglob("direct_url.json"):
        if any(part.endswith(".dist-info") for part in installer_record.parts):
            installer_record.unlink()
    copy_notices(notices)
    manifest = {"version": version, "python": platform.python_version(),
                "platform": sys.platform, "machine": platform.machine(),
                "qt": PySide6.__version__, "nuitka": metadata.version("Nuitka"),
                "h324": metadata.version("h324"), "signed": False,
                "ffmpeg_executables_bundled": False,
                "qt_multimedia_ffmpeg_backend_libraries": "Qt runtime; see notices",
                "core_ref": os.environ.get("H324_BUILD_REF", "released-index")}
    (notices / "build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if sys.platform == "darwin":
        # Editing Info.plist and adding the helper invalidates Nuitka's ad-hoc
        # signature. Renew it after staging; this is not Developer ID signing.
        run(["codesign", "--force", "--deep", "--sign", "-", str(staged)])
    # Run after copying; relocation catches helper lookup and absolute-path errors.
    run([sys.executable, str(ROOT / "native" / "smoke.py"), str(staged)])
    arch = {"arm64": "arm64", "aarch64": "arm64", "AMD64": "x64", "x86_64": "x64"}.get(platform.machine(), platform.machine())
    label = {"darwin": "macos", "win32": "windows", "linux": "linux"}[sys.platform]
    archive = archive_tree(staged, output, f"modem-conference-{version}-{label}-{arch}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / f"{archive.name}.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(json.dumps({"archive": str(archive), "stage": str(staged), "sha256": digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
