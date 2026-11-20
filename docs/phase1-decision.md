# Phase 1.5 decision report

Date: 2026-11-20. Measured on your PC (RTX 5070 Ti, driver 610.88, Windows 10). The numbers behind every statement are in `PROGRESS.md`; raw results are in `docs/phase1-results/`.

## Recommendation
**Build on MosaicPlayer** (github.com/itsui/mosaicplayer @ `004dd93`, GPL-3.0-or-later). This changes the plan's original pick, MultipleVideoPlayer, which becomes the fallback.

## Proceed rule: both pass
| | MultipleVideoPlayer | MosaicPlayer |
|---|---|---|
| Hardware HEVC decode | `nvdec`, zero-copy | `d3d11va-copy` |
| 6 × 1080p60 HEVC (your new maximum) | 0 dropped frames | 0 dropped frames |
| 6 × 4K30 HEVC | 0 dropped frames | 0 dropped frames |
| 9 / 12 tiles (headroom only) | 3 / up to 13 per tile | 8 / 4 |

Playback performance does not decide this. Both are smooth at 6 tiles with large margins.

## Why MosaicPlayer
1. **The things this app is about already work.** Drag and drop adds files, multiple files and folders (you tested it). GIFs animate and loop with correct timing. Still images and HEIC display (only its drop filter needs the image extensions added). Corrupt files get a "cannot play this file" tile. Looping is seamless, and Next in folder exists.
2. **Removing a tile frees its memory.** Measured: 3 removals freed 342 MB of RAM and 387 MB of GPU memory. MultipleVideoPlayer freed 82 MB and no GPU memory, because it keeps every removed player alive.
3. **Lighter per tile:** 1.4 GB RAM / 1.0 GB GPU memory for 6 × 1080p60 HEVC, against 3.9 / 3.0 GB.
4. **Qt fits the work ahead.** The library sidebar, list view, tag editor, context menus and R22's playlists map onto standard Qt widgets and models, and Python ships `sqlite3` for `library.db`. MultipleVideoPlayer's egui needs most of that built by hand.
5. **More mature:** 60 commits, a test suite, an English interface, settings, help and playlist files. MultipleVideoPlayer's Rust version is two weeks old (7 commits), its interface is mostly Traditional Chinese, and its build script fails on Windows 10.

## What MultipleVideoPlayer does better (and what that costs us)
| | MultipleVideoPlayer | MosaicPlayer | Plan in Phase 2 |
|---|---|---|---|
| Switching a tile to another file | 29 ms | **359 ms** median | Part of this is MosaicPlayer's policy moving a tile between CPU and GPU decoding after it loads. With the 6-tile cap, always decode on the GPU, then re-measure. Target: under 150 ms. |
| Startup to first frame | 1.9 s | **4.5 s** from source; about 7.5 s on the first launch of the packaged build | Lazy imports and a quick window first; measure the packaged build. |
| CPU at 6 × 1080p60 HEVC | 0.7 cores | 1.9 cores | Acceptable on a 24-core CPU; mostly the copy back and CPU-decoded small clips. |
| Decode path | zero-copy `nvdec` | copy back (`d3d11va-copy`); its zero-copy option silently falls back to CPU on Windows | Keep copy back (it fits easily at 6 tiles), or try its `nvdec` setting later. Fix or hide the broken zero-copy option. |

## Problems found in MultipleVideoPlayer (for the record)
- Drops land in the last-hovered cell, not the cell under the cursor (`app.rs:1664`). You could only fill the left column.
- Refuses GIFs, still images, HEIC, AVIF and WebP (extension filter; its engine decodes them all).
- No looping or auto-advance: it stops on the last frame.
- A corrupt file leaves a black cell with no message.
- Its own `verify` tool fails its pixel check on this PC.

## Risks with MosaicPlayer
- **No published release.** The README's download links lead to an empty releases page. Packaging is ours to own; its PyInstaller build works (98 MB zip).
- **Its tests assume Linux:** 11 fail on Windows (mostly path separators and symlinks). Fix those early so the suite protects our changes.
- **Its default layout crops** (the "puzzle" packing crops up to 15% to fill gaps). We need a fixed grid of up to 6 tiles with no cropping.
- **It adds a tile per dropped file** (it has no fixed cells), so the 6-tile cap and "replace which tile?" are new work.
- **GPL-3.0-or-later.** Our app inherits this license if it is distributed.

## Work this implies (both bases need it; sized for MosaicPlayer)
Small: accept images in the drop filter; remove the speed controls; cap at 6 tiles with "replace which tile?"; fixed grid without cropping; GPU-only decode policy. Medium: hover controls to spec; packaging and startup time; fix the Windows tests. Large: library sidebar with thumbnails; move, copy and delete with undo; R22 playlists and tags (SQLite, tag rules, import and export).

## Still open
- 10-minute memory at 6 tiles: MultipleVideoPlayer flat (no leak). MosaicPlayer was stable but measured over only 1.6 minutes of playback (its window was minimized, which pauses it); re-run it in Phase 2 alongside the first performance checks.
- A real iPhone HEIC photo (tile-grid HEIC) is untested. My synthetic HEIC decodes.
- I worked from the 1.4 matrix as recorded in `PROGRESS.md`; the full build plan was not pasted this session. If the plan specifies a report format, I'll re-cut this to match.

**Approve MosaicPlayer as the base, and Phase 2 starts from it.** No feature code has been written.
