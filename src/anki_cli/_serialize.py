"""JSON-friendly projections for Anki collection objects."""

from __future__ import annotations

from typing import Any

from anki.cards import Card
from anki.collection import Collection
from anki.notes import Note

_QUEUE_NAMES = {
    -3: "manually_buried",
    -2: "sibling_buried",
    -1: "suspended",
    0: "new",
    1: "learning",
    2: "review",
    3: "day_learn_relearn",
    4: "preview",
}

_CARD_TYPE_NAMES = {
    0: "new",
    1: "learning",
    2: "review",
    3: "relearning",
}


def note_to_dict(col: Collection, note: Note) -> dict[str, Any]:
    notetype = col.models.get(note.mid)
    if notetype:
        field_names = [f["name"] for f in notetype["flds"]]
        fields = dict(zip(field_names, note.fields, strict=False))
        notetype_payload = {"id": int(note.mid), "name": notetype["name"]}
    else:
        fields = {str(i): v for i, v in enumerate(note.fields)}
        notetype_payload = {"id": int(note.mid), "name": None}

    return {
        "id": int(note.id),
        "notetype": notetype_payload,
        "tags": list(note.tags),
        "fields": fields,
        "cards": [int(cid) for cid in note.card_ids()],
        "modified": int(note.mod),
    }


def card_to_dict(card: Card) -> dict[str, Any]:
    queue = int(card.queue)
    ctype = int(card.type)
    return {
        "id": int(card.id),
        "note_id": int(card.nid),
        "deck_id": int(card.did),
        "ord": int(card.ord),
        "queue": _QUEUE_NAMES.get(queue, str(queue)),
        "type": _CARD_TYPE_NAMES.get(ctype, str(ctype)),
        "due": int(card.due),
        "interval_days": int(card.ivl),
        "ease_factor": int(card.factor),
        "reps": int(card.reps),
        "lapses": int(card.lapses),
        "modified": int(card.mod),
    }
