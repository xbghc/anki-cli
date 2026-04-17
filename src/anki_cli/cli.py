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
    """Log into AnkiWeb and save sync credentials locally.

    Credentials resolve in this order: CLI flag → env var (ANKIWEB_USERNAME /
    ANKIWEB_PASSWORD) → interactive prompt. Agents running headlessly should
    set the env vars in .env and omit the flags.
    """
    import os

    from anki._backend import RustBackend
    from anki.errors import SyncError
    from anki.sync_pb2 import SyncLoginRequest

    if not username:
        username = os.environ.get("ANKIWEB_USERNAME")
    if not password:
        password = os.environ.get("ANKIWEB_PASSWORD")
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
    from anki_cli._collection import open_collection

    with open_collection() as col:
        items = col.decks.all_names_and_ids()
        payload = [{"id": int(d.id), "name": d.name} for d in items]

    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@main.command()
def notetypes() -> None:
    """List all note types as JSON, including each type's field names."""
    from anki_cli._collection import open_collection

    with open_collection() as col:
        payload = []
        for nt in col.models.all_names_and_ids():
            model = col.models.get(nt.id)
            fields = [f["name"] for f in model["flds"]] if model else []
            payload.append({"id": int(nt.id), "name": nt.name, "fields": fields})

    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@main.command()
@click.argument("query", nargs=-1)
@click.option("--limit", type=int, default=None, help="Truncate results to N notes.")
def notes(query: tuple[str, ...], limit: int | None) -> None:
    """Query notes with Anki search syntax; emit JSON array."""
    from anki.errors import SearchError

    from anki_cli._collection import open_collection
    from anki_cli._serialize import note_to_dict

    search = " ".join(query)
    with open_collection() as col:
        try:
            nids = col.find_notes(search)
        except SearchError as err:
            raise click.ClickException(f"invalid query: {err}") from err
        if limit is not None:
            nids = nids[:limit]
        payload = [note_to_dict(col, col.get_note(nid)) for nid in nids]

    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@main.command()
@click.argument("note_id", type=int)
def note(note_id: int) -> None:
    """Get a single note by ID; emit JSON object."""
    from anki.errors import NotFoundError

    from anki_cli._collection import open_collection
    from anki_cli._serialize import note_to_dict

    with open_collection() as col:
        try:
            n = col.get_note(note_id)
        except NotFoundError as err:
            raise click.ClickException(f"note {note_id} not found") from err
        payload = note_to_dict(col, n)

    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@main.command()
@click.argument("query", nargs=-1)
@click.option("--limit", type=int, default=None, help="Truncate results to N cards.")
def cards(query: tuple[str, ...], limit: int | None) -> None:
    """Query cards with Anki search syntax; emit JSON array."""
    from anki.errors import SearchError

    from anki_cli._collection import open_collection
    from anki_cli._serialize import card_to_dict

    search = " ".join(query)
    with open_collection() as col:
        try:
            cids = col.find_cards(search)
        except SearchError as err:
            raise click.ClickException(f"invalid query: {err}") from err
        if limit is not None:
            cids = cids[:limit]
        payload = [card_to_dict(col.get_card(cid)) for cid in cids]

    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@main.command()
@click.argument("card_id", type=int)
def card(card_id: int) -> None:
    """Get a single card by ID (includes scheduling state); emit JSON object."""
    from anki.errors import NotFoundError

    from anki_cli._collection import open_collection
    from anki_cli._serialize import card_to_dict

    with open_collection() as col:
        try:
            c = col.get_card(card_id)
        except NotFoundError as err:
            raise click.ClickException(f"card {card_id} not found") from err
        payload = card_to_dict(c)

    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@main.command("add-note")
def add_note() -> None:
    """Create a new note. Reads JSON from stdin: {deck, notetype, fields, tags?}."""
    import sys

    from anki_cli._collection import open_collection
    from anki_cli._pylib import run_off_main
    from anki_cli._serialize import note_to_dict

    try:
        spec = json.loads(sys.stdin.read())
    except json.JSONDecodeError as err:
        raise click.ClickException(f"invalid JSON on stdin: {err}") from err

    deck_name = spec.get("deck")
    notetype_name = spec.get("notetype")
    fields = spec.get("fields") or {}
    tags = spec.get("tags") or []

    if not deck_name or not notetype_name:
        raise click.ClickException("required fields: deck, notetype")
    if not isinstance(fields, dict):
        raise click.ClickException("fields must be an object (field_name -> value)")

    with open_collection() as col:
        notetype = col.models.by_name(notetype_name)
        if not notetype:
            raise click.ClickException(f"notetype not found: {notetype_name}")
        deck_id = col.decks.id_for_name(deck_name)
        if not deck_id:
            raise click.ClickException(f"deck not found: {deck_name}")

        note = col.new_note(notetype)
        valid_fields = {f["name"] for f in notetype["flds"]}
        for name, val in fields.items():
            if name not in valid_fields:
                raise click.ClickException(
                    f"notetype '{notetype_name}' has no field '{name}'"
                )
            note[name] = val
        if tags:
            note.tags = list(tags)

        run_off_main(col.add_note, note, deck_id)
        payload = note_to_dict(col, col.get_note(note.id))

    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@main.command("update-note")
@click.argument("note_id", type=int)
def update_note(note_id: int) -> None:
    """Update an existing note. Reads JSON from stdin: {fields?, tags?}.

    `fields` merges into the existing note (omitted fields keep their values).
    `tags` fully replaces the existing tag list.
    """
    import sys

    from anki.errors import NotFoundError

    from anki_cli._collection import open_collection
    from anki_cli._pylib import run_off_main
    from anki_cli._serialize import note_to_dict

    try:
        patch = json.loads(sys.stdin.read())
    except json.JSONDecodeError as err:
        raise click.ClickException(f"invalid JSON on stdin: {err}") from err

    with open_collection() as col:
        try:
            n = col.get_note(note_id)
        except NotFoundError as err:
            raise click.ClickException(f"note {note_id} not found") from err

        if "fields" in patch:
            if not isinstance(patch["fields"], dict):
                raise click.ClickException("fields must be an object")
            notetype = col.models.get(n.mid)
            valid = {f["name"] for f in notetype["flds"]} if notetype else set()
            for name, val in patch["fields"].items():
                if valid and name not in valid:
                    raise click.ClickException(f"note has no field '{name}'")
                n[name] = val
        if "tags" in patch:
            n.tags = list(patch["tags"])

        run_off_main(col.update_note, n)
        payload = note_to_dict(col, col.get_note(note_id))

    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@main.command("delete-note")
@click.argument("note_id", type=int)
def delete_note(note_id: int) -> None:
    """Delete a note (and all its cards) by ID."""
    from anki_cli._collection import open_collection
    from anki_cli._pylib import run_off_main

    with open_collection() as col:
        result = run_off_main(col.remove_notes, [note_id])

    click.echo(
        json.dumps(
            {"status": "deleted", "id": note_id, "count": int(result.count)},
            indent=2,
        )
    )


@main.command("answer-card")
@click.argument("card_id", type=int)
@click.argument(
    "rating",
    type=click.Choice(["again", "hard", "good", "easy"], case_sensitive=False),
)
def answer_card(card_id: int, rating: str) -> None:
    """Rate a card and advance its SRS schedule (FSRS / SM-2)."""
    from anki.errors import NotFoundError
    from anki.scheduler_pb2 import CardAnswer

    from anki_cli._collection import open_collection
    from anki_cli._pylib import run_off_main
    from anki_cli._serialize import card_to_dict

    rating_map = {
        "again": CardAnswer.AGAIN,
        "hard": CardAnswer.HARD,
        "good": CardAnswer.GOOD,
        "easy": CardAnswer.EASY,
    }
    rating_value = rating_map[rating.lower()]

    with open_collection() as col:
        try:
            c = col.get_card(card_id)
        except NotFoundError as err:
            raise click.ClickException(f"card {card_id} not found") from err

        c.start_timer()
        states = run_off_main(col._backend.get_scheduling_states, card_id)
        answer = col.sched.build_answer(card=c, states=states, rating=rating_value)
        run_off_main(col.sched.answer_card, answer)

        updated = col.get_card(card_id)
        payload = card_to_dict(updated)

    click.echo(
        json.dumps(
            {"status": "ok", "rating": rating.lower(), "card": payload},
            indent=2,
            ensure_ascii=False,
        )
    )
