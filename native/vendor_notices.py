"""Refresh upstream license texts for the fixed Qt 6.12 native runtime.

This maintainer command downloads license/attribution files only, never runtime
code. Its manifest records immutable upstream commits, URLs and SHA-256 values.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import urllib.request

DESTINATION = Path(__file__).resolve().parents[1] / "LICENSES"
REPOSITORIES = ("qtbase", "qtmultimedia", "qtsvg")
REF = "v6.12.0"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "modem-conference-license-manifest"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def save(item: tuple[str, str]) -> dict:
    relative, url = item
    data = fetch(url)
    destination = DESTINATION / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return {"path": relative, "url": url, "sha256": hashlib.sha256(data).hexdigest()}


def main() -> int:
    downloads = []
    commits = {}
    for repo in REPOSITORIES:
        tree = json.loads(fetch(f"https://api.github.com/repos/qt/{repo}/git/trees/{REF}?recursive=1"))
        if tree.get("truncated"):
            raise RuntimeError(f"Incomplete upstream tree: {repo}")
        commit = tree["sha"]
        commits[repo] = commit
        paths = []
        for item in tree["tree"]:
            path = PurePosixPath(item["path"])
            if item["type"] != "blob":
                continue
            if path.parts[0] == "LICENSES" or (
                str(path).startswith("src/3rdparty/") and (
                    path.name.upper().startswith(("LICENSE", "COPYING", "COPYRIGHT"))
                    or path.name == "qt_attribution.json"
                )
            ):
                paths.append(str(path))
        downloads += [(f"qt/{repo}/{path}", f"https://raw.githubusercontent.com/qt/{repo}/{commit}/{path}") for path in paths]
    downloads += [(f"ffmpeg/{name}", f"https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.1/{name}")
                  for name in ("COPYING.LGPLv2.1", "COPYING.LGPLv3", "COPYING.GPLv2", "COPYING.GPLv3", "LICENSE.md")]
    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(pool.map(save, downloads))
    manifest = {"qt_version": "6.12.0", "ffmpeg_version": "9.0.1", "qt_commits": commits,
                "note": "Superset of upstream runtime notices; inclusion does not imply every optional component is linked.",
                "files": sorted(entries, key=lambda item: item["path"])}
    DESTINATION.mkdir(parents=True, exist_ok=True)
    (DESTINATION / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {len(entries)} upstream license/attribution files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
