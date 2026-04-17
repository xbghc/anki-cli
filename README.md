# anki-cli

Headless Anki sync client with JSON I/O — log in to AnkiWeb, sync, query decks/notetypes/notes/cards, all without the Anki GUI. Designed for agents and servers where the Anki desktop app cannot run.

## Install

```bash
uv tool install git+https://github.com/xbghc/anki-cli
```

## Quickstart

```bash
# Store AnkiWeb credentials (prompts for password if omitted)
anki login -u you@example.com

# Pull your collection locally (first sync does a full download)
anki sync

# List decks
anki decks

# Search notes with Anki query syntax
anki notes "deck:Japanese tag:verb" --limit 20

# Inspect one card's scheduling state
anki card 1234567890

# Add a note (reads JSON from stdin)
echo '{"deck":"Japanese","notetype":"Basic","fields":{"Front":"食べる","Back":"to eat"},"tags":["verb"]}' \
  | anki add-note

# Rate a card and advance its SRS schedule
anki answer-card 1234567890 good
```

## Commands

**Read-only:**

| Command | Purpose |
|---------|---------|
| `anki login` | Exchange AnkiWeb email + password for a hostkey, save to `~/.config/anki-cli/config.json`. |
| `anki sync` | Bidirectional incremental sync with AnkiWeb. Refuses `FULL_UPLOAD` / `FULL_SYNC` to prevent accidental overwrites. |
| `anki decks` | JSON array of `{id, name}` per deck. |
| `anki notetypes` | JSON array of `{id, name, fields[]}` per notetype. |
| `anki notes QUERY` | Search notes; JSON array of note objects (fields as name→value dict). |
| `anki note NOTE_ID` | Single note by ID. |
| `anki cards QUERY` | Search cards; JSON array with scheduling state. |
| `anki card CARD_ID` | Single card by ID. |

**Write:**

| Command | Input | Purpose |
|---------|-------|---------|
| `anki add-note` | stdin JSON `{deck, notetype, fields, tags?}` | Create a new note. |
| `anki update-note NOTE_ID` | stdin JSON `{fields?, tags?}` | Merge field values into existing note; tags are replaced wholesale. |
| `anki delete-note NOTE_ID` | — | Remove the note and its cards. |
| `anki answer-card CARD_ID {again\|hard\|good\|easy}` | — | Rate a card; FSRS / SM-2 scheduler advances its state. |

Queries use [Anki's search syntax](https://docs.ankiweb.net/searching.html): `deck:...`, `tag:...`, `is:due`, `added:7`, `-tag:suspended`, etc.

Write operations modify the local collection only. Run `anki sync` to push them to AnkiWeb.

## Design

- **Not for interactive use** — all output is JSON on stdout, errors on stderr. Pair with `jq` for shell scripts, or call from an agent.
- **Based on official Anki pylib** (`anki` package) — schema migrations, sync protocol, and the FSRS scheduler are delegated to upstream. No direct SQLite manipulation.
- **Headless** — no Qt, no `aqt`. Runs on servers that cannot install the Anki desktop app.
- **Explicit sync** — `sync` is never implicit. Agents manage their own cadence (typically once per session start, once before exit).

## Status

Phase 1 (login, sync, queries) and Phase 2 (note CRUD + `answer-card`) complete.

## License

MIT
