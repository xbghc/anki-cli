"""Helpers for opening the local Anki collection."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import click
from anki.collection import Collection

from anki_cli.paths import collection_path


@contextmanager
def open_collection() -> Iterator[Collection]:
    """Open the local collection, or fail loudly if it hasn't been synced yet."""
    path = collection_path()
    if not path.exists():
        raise click.ClickException(
            "no local collection found; run `anki sync` first to pull from AnkiWeb"
        )
    col = Collection(str(path))
    try:
        yield col
    finally:
        col.close()
