"""MCP server wrapping anki-cli — exposes Anki operations as MCP tools.

Intended for agents that cannot shell out (e.g. sandboxed or pure-tool
runtimes): instead of invoking the `anki` CLI, the agent calls MCP tools
that reuse the same underlying pylib calls in-process.

Run via `anki-mcp` (installed as a console script) or `python -m anki_cli.mcp_server`.
Communicates over stdio, suitable for MCP hosts like Claude Desktop,
claude-code MCP servers, or chat-assistant's `~/.chat-assistant/config/mcp.json`.

Intentionally does NOT expose `login` as an MCP tool: logging in is a
one-time setup action, not something an agent should trigger on its own.
Run `anki login` from the CLI during deployment instead.

All tools return a single JSON string so every MCP client sees one clean
text block regardless of how it flattens multi-part content (FastMCP's
default list→multiple-text-blocks behavior confuses clients that naively
concatenate blocks).
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from anki_cli import ops

mcp = FastMCP("anki")


def _emit(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def sync() -> str:
    """Synchronize the local Anki collection with AnkiWeb (bidirectional incremental).

    The server never syncs implicitly. Call `sync` once before a block of
    read/write work (to pull the user's latest edits from phone/desktop),
    and once after (to push your changes back).
    """
    return _emit(ops.do_sync())


@mcp.tool()
def decks() -> str:
    """List all decks as a JSON array of {id, name}."""
    return _emit(ops.do_decks())


@mcp.tool()
def notetypes() -> str:
    """List all notetypes with their field names: [{id, name, fields}]."""
    return _emit(ops.do_notetypes())


@mcp.tool()
def notes(query: str, limit: int | None = None) -> str:
    """Search notes with Anki query syntax.

    Query examples: 'deck:Japanese tag:verb', 'is:due', 'added:7',
    'front:*python*', '-tag:suspended'. Returns note objects with fields
    exposed as a name→value dict keyed by the notetype's field order.
    """
    return _emit(ops.do_notes(query, limit))


@mcp.tool()
def note(note_id: int) -> str:
    """Get a single note by ID."""
    return _emit(ops.do_note(note_id))


@mcp.tool()
def cards(query: str, limit: int | None = None) -> str:
    """Search cards with Anki query syntax. Returns full scheduling state.

    Each card object includes: queue (new/learning/review/...),
    type, due, interval_days, ease_factor, reps, lapses. Use this when
    you care about card-level scheduling rather than note content.
    """
    return _emit(ops.do_cards(query, limit))


@mcp.tool()
def card(card_id: int) -> str:
    """Get a single card by ID, including its full scheduling state."""
    return _emit(ops.do_card(card_id))


@mcp.tool()
def add_note(
    deck: str,
    notetype: str,
    fields: dict[str, str],
    tags: list[str] | None = None,
) -> str:
    """Create a new note in an existing deck.

    The deck and notetype MUST already exist — look them up via the
    `decks` and `notetypes` tools first if unsure. `fields` keys must
    match the notetype's field names exactly (case-sensitive); mismatched
    keys raise an error rather than silently dropping content.

    Writes affect the local collection only; call `sync` afterward to
    push them to AnkiWeb.
    """
    return _emit(ops.do_add_note(deck, notetype, fields, tags))


@mcp.tool()
def update_note(
    note_id: int,
    fields: dict[str, str] | None = None,
    tags: list[str] | None = None,
) -> str:
    """Update an existing note's fields and/or tags.

    `fields` merges into the existing note — omitted fields keep their
    current values (partial update). `tags`, if provided, fully replaces
    the existing tag list; pass the current tags plus your additions to
    append rather than replace.
    """
    return _emit(ops.do_update_note(note_id, fields, tags))


@mcp.tool()
def delete_note(note_id: int) -> str:
    """Delete a note and all its generated cards by ID."""
    return _emit(ops.do_delete_note(note_id))


@mcp.tool()
def answer_card(card_id: int, rating: str) -> str:
    """Rate a card to advance its SRS schedule.

    `rating` must be one of: 'again', 'hard', 'good', 'easy'. The rating
    feeds Anki's FSRS / SM-2 scheduler and advances the card's next due
    date. **Not cleanly reversible** — use this only when you're
    explicitly recording a real review outcome the user asked you to
    log, not as part of a speculative workflow.
    """
    return _emit(ops.do_answer_card(card_id, rating))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
