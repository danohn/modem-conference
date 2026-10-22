# Native preview builds

Build from an installed client wheel, using CPython 3.14 and the compiler tools in
`requirements-build.txt`. `build.py` invokes the installed `pyside6-deploy` for
the GUI and Nuitka standalone mode for the console helper. FFmpeg stays external.

```sh
uv run --no-project --python 3.14 --with modem-conference==0.1.0a1 --with-requirements native/requirements-build.txt native/build.py
```

The build writes only `build/native/` and `dist/native/`. Run `native/smoke.py`
against the staged directory before distributing its archive. The smoke test
moves a copy to a path containing spaces, clears Python-specific environment
variables, excludes Python/uv and FFmpeg directories from PATH, launches the
helper and opens/closes the GUI without modem access. This is an installed-runtime
check; real camera, audio and modem checks remain separate.

The workflows build independently on macOS arm64, macOS x64, Windows x64 and
Ubuntu 24.04 x64. There is no cross-compilation. Preview downloads are unsigned
and unnotarized. Inspect source and checksums before running them. See
`docs/release.md` for release gates and opening instructions.
