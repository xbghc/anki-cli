"""Read/write sync credentials at ~/.config/anki-cli/config.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from anki_cli.paths import config_dir, config_path


@dataclass
class SyncConfig:
    username: str
    hostkey: str
    endpoint: str = ""


def load() -> SyncConfig | None:
    path = config_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    sync = data.get("sync") or {}
    hostkey = sync.get("hostkey")
    username = sync.get("username")
    if not hostkey or not username:
        return None
    return SyncConfig(
        username=username,
        hostkey=hostkey,
        endpoint=sync.get("endpoint", ""),
    )


def save(cfg: SyncConfig) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    payload = {"sync": asdict(cfg)}
    path = config_path()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    path.chmod(0o600)
