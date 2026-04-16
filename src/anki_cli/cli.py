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
@click.option("--pull", "mode", flag_value="pull", help="Only download remote → local.")
@click.option("--push", "mode", flag_value="push", help="Only upload local → remote.")
def sync(mode: str | None) -> None:
    """Synchronize with AnkiWeb (default: pull + push)."""
    raise click.ClickException("not implemented")


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
