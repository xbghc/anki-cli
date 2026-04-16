"""XDG base-directory paths for anki-cli."""

from __future__ import annotations

import os
from pathlib import Path


def _xdg(env: str, default_rel: str) -> Path:
    value = os.environ.get(env)
    return Path(value) if value else Path.home() / default_rel


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "anki-cli"


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "anki-cli"


def config_path() -> Path:
    return config_dir() / "config.json"


def collection_path() -> Path:
    return data_dir() / "collection.anki2"
