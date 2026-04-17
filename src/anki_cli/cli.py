"""CLI entry point — thin wrapper around anki_cli.ops."""

from __future__ import annotations

import json
import os
import sys

import click

from anki_cli import __version__, ops


def _emit(data: object) -> None:
    click.echo(json.dumps(data, indent=2, ensure_ascii=False))


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ops.OpsError as err:
        raise click.ClickException(str(err)) from err


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
    """Log into AnkiWeb and save sync credentials locally.

    Credentials resolve in this order: CLI flag → env var (ANKIWEB_USERNAME /
    ANKIWEB_PASSWORD) → interactive prompt. Agents running headlessly should
    set the env vars in .env and omit the flags.
    """
    if not username:
        username = os.environ.get("ANKIWEB_USERNAME")
    if not password:
        password = os.environ.get("ANKIWEB_PASSWORD")
    if not username:
        username = click.prompt("Username (email)", type=str)
    if not password:
        password = click.prompt("Password", type=str, hide_input=True)

    _emit(_guard(ops.do_login, username, password, endpoint))


@main.command()
def sync() -> None:
    """Synchronize the local collection with AnkiWeb (bidirectional incremental)."""
    _emit(_guard(ops.do_sync))


@main.command()
def decks() -> None:
    """List all decks as JSON."""
    _emit(_guard(ops.do_decks))


@main.command()
def notetypes() -> None:
    """List all note types as JSON, including each type's field names."""
    _emit(_guard(ops.do_notetypes))


@main.command()
@click.argument("query", nargs=-1)
@click.option("--limit", type=int, default=None, help="Truncate results to N notes.")
def notes(query: tuple[str, ...], limit: int | None) -> None:
    """Query notes with Anki search syntax; emit JSON array."""
    _emit(_guard(ops.do_notes, " ".join(query), limit))


@main.command()
@click.argument("note_id", type=int)
def note(note_id: int) -> None:
    """Get a single note by ID; emit JSON object."""
    _emit(_guard(ops.do_note, note_id))


@main.command()
@click.argument("query", nargs=-1)
@click.option("--limit", type=int, default=None, help="Truncate results to N cards.")
def cards(query: tuple[str, ...], limit: int | None) -> None:
    """Query cards with Anki search syntax; emit JSON array."""
    _emit(_guard(ops.do_cards, " ".join(query), limit))


@main.command()
@click.argument("card_id", type=int)
def card(card_id: int) -> None:
    """Get a single card by ID (includes scheduling state); emit JSON object."""
    _emit(_guard(ops.do_card, card_id))


@main.command("add-note")
def add_note() -> None:
    """Create a new note. Reads JSON from stdin: {deck, notetype, fields, tags?}."""
    try:
        spec = json.loads(sys.stdin.read())
    except json.JSONDecodeError as err:
        raise click.ClickException(f"invalid JSON on stdin: {err}") from err

    deck = spec.get("deck")
    notetype = spec.get("notetype")
    if not deck or not notetype:
        raise click.ClickException("required fields: deck, notetype")
    fields = spec.get("fields") or {}
    if not isinstance(fields, dict):
        raise click.ClickException("fields must be an object (field_name -> value)")

    _emit(_guard(ops.do_add_note, deck, notetype, fields, spec.get("tags") or []))


@main.command("update-note")
@click.argument("note_id", type=int)
def update_note(note_id: int) -> None:
    """Update an existing note. Reads JSON from stdin: {fields?, tags?}.

    `fields` merges into the existing note (omitted fields keep their values).
    `tags` fully replaces the existing tag list.
    """
    try:
        patch = json.loads(sys.stdin.read())
    except json.JSONDecodeError as err:
        raise click.ClickException(f"invalid JSON on stdin: {err}") from err

    fields = patch.get("fields")
    if fields is not None and not isinstance(fields, dict):
        raise click.ClickException("fields must be an object")
    tags = patch.get("tags") if "tags" in patch else None

    _emit(_guard(ops.do_update_note, note_id, fields, tags))


@main.command("delete-note")
@click.argument("note_id", type=int)
def delete_note(note_id: int) -> None:
    """Delete a note (and all its cards) by ID."""
    _emit(_guard(ops.do_delete_note, note_id))


@main.command("rename-deck")
@click.argument("old_name")
@click.argument("new_name")
def rename_deck(old_name: str, new_name: str) -> None:
    """Rename a deck. Children (Prefix::Child) are updated automatically."""
    _emit(_guard(ops.do_rename_deck, old_name, new_name))


@main.command("answer-card")
@click.argument("card_id", type=int)
@click.argument(
    "rating",
    type=click.Choice(["again", "hard", "good", "easy"], case_sensitive=False),
)
def answer_card(card_id: int, rating: str) -> None:
    """Rate a card and advance its SRS schedule (FSRS / SM-2)."""
    _emit(_guard(ops.do_answer_card, card_id, rating))
