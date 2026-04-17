"""CLI entry point — command group wiring."""

from __future__ import annotations

import json

import click

from anki_cli import __version__, config
from anki_cli.paths import config_path


@click.group()
@click.version_option(__version__, "-V", "--version", prog_name="anki")
def main() -> None:
    """Headless Anki sync client with JSON I/O."""


@main.command()
@click.option("--username", "-u", help="AnkiWeb email or username.")
@click.option(
    "--password",
    "-p",
    help="AnkiWeb password (omit to prompt; never logged or stored).",
)
@click.option(
    "--endpoint",
    default=None,
    help="Custom sync endpoint (default: AnkiWeb).",
)
def login(username: str | None, password: str | None, endpoint: str | None) -> None:
    """Log into AnkiWeb and save sync credentials locally."""
    from anki._backend import RustBackend
    from anki.errors import SyncError
    from anki.sync_pb2 import SyncLoginRequest

    if not username:
        username = click.prompt("Username (email)", type=str)
    if not password:
        password = click.prompt("Password", type=str, hide_input=True)

    from anki_cli._pylib import run_off_main

    backend = RustBackend()
    try:
        auth = run_off_main(
            backend.sync_login,
            SyncLoginRequest(username=username, password=password, endpoint=endpoint),
        )
    except SyncError as err:
        raise click.ClickException(f"login failed: {err}") from err

    cfg = config.SyncConfig(
        username=username,
        hostkey=auth.hkey,
        endpoint=auth.endpoint or "",
    )
    config.save(cfg)

    click.echo(
        json.dumps(
            {
                "status": "ok",
                "username": username,
                "endpoint": cfg.endpoint or "ankiweb",
                "config_path": str(config_path()),
            },
            indent=2,
        )
    )


@main.command()
def sync() -> None:
    """Synchronize the local collection with AnkiWeb (bidirectional incremental)."""
    from anki.collection import Collection
    from anki.errors import SyncError
    from anki.sync import SyncAuth
    from anki.sync_pb2 import SyncCollectionResponse

    from anki_cli._pylib import run_off_main
    from anki_cli.paths import collection_path, data_dir

    cfg = config.load()
    if cfg is None:
        raise click.ClickException("not logged in; run `anki login` first")

    data_dir().mkdir(parents=True, exist_ok=True)
    auth = SyncAuth(
        hkey=cfg.hostkey,
        endpoint=cfg.endpoint or None,
        io_timeout_secs=30,
    )

    col = Collection(str(collection_path()))
    try:
        try:
            result = run_off_main(col.sync_collection, auth, False)
        except SyncError as err:
            raise click.ClickException(f"sync failed: {err}") from err

        if result.new_endpoint:
            cfg.endpoint = result.new_endpoint
            config.save(cfg)
            auth = SyncAuth(
                hkey=cfg.hostkey,
                endpoint=result.new_endpoint,
                io_timeout_secs=30,
            )

        required = result.required
        action: str
        if required == SyncCollectionResponse.NO_CHANGES:
            action = "no_changes"
        elif required == SyncCollectionResponse.NORMAL_SYNC:
            action = "normal_sync"
        elif required == SyncCollectionResponse.FULL_DOWNLOAD:
            col.close_for_full_sync()
            try:
                run_off_main(
                    col.full_upload_or_download,
                    auth=auth,
                    server_usn=None,
                    upload=False,
                )
            except SyncError as err:
                raise click.ClickException(f"full download failed: {err}") from err
            action = "full_download"
        elif required == SyncCollectionResponse.FULL_UPLOAD:
            raise click.ClickException(
                "FULL_UPLOAD required — remote collection is empty. "
                "Refusing automatic upload; resolve manually if intended."
            )
        else:  # FULL_SYNC
            raise click.ClickException(
                "FULL_SYNC required — local and remote have diverged. "
                "Resolve manually (choose upload or download) before retrying."
            )
    finally:
        col.close()

    click.echo(
        json.dumps(
            {
                "status": "ok",
                "action": action,
                "server_message": result.server_message,
            },
            indent=2,
        )
    )


@main.command()
def decks() -> None:
    """List all decks as JSON."""
    raise click.ClickException("not implemented")


@main.command()
def notetypes() -> None:
    """List all note types as JSON."""
    raise click.ClickException("not implemented")


@main.command()
@click.argument("query", nargs=-1)
@click.option("--limit", type=int, default=None, help="Truncate results to N notes.")
def notes(query: tuple[str, ...], limit: int | None) -> None:
    """Query notes with Anki search syntax; emit JSON array."""
    raise click.ClickException("not implemented")


@main.command()
@click.argument("note_id", type=int)
def note(note_id: int) -> None:
    """Get a single note by ID; emit JSON object."""
    raise click.ClickException("not implemented")


@main.command()
@click.argument("query", nargs=-1)
@click.option("--limit", type=int, default=None, help="Truncate results to N cards.")
def cards(query: tuple[str, ...], limit: int | None) -> None:
    """Query cards with Anki search syntax; emit JSON array."""
    raise click.ClickException("not implemented")


@main.command()
@click.argument("card_id", type=int)
def card(card_id: int) -> None:
    """Get a single card by ID (includes scheduling state); emit JSON object."""
    raise click.ClickException("not implemented")
