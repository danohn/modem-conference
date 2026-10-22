"""Per-user settings and explicit serial-device identity selection."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib

from platformdirs import user_cache_path, user_config_path, user_log_path
from serial.tools import list_ports


def directories():
    return {"config": user_config_path("modem-conference", appauthor=False),
            "cache": user_cache_path("modem-conference", appauthor=False),
            "logs": user_log_path("modem-conference", appauthor=False)}


def load_settings(path: Path | None = None) -> dict:
    path = path or directories()["config"] / "settings.toml"
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except FileNotFoundError:
        return {}


def save_settings(values: dict, path: Path | None = None):
    """Write our flat string-valued configuration atomically as TOML."""
    path = path or directories()["config"] / "settings.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(f"{key} = {json.dumps(str(value), ensure_ascii=False)}\n"
                      for key, value in sorted(values.items())
                      if key.replace("_", "").isalnum() and value is not None)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def serial_devices():
    return sorted(list_ports.comports(), key=lambda item: item.device)


def device_identity(device) -> str:
    if device.serial_number:
        return f"usb:{device.vid}:{device.pid}:{device.serial_number}"
    return f"path:{device.device}"


def restore_port(identity: str, devices=None) -> str:
    """An absent or duplicated identity requires the user to select a port."""
    matches = [d.device for d in (serial_devices() if devices is None else devices)
               if device_identity(d) == identity]
    return matches[0] if len(matches) == 1 else ""
