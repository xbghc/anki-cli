"""Business logic shared between the CLI and the MCP server.

Each function takes native Python args, returns native Python data
structures (dict / list), and raises OpsError for user-facing failures.
Neither Click nor MCP serialization should leak in.
"""

from __future__ import annotations

from typing import Any

from anki_cli import config
from anki_cli._collection import open_collection
from anki_cli._pylib import run_off_main
from anki_cli._serialize import card_to_dict, note_to_dict
from anki_cli.paths import collection_path, config_path, data_dir


class OpsError(Exception):
    """Raised when an operation cannot complete for a user-facing reason."""


def do_login(username: str, password: str, endpoint: str | None = None) -> dict[str, Any]:
    from anki._backend import RustBackend
    from anki.errors import SyncError
    from anki.sync_pb2 import SyncLoginRequest

    backend = RustBackend()
    try:
        auth = run_off_main(
            backend.sync_login,
            SyncLoginRequest(username=username, password=password, endpoint=endpoint),
        )
    except SyncError as err:
        raise OpsError(f"login failed: {err}") from err

    cfg = config.SyncConfig(
        username=username,
        hostkey=auth.hkey,
        endpoint=auth.endpoint or "",
    )
    config.save(cfg)
    return {
        "status": "ok",
        "username": username,
        "endpoint": cfg.endpoint or "ankiweb",
        "config_path": str(config_path()),
    }


def do_sync() -> dict[str, Any]:
    from anki.collection import Collection
    from anki.errors import SyncError
    from anki.sync import SyncAuth
    from anki.sync_pb2 import SyncCollectionResponse

    cfg = config.load()
    if cfg is None:
        raise OpsError("not logged in; run `anki login` first")

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
            raise OpsError(f"sync failed: {err}") from err

        if result.new_endpoint:
            cfg.endpoint = result.new_endpoint
            config.save(cfg)
            auth = SyncAuth(
                hkey=cfg.hostkey,
                endpoint=result.new_endpoint,
                io_timeout_secs=30,
            )

        required = result.required
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
                raise OpsError(f"full download failed: {err}") from err
            action = "full_download"
        elif required == SyncCollectionResponse.FULL_UPLOAD:
            raise OpsError(
                "FULL_UPLOAD required — remote collection is empty. "
                "Refusing automatic upload; resolve manually if intended."
            )
        else:
            raise OpsError(
                "FULL_SYNC required — local and remote have diverged. "
                "Resolve manually (choose upload or download) before retrying."
            )
    finally:
        col.close()

    return {
        "status": "ok",
        "action": action,
        "server_message": result.server_message,
    }


def do_decks() -> list[dict[str, Any]]:
    with open_collection() as col:
        return [
            {"id": int(d.id), "name": d.name}
            for d in col.decks.all_names_and_ids()
        ]


def do_notetypes() -> list[dict[str, Any]]:
    with open_collection() as col:
        out = []
        for nt in col.models.all_names_and_ids():
            model = col.models.get(nt.id)
            fields = [f["name"] for f in model["flds"]] if model else []
            out.append({"id": int(nt.id), "name": nt.name, "fields": fields})
        return out


def do_notes(query: str, limit: int | None = None) -> list[dict[str, Any]]:
    from anki.errors import SearchError

    with open_collection() as col:
        try:
            nids = col.find_notes(query)
        except SearchError as err:
            raise OpsError(f"invalid query: {err}") from err
        if limit is not None:
            nids = nids[:limit]
        return [note_to_dict(col, col.get_note(nid)) for nid in nids]


def do_note(note_id: int) -> dict[str, Any]:
    from anki.errors import NotFoundError

    with open_collection() as col:
        try:
            n = col.get_note(note_id)
        except NotFoundError as err:
            raise OpsError(f"note {note_id} not found") from err
        return note_to_dict(col, n)


def do_cards(query: str, limit: int | None = None) -> list[dict[str, Any]]:
    from anki.errors import SearchError

    with open_collection() as col:
        try:
            cids = col.find_cards(query)
        except SearchError as err:
            raise OpsError(f"invalid query: {err}") from err
        if limit is not None:
            cids = cids[:limit]
        return [card_to_dict(col.get_card(cid)) for cid in cids]


def do_card(card_id: int) -> dict[str, Any]:
    from anki.errors import NotFoundError

    with open_collection() as col:
        try:
            c = col.get_card(card_id)
        except NotFoundError as err:
            raise OpsError(f"card {card_id} not found") from err
        return card_to_dict(c)


def do_add_note(
    deck: str,
    notetype: str,
    fields: dict[str, str],
    tags: list[str] | None = None,
) -> dict[str, Any]:
    with open_collection() as col:
        nt = col.models.by_name(notetype)
        if not nt:
            raise OpsError(f"notetype not found: {notetype}")
        deck_id = col.decks.id_for_name(deck)
        if not deck_id:
            raise OpsError(f"deck not found: {deck}")

        note = col.new_note(nt)
        valid = {f["name"] for f in nt["flds"]}
        for name, val in fields.items():
            if name not in valid:
                raise OpsError(f"notetype '{notetype}' has no field '{name}'")
            note[name] = val
        if tags:
            note.tags = list(tags)

        run_off_main(col.add_note, note, deck_id)
        return note_to_dict(col, col.get_note(note.id))


def do_update_note(
    note_id: int,
    fields: dict[str, str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    from anki.errors import NotFoundError

    with open_collection() as col:
        try:
            n = col.get_note(note_id)
        except NotFoundError as err:
            raise OpsError(f"note {note_id} not found") from err

        if fields:
            nt = col.models.get(n.mid)
            valid = {f["name"] for f in nt["flds"]} if nt else set()
            for name, val in fields.items():
                if valid and name not in valid:
                    raise OpsError(f"note has no field '{name}'")
                n[name] = val
        if tags is not None:
            n.tags = list(tags)

        run_off_main(col.update_note, n)
        return note_to_dict(col, col.get_note(note_id))


def do_delete_note(note_id: int) -> dict[str, Any]:
    with open_collection() as col:
        result = run_off_main(col.remove_notes, [note_id])
    return {"status": "deleted", "id": note_id, "count": int(result.count)}


def do_rename_deck(old_name: str, new_name: str) -> dict[str, Any]:
    if not old_name or not old_name.strip():
        raise OpsError("old_name is required")
    if not new_name or not new_name.strip():
        raise OpsError("new_name is required")
    old_name = old_name.strip()
    new_name = new_name.strip()

    with open_collection() as col:
        deck_id = col.decks.id_for_name(old_name)
        if not deck_id:
            raise OpsError(f"deck not found: {old_name}")
        existing = col.decks.id_for_name(new_name)
        if existing and int(existing) != int(deck_id):
            raise OpsError(f"a different deck named '{new_name}' already exists")
        run_off_main(col.decks.rename, int(deck_id), new_name)

    return {
        "status": "ok",
        "deck_id": int(deck_id),
        "old_name": old_name,
        "new_name": new_name,
    }


def do_answer_card(card_id: int, rating: str) -> dict[str, Any]:
    from anki.errors import NotFoundError
    from anki.scheduler_pb2 import CardAnswer

    rating_map = {
        "again": CardAnswer.AGAIN,
        "hard": CardAnswer.HARD,
        "good": CardAnswer.GOOD,
        "easy": CardAnswer.EASY,
    }
    key = rating.lower()
    if key not in rating_map:
        raise OpsError(f"invalid rating: {rating} (expected again/hard/good/easy)")
    rating_value = rating_map[key]

    with open_collection() as col:
        try:
            c = col.get_card(card_id)
        except NotFoundError as err:
            raise OpsError(f"card {card_id} not found") from err

        c.start_timer()
        states = run_off_main(col._backend.get_scheduling_states, card_id)
        answer = col.sched.build_answer(card=c, states=states, rating=rating_value)
        run_off_main(col.sched.answer_card, answer)

        updated = col.get_card(card_id)
        return {"status": "ok", "rating": key, "card": card_to_dict(updated)}
