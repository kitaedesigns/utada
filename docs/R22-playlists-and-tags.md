# R22: Playlists and tags (added 2026-11-19)

| # | Requirement | Priority |
|---|---|---|
| R22 | A playlist system with tags. One file can be in any number of playlists and carry any number of tags. Playlists can be hand-built (ordered) or built automatically from tags. | Must |

Status: **specified, not built.** Phase 1 is still at the decision gate, so no feature code yet. Slots into Phase 2 after 2.8 (settings) and 2.13 (queues), because it reuses both.

## Interpretation (tags on files confirmed by you 2026-11-19)
"Playlist with tags, so one video can be in multiple playlists" is read as:
- **Tags** are labels you put on files (for example `keynote`, `2025`, `Q&A`, `best-of`). A file can have many tags.
- **Playlists** are named collections. A file can be in many playlists. Two kinds:
  - **Manual playlist:** you add files and drag to reorder. The same file can appear in several playlists at different positions. Removing a file from one playlist leaves it in the others.
  - **Smart playlist:** a saved tag rule, for example `keynote AND 2025`, `keynote OR panel`, `best-of NOT draft`. Its contents update automatically as you tag files.
- Playlists can also carry tags of their own (for example tag playlists `client-A`), so the playlist list can be filtered. Low priority.

## Data model
Stored in one local SQLite file, `%APPDATA%\<AppName>\library.db` (no network, backed up before schema upgrades).

| Table | Fields |
|---|---|
| `media` | id, path, size, modified time, content fingerprint (hash of first and last 1 MB + size), last seen |
| `tag` | id, name (unique, case-insensitive), optional color |
| `media_tag` | media_id, tag_id (many-to-many) |
| `playlist` | id, name, kind (manual / smart), smart rule, sort order, created, modified |
| `playlist_item` | playlist_id, media_id, position (many-to-many, ordered; duplicates within one playlist off by default) |

**Files that move.** Moves done by the app (R13 Send to folder, R12 delete) update `media.path` in the same step, so playlists and tags follow the file and undo restores both. Files moved or renamed outside the app are found again by fingerprint the next time their folder is scanned. Files that cannot be found show as "missing" entries in playlists (never silently dropped), with Locate... and Remove actions.

## Interface
- **Library sidebar:** new **Playlists** and **Tags** sections in the folder tree, above the folders. Clicking one shows its files in the existing Grid/List pane with the same sorting, filters and thumbnails. A manual playlist adds a "Playlist order" sort and drag-to-reorder.
- **Tagging:** a Tags field in the Details panel (type to add, with autocomplete; x to remove); "Tags..." in the tile and sidebar context menus; works on multi-selection; hotkey `T` opens the tag field for the current file (bare `T` is unused in the hotkey table; always-on-top stays on `Ctrl+T`).
- **Adding to playlists:** "Add to playlist" submenu in tile and sidebar context menus (lists playlists plus "New playlist..."); drag files from the sidebar or a tile onto a playlist in the sidebar; hotkey `Ctrl+P` opens a quick playlist picker for the current or selected files.
- **Membership is visible:** the Details panel lists the file's playlists and tags; a List-view column "Tags".
- **Playing:** "Play playlist in a tile" (one tile, queue = playlist, works with Loop/Next from 2.13) and "Open playlist on the wall" (one tile per file, respecting the tile limit from Phase 3).
- **Tag filter in the sidebar:** pill filters by tag, combinable with the type filter and search.
- **Manage:** rename, recolor, merge and delete tags (delete asks if the tag is in use and says how many files); rename, duplicate, delete playlists (deleting a playlist never deletes files). All undoable with `Ctrl+Z`.
- **Import/export:** export a playlist as `.m3u` (paths only) or as the app's `.json` (paths + tags); import both. This replaces the separate "Save playlist / Open playlist" in 2.8 so there is one playlist concept, not two.

## Acceptance
1. Tag one file `keynote` and `2025`; add it to playlists A and B. It shows in both, and in the smart playlist `keynote AND 2025`. Removing it from A leaves it in B and keeps its tags.
2. A manual playlist of 10 files keeps its order across restarts; drag-reorder persists.
3. Move the file with Send to folder (`Ctrl+1`): it stays in both playlists with its tags, at the new path. `Ctrl+Z` moves it back and the playlists follow.
4. Rename the file in Explorer, rescan: it is matched by fingerprint and stays in its playlists. Delete it in Explorer: it shows as missing, not removed.
5. Smart playlist updates within one second of adding or removing a tag.
6. Tag 50 selected files in one action; one `Ctrl+Z` undoes it.
7. A library with 20,000 files, 200 tags and 100 playlists opens a playlist or tag view in under 300 ms (target; report the measured number).
8. Export a playlist to `.m3u` and `.json`, delete it, import it back: same files, same order, same tags (json).
9. A corrupt `library.db` is backed up and replaced, with a clear message; the app still starts.

## Effect on the candidate choice
Neither candidate has tags or many-to-many playlists. MosaicPlayer has single playlist files (`.gpls`, `.m3u`) that save layout and positions; that format can be kept as an import option. The database layer is new work in either base (Python ships `sqlite3`; Rust would add the `rusqlite` crate). Size estimate: **medium-large**, mostly interface work in the sidebar and context menus. This addition does not change my recommendation.
