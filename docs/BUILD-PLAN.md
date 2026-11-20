> Saved verbatim from the original kickoff message (2026-11-18). Later additions live in separate files and take precedence where they conflict:
> - **R22 Playlists and tags:** `docs/R22-playlists-and-tags.md` (tags go on videos; confirmed 2026-11-19). It replaces "Save playlist / Open playlist" in section 2.8.
> - **Maximum 6 tiles on the wall** (decided on the Windows PC; see `PROGRESS.md`, Requirements changes). Overrides the 9/12-tile targets below.
> - Current status and decisions: `PROGRESS.md`, `HANDOFF.md`, `ARCHITECTURE.md`.

# Multi-Video "Compiled Talks" Player: Build Plan for Claude Code

Paste this whole file into Claude Code as the first message in an empty working folder on the Windows machine. Replace nothing; the plan tells you what to discover.

---

## 0. Kickoff prompt (read first)

You are building an **internal-use, Windows-native desktop app**: a multi-video player where you drag and drop files in, each file becomes its own tile, tiles play together in one window, and the window can be normal (resizable), maximized, or full screen. There is no borderless mode.

**Approach:** do not start from scratch. Adapt an existing open-source player built on **mpv** (a free playback engine). Primary candidate: **MultipleVideoPlayer** (https://github.com/alan52013141314/MultipleVideoPlayer, which redirects to hozumikiruse/MultipleVideoPlayer; Rust; GPL-3.0). Backup candidate: **MosaicPlayer** (https://github.com/itsui/mosaicplayer; mpv + Qt; GPL-3.0).

**Important: everything I know about these repos comes from READMEs. Nothing has been tested.** Phase 1 is a discovery and verification phase. Do not assume the framework, language, file layout, or feature list. Report what you find before building.

**Working rules**
1. Work in a git branch per phase. Commit after each feature with a clear message. Never force-push.
2. Keep the upstream LICENSE (GPL-3.0), copyright notices, and attribution. Add a `NOTICE.md` crediting upstream authors and any third-party libraries (mpv, FFmpeg).
3. Maintain `PROGRESS.md` at the repo root: what is done, what is in progress, what failed, decisions made, and open questions. Update it after every feature.
4. Maintain `ARCHITECTURE.md`: how the app is structured (written in Phase 1, kept current).
5. Do not rewrite unrelated upstream code. Make the smallest change that meets each requirement.
6. Do not swap the playback engine, UI framework, or language without stopping and asking me first.
7. No telemetry, no network calls, no auto-update. The app is local-only.
8. When something cannot be verified by running it, say so explicitly. Do not claim a feature works until you have run it and tested it against the acceptance criteria below.
9. If a requirement turns out to be impossible or very costly in the chosen codebase, stop and tell me the options and costs before continuing.

**My environment:** Windows 10/11, PowerShell. Prefer commands that work in PowerShell. Check which GPU is installed (`Get-CimInstance Win32_VideoController`) and tell me, because hardware HEVC decoding depends on it.

---

## 1. Product requirements

| # | Requirement | Priority |
|---|---|---|
| R1 | Drag and drop video, GIF, and image files (and folders) from Windows Explorer onto the window; each file automatically becomes a new tile | Must |
| R2 | Plays HEVC/H.265 (hardware accelerated when the GPU supports it), H.264, and common containers (MP4, MKV, MOV, WebM, AVI) | Must |
| R3 | First-class support for animated GIFs (play, pause, loop) and still images (JPG, PNG, WebP, BMP, TIFF, plus HEIC/AVIF/animated WebP if the engine supports them), mixed freely with videos in the same grid | Must |
| R4 | Play controls that appear on hover, per tile | Must |
| R5 | Global audio control (master volume + master mute) on top of per-tile volume/mute | Must |
| R6 | Window modes: (a) normal, freely resizable window, (b) maximize/restore, (c) true full screen; switch from the footer or by hotkey. No borderless mode | Must |
| R7 | Left sidebar file browser that can be opened and closed: folder tree plus a file pane with Grid (thumbnails) and List views, sorting (name, date modified, size, type, duration, resolution), a "recently modified" quick view, and type filters | Must |
| R8 | Settings and last session persist between launches | Should |
| R9 | Portable Windows build (`.exe` + dependencies in a zip) | Must |
| R10 | Handles many simultaneous tiles gracefully (no crashes; degrade predictably) | Should |
| R11 | Zoom and pan the currently hovered video, image, or GIF, independently per tile: mouse wheel zooms, middle-mouse drag pans | Must |
| R12 | Quick controls to remove or delete items: one-click/one-key remove from the grid with undo, "clear all", and an optional, safe "delete file" (Recycle Bin only) | Must |
| R13 | Quick "send to folder": a user-defined list of destination folders; one click or hotkey moves (or copies) the hovered/selected file(s) to the chosen folder, with undo | Must |
| R14 | GPU-accelerated throughout (hardware video decode, GPU rendering, GPU-friendly UI), very fast media switching (preloading, reused players, no black flashes), and autoplay on add | Must |
| R15 | End-of-media behavior per tile: Loop (repeat current) or Next (advance to the next file in the folder/queue), with global default and per-tile override | Must |
| R16 | Left-click-drag horizontally on a video tile scrubs through it, natural-scroll direction (drag left = forward, drag right = backward); a horizontal trackpad swipe does the same | Must |
| R17 | Drag a file from the sidebar onto the video area to add it as a tile; each tile has a close (X) control; right-click a tile or sidebar file opens a context menu (play, end behavior, reset zoom, move to, copy to, show in Explorer, copy path, close, delete) | Must |
| R18 | Layout and look: left library, center wall, right panel (details + pinned destinations + hotkeys), one footer holding the main controls (master volume, end-of-clip behavior, window mode, panel toggles). Dark theme, light text, a single blue accent used only for selection and active states, no yellow | Must |
| R20 | The app is just as good as a single-video viewer as a multi-video wall: it must start and work well with one file (or one file at a time), and **Next / Previous file hotkeys** work in every layout without needing to hover a tile | Must |
| R21 | Optional "Enhance" for video and still images: real-time GPU upscaling and light sharpening using mpv shaders, toggled per tile, off by default | Should |
| R19 | Details panel for the current file (hovered tile, last viewed tile, or selected in the sidebar): resolution, duration, size, date modified, format, frame rate, decode path, location; buttons for Remove from wall, Delete file, Show in Explorer, each with its hotkey shown | Must |
| R22 | Playlists and tags: one video can be in many playlists and carry many tags (added 2026-11-19; spec in `docs/R22-playlists-and-tags.md`) | Must |

Out of scope: editing, exporting, streaming, network sources, cloud sync, accounts, auto-update. **Also explicitly out of scope (do not build): playback speed controls, frame stepping, subtitle controls, video filters/effects, equalizers, or any "advanced player" menus.** Keep the controls minimal: play/pause, seek and scrub, volume/mute, loop/next mode, remove, move-to-folder, zoom/pan. A visual reference for the target layout and interactions is the published HTML mockup (see section 2.14); match its behavior unless a section below says otherwise.

---

## 2. Phase 1: Recon and verification (do not build features yet)

**Goal:** know exactly what we have before touching it.

### 1.1 Environment
- Install or verify prerequisites for whatever the repo needs. For a Rust project: Rust via rustup (MSVC toolchain), Visual Studio Build Tools (C++ workload), Git. For a Qt/C++ or Python project: whatever its README says. Install nothing without telling me what and why.
- Record GPU model and driver version in `PROGRESS.md`.

### 1.2 Get and build the primary candidate
1. Clone MultipleVideoPlayer into a new empty folder. Check `git log -1` and record the last commit date and the latest release tag.
2. Read README, LICENSE, build files, and the directory tree. Record in `ARCHITECTURE.md`:
   - Language and UI framework (do not assume; find out)
   - How mpv is embedded (linked library, bundled `libmpv-2.dll`, spawned process, render API, or native child window)
   - Where tiles are created, where drag and drop is handled, where hover controls are drawn, where window mode (maximize/full screen) logic lives, where volume is set, how settings are stored
   - Which mpv options are set (especially `hwdec`)
3. Build in release mode and run it. Record any build errors and how you fixed them.
4. Download the project's latest portable release too and compare behavior with your local build.

### 1.3 Build the test media set
Use FFmpeg (install via `winget install Gyan.FFmpeg` if missing) to generate synthetic files into a `testmedia/` folder (git-ignored). Use `lavfi` test sources with a visible frame counter and an audible tone so playback and audio are easy to verify. Create at least:
- `hevc_4k_30.mp4` (H.265, 3840x2160, 30 fps, 60 s, tone A)
- `hevc_1080_60.mp4` (H.265, 1920x1080, 60 fps, 60 s, tone B)
- `hevc_10bit.mp4` (H.265 Main10, 1080p)
- `h264_1080_30.mp4` (H.264, 1080p, tone C)
- `h264_4k_30.mkv`
- `vp9.webm` (a codec-diversity check)
- `anim.gif` (animated, looping, at least 2 s), `anim_once.gif` (plays once), `anim_variable.gif` (variable frame delays), `anim_large.gif` (50 MB or more), `anim_transparent.gif`
- `still.jpg`, `still.png`, `still.webp`, `anim.webp` (animated WebP), `transparent.png`, `big_8000x6000.jpg`, `exif_rotated.jpg` (EXIF orientation 6, so it must display upright), `still.heic` and `still.avif` if you can generate them (FFmpeg may not; if not, note that and ask me for samples)
- `no_audio.mp4` (video-only)
- `corrupt.mp4` (a truncated copy of a valid file)
- `notamedia.txt` (to test rejection)
Put real talk recordings in a separate `testmedia/real/` folder when I provide them.

### 1.4 Run the baseline test matrix (against the unmodified upstream build)
Record pass / fail / partial / unknown for each in a table in `PROGRESS.md`:

| Test | How to check |
|---|---|
| Drop 1 file creates a tile | Drag from Explorer |
| Drop 6 files at once | Multi-select drag |
| Drop a folder | Drag folder |
| HEVC 4K plays smoothly | Visual + frame counter |
| **Hardware decode active** | Task Manager > Performance > GPU > "Video Decode" graph moves; also confirm in the app's mpv log or properties (`hwdec-current`) |
| Animated GIF animates and loops, with correct frame timing | Visual; compare against a GIF with variable frame delays |
| Still images display (incl. EXIF-rotated photo, large image, transparent PNG) | Visual |
| HEIC / AVIF / animated WebP | Drop each; record supported or not |
| Removing a tile frees memory | Task Manager before/after |
| Does upstream have any move/copy-to-folder or delete feature? | Menus, README, source search |
| Which renderer and hwdec path does upstream use (GPU renderer, zero-copy vs copy-back)? | Source and mpv log |
| Baseline switch latency (action to first frame) for 1080p H.264, 1080p HEVC, 4K HEVC, GIF, large JPG | Add temporary timing logs; report median and worst |
| Does upstream have autoplay, loop/next, a sidebar, thumbnails, speed controls to remove? | UI and source |
| Hover controls appear/disappear | Mouse over tile |
| Zoom/pan/scrub on hovered tile (check whether upstream already has any) | Wheel, middle-drag, left-drag over a tile |
| Per-tile volume/mute | Listen / tone test |
| Maximize and restore | Toggle |
| Full screen | Toggle |
| Resize the normal window | Drag edges |
| Corrupt file does not crash app | Drop `corrupt.mp4` |
| Non-media file is rejected gracefully | Drop `notamedia.txt` |
| 6, 9, 12 tiles of 1080p HEVC: CPU %, GPU %, dropped frames | Task Manager + log |
| 4 tiles of 4K HEVC | Same |
| Memory after 10 minutes with 9 tiles | Task Manager |

### 1.5 Decision gate (stop and report to me)
Write a short report (max one page) with:
- What the baseline can do today vs. the requirements R1 to R10
- The gaps, each with a size estimate (small / medium / large) and the file(s) you would change
- Verdict: **proceed with MultipleVideoPlayer**, **switch to MosaicPlayer**, or **clean build on libmpv**
- Risks you found (single-maintainer repo, stale deps, framework limits, performance ceilings)

**Proceed rule:** if the baseline plays HEVC with hardware decode active and 6+ tiles run without dropped frames on my machine, proceed with it. If it fails that, repeat 1.2 to 1.4 on MosaicPlayer (https://github.com/itsui/mosaicplayer) and compare. If both fail, propose the clean-build option (a new app on libmpv; C#/WPF with mpv.net as reference, or Tauri with a libmpv plugin) and wait for my approval.

---

## 3. Phase 2: Core features

Implement in this order. For each: build, run, test against the acceptance criteria, update `PROGRESS.md`, commit.

### 2.1 Drag and drop and the playlist model (R1)
- Introduce a single source of truth: a list of **media items** (id, absolute path, type = video/gif/image, per-item volume, muted flag, loop flag, position in layout). The UI renders from this list.
- Accept drops of: multiple files, folders (recursive, optional setting; default: one level), mixed types. Sort a dropped folder by name (natural sort).
- Dedupe: dropping a path already open adds a second tile only if I confirm via a setting ("Allow duplicates", default off with a brief on-screen notice).
- Reject unsupported files with a non-blocking toast listing what was skipped. Probe by extension first, then by letting mpv fail gracefully.
- Add a visible drop-zone state: when a drag is hovering over the window, show an overlay ("Drop to add").
- Empty state: a centered hint ("Drag videos here") when there are no tiles.
- **Acceptance:** drop 1, drop 6, drop folder of 20, drop a mix of video+GIF+JPG+txt; correct tiles appear, `.txt` is skipped with a notice, no crash, order is stable.

### 2.2 Media handling (R2, R3)
- **mpv settings to verify and apply** (confirm exact option names against the mpv version bundled; do not trust this list blindly):
  - Hardware decode must be explicitly enabled: use `hwdec=auto-safe` (or `d3d11va` first, then `nvdec` fallback). Log `hwdec-current` per tile. Hardware decoding is **not** on by default in mpv.
  - Videos: `keep-open=yes` (hold last frame), loop controlled per tile.
  - GIF: `loop-file=inf` by default; verify that mpv actually animates GIFs in this embedding.
  - Still images: `image-display-duration=inf` so images stay on screen; images get no seek bar and no play/pause.
  - Audio-less files: hide the volume control on that tile or show it disabled.
- If hardware decode fails for a stream, fall back to software and show a small badge on the tile ("SW decode") so I can see when it happens. Do not fail silently.
- **Animated GIFs (first-class, not an afterthought):**
  - Play automatically on add, loop by default (honor the GIF's own loop count if the engine exposes it; a per-tile "loop" toggle overrides).
  - Hover bar: play/pause and the loop/next mode button only (no speed control, no frame stepping).
  - Respect per-frame delays; verify with a GIF that has variable frame timing. Report if the engine plays it too fast or slow.
  - Large GIFs (for example 50 MB+) must not freeze the UI on add; load asynchronously and show a loading state on the tile.
  - Transparent GIFs/PNGs render over the tile background (dark by default, with a setting for a checkerboard).
  - If the engine cannot play a particular GIF correctly, fall back to converting it on load (for example to a temporary H.264/WebM via FFmpeg in `%TEMP%`, cleaned up on exit) and tell me; do not silently show a frozen frame.
- **Still images (first-class):**
  - Display at fit by default, with zoom/pan from section 2.9 so I can inspect details.
  - Respect EXIF orientation (photos from phones must not appear sideways).
  - Handle large images (for example 8000x6000) without lag; downscale for the tile view and use full resolution only when zoomed in, if the engine does not do this itself.
  - Supported: JPG, PNG, WebP (including animated WebP), BMP, TIFF, GIF; also HEIC and AVIF if the bundled FFmpeg/mpv build supports them (test and report; do not promise).
  - Image tiles have no seek bar. They get: remove, focus/maximize, zoom reset, and "next/previous image in folder" with Left/Right arrows when the tile is in focus mode (nice-to-have; nice for flipping through a folder of stills).
  - Auto-advance through images in a folder is handled by the Loop/Next mode in section 2.13 (images advance after a set display time), not by a separate slideshow feature.
  - Show a small type badge on each tile (VIDEO / GIF / IMG) and, in the hover bar, resolution and file size, so mixed grids are easy to read.
- **Acceptance:** all files in `testmedia/` display or play correctly; the Task Manager Video Decode graph moves for HEVC; GIF loops with correct timing; JPG/PNG/WebP show indefinitely; a phone photo with EXIF rotation displays upright; an 8000x6000 image loads without UI freeze; a transparent PNG shows correctly; corrupt file shows an error state on its tile (not a crash).

### 2.3 Tile layout (supports R1, R6, R10)
- Default **auto grid**: choose rows/columns to best fit tile count and window aspect ratio. **Fit rule (default and baseline for zoom): scale each video, GIF, or image so its longest side exactly fits the tile, keeping the full frame visible and the aspect ratio unchanged** (mpv `keepaspect=yes`, `panscan=0`; verify). A landscape file fills the tile's width, a portrait file fills its height, and the leftover area is black bars, never stretched or cropped. This applies after rotation metadata (EXIF orientation, video rotation) and to pixel-aspect-ratio-corrected sizes. 100% zoom in section 2.9 means this fit size. Keep an optional setting "Fill tile (crop)" (default off) and make sure it is never applied silently.
- **Single-video use (R20):** the app will often be used with one file. With exactly one tile, the layout is a single full-size tile (no grid chrome, no empty cells), the sidebar can be hidden, and everything works the same: controls, scrub, zoom, Details, Send to. A setting "Open one file at a time" (default off) makes a file added from the library or Explorer *replace* the current tile instead of adding a second one; the existing tile's volume and end-of-clip mode carry over. Opening a file from Windows ("Open with") or double-clicking it in the sidebar in this mode behaves like a normal media player: that file fills the window and Next/Previous move through its folder.
- **Which tile do keyboard commands act on?** In this order: the hovered tile; otherwise the focused/selected tile; otherwise the tile most recently hovered (the "current" file shown in Details); and if only one tile exists, that tile. Hotkeys must therefore work after the mouse leaves the window or while using the keyboard alone. Apply this rule to every per-tile hotkey, not just Next/Previous.
- **Focus mode:** double-click a tile to enlarge it to fill the window; double-click again (or Esc) to return to grid. Other tiles keep playing (setting: "pause others while focused", default on to save GPU).
- Drag to reorder tiles (nice-to-have; implement if the framework makes it cheap).
- Remove tile: control on the hover bar and `Delete` key on the selected tile.
- **Acceptance:** 1, 2, 3, 4, 6, 9, 12 tiles lay out cleanly at several window shapes; focus mode round-trips; removing a tile releases its mpv instance (verify memory drops).

### 2.4 Hover controls (R4)
- Per tile, an overlay that fades in when the mouse enters the tile and fades out about 2 seconds after the mouse stops moving or leaves.
- Controls: play/pause, seek bar with elapsed/total time, mute button, per-tile volume slider, loop/next mode button (section 2.13), previous/next buttons, move-to-folder button (section 2.11), remove (X), maximize/focus. No speed controls. For GIFs: play/pause + mode + prev/next only. For images: prev/next + mode + remove + maximize only.
- Keyboard: Space toggles play/pause on the hovered tile; Left/Right seek 5 s; Up/Down per-tile volume; M mutes the hovered tile.
- **Known risk to resolve early:** if mpv renders into a native child window, standard UI drawn by the app may be hidden behind it (the "airspace" problem). Find out how upstream draws its overlay and reuse that technique. If upstream uses the mpv render API into the app's own surface, overlays are straightforward. Report which case applies.
- **Acceptance:** overlay appears on hover, hides after idle, never flickers, never blocks scrubbing, panning, or window resizing, and works at 12 tiles without lag.

### 2.5 Global audio (R5)
- A **master volume** slider (0 to 100%) and **master mute** in the persistent footer control strip (section 2.14). Show current master level.
- Effective volume per tile = `tile_volume x master_volume` (clamp to mpv's allowed range). Changing master updates all tiles immediately, without altering their saved per-tile levels.
- Hotkeys: `Ctrl+Up` / `Ctrl+Down` master volume, `Ctrl+M` master mute, `Ctrl+Shift+M` mute all but the focused tile.
- Optional "Solo audio" mode (setting, default off): only the hovered or focused tile is audible; others auto-mute.
- Master volume and mute state persist across launches.
- **Acceptance:** using the tone-per-file test media, verify by ear that master scales all tiles, per-tile changes only affect one, and mute states combine correctly. Log effective volumes in debug output for each change.

### 2.6 Window modes (R6)
Implement one window-mode state machine with three states plus a persistent "always on top" toggle. **There is no borderless mode; do not build one.** Keep the standard Windows title bar and frame.

| Mode | Behavior |
|---|---|
| **Normal** | Standard framed window: title bar, resizable by all edges and corners, draggable by the title bar |
| **Maximized** | The standard Windows maximize: fills the work area (taskbar stays visible). Toggle again to restore the previous size and position |
| **Full screen** | Covers the current monitor exactly (including above the taskbar); Esc or F11 exits; remembers the previous state (normal or maximized) and restores it |

- Footer buttons: **Maximize** and **Full screen**. Clicking the active one returns to the previous state.
- Keys: `F11` full screen toggle, `F10` maximize/restore, `Ctrl+T` always on top, `Esc` exit full screen or focus mode. Double-clicking the title bar maximizes (standard Windows behavior; do not override it).
- A small settings menu or right-click menu also exposes these.
- Because left-drag on a tile now scrubs (section 2.9), the window moves only by its title bar. This removes any conflict between scrubbing and moving the window.
- Multi-monitor: full screen goes to the monitor the window is mostly on; moving between monitors with different DPI scaling must not blur or misplace the window.
- **Acceptance:** each transition works in both directions without video tearing or a black frame longer than about 200 ms; maximize/restore returns to the exact previous size and position; full screen covers the entire monitor and hides the taskbar; dual-monitor test if available; window state is restored after a restart.

### 2.7 File-browser sidebar (R7)
- A collapsible left sidebar toggled by `Ctrl+B` and a visible button. Default width about 280 px, user-resizable, collapsed width zero. Collapsing must **give the width back to the tile grid** (no empty gap).
- **Layout:** two panes inside the sidebar. Top or left: a **folder tree** rooted at one or more user-chosen root folders (default: last opened folder; "Open Folder..." and "Add root" buttons), with a Favorites/Pinned section that includes the send-to-folder destinations from section 2.11. Bottom or right: a **file pane** showing the media in the selected folder.
- **Two view modes for the file pane**, switched by a toggle button in the sidebar header (and `Ctrl+Shift+G` for Grid, `Ctrl+Shift+L` for List):
  - **Grid view:** a thumbnail grid with a thumbnail-size slider (small, medium, large). Each thumbnail shows a small type badge (VIDEO / GIF / IMG), duration for videos, and the file name on hover or below.
  - **List view:** a details table with sortable column headers: small thumbnail/icon, Name, Type, Duration, Resolution, Size, Date modified (and optionally Date created). Columns can be shown/hidden and resized.
- **Sorting:** Name (natural order, so `clip2` comes before `clip10`), Date modified, Date created, Size, Type, Duration, Resolution; ascending/descending toggle. Sorting works the same in both views.
- **Recently modified:** a one-click quick view that sorts by Date modified, newest first, with a time filter (Today, Last 7 days, Last 30 days, All). A "Recent" entry at the top of the folder tree shows recently modified media across all root folders.
- **Filters and search:** type filter (All / Videos / GIFs / Images), a search box (file name contains), and an "Include subfolders" toggle that flattens everything under the selected folder into one list.
- **Live updates:** watch the selected folder for changes (new, renamed, deleted, moved files) and update the pane without a manual refresh.
- Show only media files and folders that contain them. Never block the UI while listing, probing duration/resolution, or generating thumbnails: do all of it on background threads, lazily, for visible items first.
- Actions: double-click or Enter adds the file as a tile; drag from the sidebar onto the grid adds it; right-click offers "Add to grid" and "Reveal in Explorer"; a "Add all in folder" button.
- **Thumbnails (required, not optional):** video = a frame near the 10% mark (fall back to the first frame), GIF = first frame, image = downscaled copy. Generate with a small background worker pool (use hardware-assisted decode where the engine allows it), cache on disk in `%LOCALAPPDATA%\<AppName>\thumbs` keyed by path + modified time + size, with a size cap (default 1 GB) and least-recently-used cleanup. The grid must be **virtualized** (only visible items are rendered), show placeholders instantly, and fill in thumbnails as they arrive. "Clear thumbnail cache" button in settings.
- **Multi-select in the sidebar** (Ctrl+click, Shift+click, Ctrl+A). "Play folder in a tile" action (button and right-click): creates one tile whose queue is the folder's files in the current sort order and filters (see section 2.13).
- Persist: view mode (Grid/List), thumbnail size, sort field and direction, filters, visible columns, pinned folders, and root folders.
- Sidebar open/closed state and root folder persist.
- **Acceptance:** opens/closes smoothly with 9 tiles playing and no video stutter; a folder with 5,000 media files lists and scrolls smoothly in both Grid and List view, with thumbnails filling in progressively and the UI never freezing; switching Grid/List and changing sort order take effect instantly and persist across restarts; sort by Name, Date modified, Size, Duration, and Resolution each give correct order (verify against Explorer); the "Recent" view shows the newest files first and respects the time filter; creating or deleting a file in the folder from Explorer updates the pane within about 2 seconds; the thumbnail cache is reused on the second visit (no regeneration) and stays under its size cap; adding from the sidebar works by double-click, Enter, and drag; "Play folder in a tile" works.

### 2.8 Settings and persistence (R8)
- Store a JSON settings file in `%APPDATA%\<AppName>\settings.json`, versioned with a `schema_version` field and tolerant of missing or unknown keys.
- Persist: window mode, size, position, monitor, always-on-top, sidebar state and root, master volume/mute, layout options, hardware-decode preference, the destination-folder list (section 2.11) with its move/copy and name-collision settings, and the last session's playlist (paths, per-tile volume, positions optional).
- A "Restore last session" prompt or setting on launch (default: restore, with missing files shown as error tiles that can be removed).
- Also provide "Save playlist..." and "Open playlist..." (`.json`), so a set of talks can be reloaded as a "compilation".
- **Acceptance:** quit and relaunch restores everything; deleting settings.json starts clean without error; a corrupt settings.json is backed up and replaced with defaults.

### 2.9 Zoom, pan, and scrub on the hovered tile (R11, R16)
**Input scheme (final):** mouse **wheel** zooms, **middle-mouse drag** pans, **left-mouse drag** scrubs through a video. These three do not overlap. Interpretation: the user zooms into the tile under the mouse and moves around the zoomed image. If upstream already has something similar, reuse it and tell me. If anything below is ambiguous in practice, pick the behavior that matches common image-viewer conventions and note the choice in `PROGRESS.md`.

- **Scope:** applies to the single tile currently under the mouse cursor (the "hovered tile"), for videos, GIFs, and still images. Each tile keeps its own zoom and pan state; zooming one tile never affects others. Works in grid view and in focus mode.
- **Zoom input:**
  - Mouse wheel over the video area zooms in/out, **centered on the cursor position** (the point under the cursor stays under the cursor).
  - Touchpad pinch zooms if the toolkit exposes it (nice-to-have).
  - `+` / `-` keys zoom the hovered tile in steps; `0` resets zoom and pan (fit); `1` jumps to 100% (native pixel size) if cheap to implement.
  - Zoom range: 100% (fit) up to at least 800%, with smooth, small steps (about 10 to 15% per wheel notch). Fit is the minimum; no zooming out below fit.
- **Pan input:**
  - When zoomed in, holding the **middle mouse button** and dragging pans the video within the tile (the content follows the cursor). Show a "grab" cursor while panning.
  - Arrow keys are reserved for seek/volume (section 2.4), so use `Shift` + arrow keys to pan the hovered tile when zoomed.
  - Clamp panning so the video can never be dragged fully out of the tile; some part of the image always stays in view. At fit zoom, panning is disabled.
  - Suppress the default middle-click behavior (Windows auto-scroll) over tiles.
- **Scrub input (R16), videos only:**
  - Press and hold the **left mouse button** on the video area (not on the hover bars) and drag horizontally to scrub. Use **natural-scroll direction**: dragging left moves forward in time, dragging right moves backward.
  - A horizontal trackpad swipe (wheel events with horizontal delta) scrubs the same way. Vertical wheel still zooms.
  - Sensitivity: dragging across about two thirds of the tile width moves through the whole clip (tunable constant; for very long files, cap the span so a full-width drag is at most a few minutes). Show a large, brief time readout in the tile center while scrubbing (for example ">> 1:12 / 3:20").
  - While the button is held, use fast keyframe seeks for responsiveness (mpv `seek ... absolute+keyframes`; verify against the bundled version) and do an exact seek on release. Play state is unchanged by scrubbing; periodic position updates pause while dragging so the playhead does not fight the user.
  - A left click without movement (under about 4 px) toggles play/pause. A double-click still toggles focus mode.
  - GIFs and images do not scrub (a left-drag does nothing). Scrub works while zoomed; it never pans.
  - Hide the hover bars while a drag is in progress so they do not intercept the pointer, and capture the pointer so the drag continues if the cursor leaves the tile.
- **Conflicts to resolve explicitly:**
  - The wheel must **not** zoom when the cursor is over the hover control bar, the seek bar, or the volume slider; there it keeps its normal slider behavior.
  - Per-tile volume stays on Up/Down and the slider (section 2.4); do not use the wheel for volume by default.
  - If the user drags on the video area while not zoomed, nothing pans; left-drag never pans and never moves the window (the window moves only by its title bar), so a left-drag over a tile is a scrub on videos and a no-op on GIFs and images.
  - Double-click still toggles focus mode (section 2.3); `0` or the context menu resets zoom and pan (middle-click is reserved for pan-drag).
- **Feedback:** while zoomed, show a small unobtrusive badge in the tile corner (for example "250%") that fades out after about 1.5 seconds and reappears on change; the hover bar gets a "reset zoom" button that appears only when zoom is not 100%. Show a "grab" cursor while panning.
- **Implementation notes (verify against the bundled mpv and the repo's embedding method; do not assume):**
  - mpv exposes per-instance video zoom and pan properties (`video-zoom`, `video-pan-x`, `video-pan-y`). Check the exact names, units (zoom is logarithmic in mpv: 0 = 100%, 1 = 200%), and whether they work for GIFs and still images in this embedding.
  - Zoom-toward-cursor requires adjusting pan as zoom changes: compute the cursor position relative to the video rectangle, then adjust `video-pan-x/y` so that point stays fixed. Write this math as a small pure function with unit tests.
  - If the embedding makes mpv's properties unreliable (for example, a render path that ignores them), fall back to applying a scale/offset transform in the app's own rendering layer. Stop and tell me before taking that route if it means significant code.
  - Hardware decoding must stay on while zoomed; zooming must not trigger a re-decode or a visible stutter.
  - Pausing a video must not reset zoom. Seeking or looping must not reset zoom. Loading a new file into a tile starts at fit.
- **Persistence:** zoom and pan are session-only by default. Add a setting "Remember zoom per file" (default off). When on, store zoom and pan keyed by file path in the session file.
- **Performance:** zoom and pan must stay smooth (no visible lag or dropped frames in other tiles) with 9 tiles playing and one being zoomed.
- **Acceptance:**
  1. Wheel up over a tile zooms in toward the cursor; wheel down zooms back out; the point under the cursor stays fixed (test with the frame-counter test video: the counter stays under the cursor while zooming).
  2. Zoomed tile pans by middle-drag and by `Shift` + arrows; pan clamps so the video never leaves the tile; at fit zoom, middle-drag does nothing. Left-drag on a video scrubs (drag left = forward, drag right = backward), a click toggles play/pause, and left-drag on a GIF or image does nothing.
  3. Zooming tile A does not change tile B; moving the mouse to tile B makes the wheel affect B.
  4. Wheel over the seek/volume controls does not zoom.
  5. `0` and the context menu reset; the zoom badge shows the correct percentage.
  6. Works for HEVC video, H.264 video, an animated GIF, and a still image; playback continues smoothly while zoomed; hardware decode graph still shows activity.
  7. Zoom/pan state survives pause, seek, loop, entering/leaving focus mode, and a window resize (the zoomed region scales sensibly with the tile), but resets when the file is replaced.

### 2.10 Quick remove and delete controls (R12)
Interpretation: "quick controls for deleting something" most likely means removing a tile from the grid fast. I am also including an optional way to delete the actual file from disk, kept deliberately safe. Implement the grid-removal parts first; treat disk deletion as a separate, opt-in feature. Report your interpretation in `PROGRESS.md`.

**A. Remove from grid (does not touch the file on disk)**
- Every tile has a clearly visible **X** button in the hover bar's top-right corner, large enough to hit quickly (at least 28x28 px), red on hover.
- `Delete` or `Backspace` removes the hovered tile (or the selected tile, if one is selected); no confirmation dialog.
- Right-click a tile gives the context menu defined in section 2.15 (it includes Close tile; also offer "Remove all others" there).
- **Undo:** every removal shows a brief toast ("Removed 'name.mp4'. Undo") for about 6 seconds, and `Ctrl+Z` restores the last removed tiles (keep an undo stack of at least 20 removals) in their original position, with their volume, zoom, and playback position. `Ctrl+Shift+Z` redoes.
- **Multi-select:** `Ctrl+click` toggles selection on tiles, `Shift+click` selects a range, `Ctrl+A` selects all; selected tiles show a highlighted border. `Delete` removes all selected tiles as one undoable action. A small floating bar appears when 2 or more tiles are selected: "N selected: Remove, Clear selection".
- **Clear all:** a "Clear all" button in the footer (and in the wall's context menu) and `Ctrl+Shift+Delete`. This one asks for confirmation if more than 3 tiles are open, and is also undoable.
- Removing a tile must free its engine instance and memory immediately (verify, as in section 2.3).
- Removing from the sidebar's "open in grid" markers: if a file shown in the sidebar is currently open as a tile, mark it with a dot; a quick click on the dot removes that tile.

**B. Delete the file from disk (opt-in, safe)**
- Setting "Enable delete-from-disk commands", **default off**. When off, none of the commands below appear in menus.
- When on: context menu item "Delete file...", and hotkey `Shift+Delete` on the hovered/selected tile(s), and the same on files in the sidebar.
- Always sends the file to the **Windows Recycle Bin** (use the proper shell API, for example `SHFileOperation` / `IFileOperation` with the "allow undo" flag; in Rust, the `trash` crate is a common choice, but verify the current best option), never permanently deletes, and never uses raw `rm`/`DeleteFile`.
- Always asks for confirmation first, showing the file name, full path, and size, with the default button on Cancel. A "Don't ask again this session" checkbox is allowed but resets on restart.
- Removes the tile after a successful delete. If the delete fails (file locked, no permission, network drive that has no Recycle Bin), show the reason and keep the tile.
- Refuse to delete: anything that is not a media file the app opened itself; anything in a system folder; and any batch of more than 25 files in one action without a second, stronger confirmation that states the count.
- Log every disk deletion (path, time) to the app log.
- Undo for disk deletion is "restore from Recycle Bin," which is the user's job in Explorer; say that clearly in the confirmation text. Do not pretend `Ctrl+Z` can restore it.

**Acceptance**
1. Click X and press `Delete` both remove a tile instantly; the toast and `Ctrl+Z` restore it with the same volume, zoom, and position; redo works.
2. Multi-select with Ctrl/Shift click and Ctrl+A; `Delete` removes all selected as one undo step.
3. "Clear all" with 6 tiles asks for confirmation, then clears; `Ctrl+Z` brings all 6 back.
4. Removing 20 tiles in a row and undoing all of them does not leak memory or crash.
5. With delete-from-disk **off**, no delete-file command is reachable by any menu or hotkey (verify `Shift+Delete` does nothing).
6. With it **on**: delete a test file; confirm the dialog content is accurate, the file lands in the Recycle Bin and can be restored from Explorer, the tile disappears, and the action is logged. Cancel leaves everything untouched. A locked file shows an error and keeps the tile.
7. Never touches files outside what the app opened; test by trying to delete a file that is open in another program.

### 2.11 Quick "send to folder" destinations (R13)
Purpose: sort media fast. I define a set of destination folders once (for example "Keep", "Use in deck", "Review later", "Archive"); then one click or one key sends the file I am looking at to that folder. Default action is **Move**; **Copy** is available as a modifier.

**A. Managing destinations**
- A "Destinations..." settings panel (also reachable from the right-click menu and the right panel's "Pin a folder" button). For each destination: a **label**, a **folder path** (pick with a folder dialog, or drag a folder from Explorer onto the panel), an optional **color**, and an automatic **hotkey slot** (1 to 9, by order). Add, edit, reorder (drag), and remove destinations. Unlimited destinations are allowed; only the first 9 get hotkeys, the rest are reachable by menu.
- "Create folder if missing" option per destination (default off). Validate paths on save and again at launch: a destination whose folder no longer exists or is offline shows a warning icon and cannot be used until fixed (never silently create or recreate it).
- Destinations are saved in `settings.json` and survive restarts. Provide Export/Import of the destination list as JSON, so I can reuse it on another machine.

**B. Sending files (three ways, all doing the same thing)**
1. **Hover bar button:** a "Move to..." button on every tile's hover bar opens a compact popup listing the destinations (label + color + hotkey). One click sends the file. Optionally also show the first 3 destinations as one-click chips directly on the hover bar (setting, default on).
2. **Hotkeys:** `Ctrl+1` to `Ctrl+9` move the hovered tile (or all selected tiles) to destination 1 to 9. `Ctrl+Shift+1` to `Ctrl+Shift+9` **copy** instead of move. (Plain `0` and `1` are already used for zoom reset and 100% zoom in section 2.9, so do not use bare digit keys.)
3. **Right-click menu:** "Move to" and "Copy to" submenus listing all destinations. The sidebar's file context menu gets the same submenus, so files can be sorted straight from the file browser.
- Optional: drag a tile (or a sidebar file) onto a destination chip in an on-screen destination bar (setting, default off).
- Works on single tiles and on multi-selection (section 2.10); a batch is one undoable action.

**C. What happens after a Move**
- Setting "After moving": (a) remove the tile from the grid (default), or (b) keep the tile, now pointing at the new path. Whichever is chosen, the tile's engine must release the file handle **before** the move, because Windows will not move a file that is open. Sequence: pause and close the file in that tile, perform the move, then either remove the tile or reopen it from the new path with the same playback position, volume, and zoom.
- Show a toast: "Moved 'name.mp4' to Keep. Undo", about 6 seconds, with `Ctrl+Z` also undoing it. Undo moves the file back to its original folder and restores the tile to its original position with its state. Keep an undo stack of at least 20 operations, shared with the removal undo in section 2.10 so `Ctrl+Z` always undoes the most recent action of either kind.
- Copy leaves the original and the tile untouched; toast says "Copied to Keep".

**D. Safety rules (do not skip)**
- **Name collisions:** if a file with the same name exists in the destination, never overwrite silently. Setting "On name collision": ask (default; options: Keep both with a numeric suffix like `name (2).mp4`, Replace, Skip), or always keep both, or always skip. Replace requires an extra confirmation showing both files' sizes and modified dates.
- **Same folder:** moving a file to the folder it is already in is a no-op with a brief notice.
- **Cross-drive moves** are a copy then delete. Do the copy, verify the byte size (and a checksum for files under a configurable size, default 2 GB), and only then delete the original. If the verify fails, delete nothing, remove the partial copy, and show an error. Show a progress indicator for large files and keep the UI responsive (do the work on a background thread; the tile shows a "moving" state).
- Refuse destinations inside system folders (`C:\Windows`, `C:\Program Files`, and so on) and refuse a destination that is inside the file's own source folder tree if that would cause loops. Handle long paths (over 260 characters) and network paths (UNC) without crashing; show a clear error if the destination is read-only or offline.
- Locked or in-use file (open in another program): show the reason, change nothing, keep the tile.
- A move never touches anything except the file(s) the app opened. Sidecar files (for example `.srt` subtitles next to a video with the same base name) are an optional setting, "Also move matching sidecar files", default off.
- Log every move or copy (source, destination, time, result) to the app log, and keep a "Recent moves" list in the UI (last 50) with an Undo button per entry while the files are still there.
- Batch moves of more than 25 files require a confirmation stating the count and destination.

**E. Acceptance**
1. Define 4 destinations; relaunch the app; they are still there with the right order, colors, and hotkey slots.
2. Hover a tile and click "Move to > Keep": the file lands in that folder, the tile is removed (or retargeted, per setting), the toast appears, and `Ctrl+Z` returns the file and tile to their original state.
3. `Ctrl+2` moves the hovered tile to destination 2; `Ctrl+Shift+2` copies instead and leaves the original in place. Bare `0` and `1` still do zoom actions.
4. Select 5 tiles, press `Ctrl+1`: all 5 move as one undoable action; one `Ctrl+Z` returns all 5.
5. Name collision: ask, keep both, replace, and skip each behave as described; nothing is ever overwritten without the extra confirmation.
6. Cross-drive move of a large file (use a second drive or a USB stick if available): shows progress, verifies, deletes the original only after verification; a simulated failure (disconnect or full disk) leaves the original intact.
7. Moving a file that is currently playing in a tile succeeds (the handle is released first). A file locked by another program fails safely with a clear message.
8. A destination folder that has been deleted or is offline shows a warning and cannot be used; the app never recreates it silently.
9. Sidebar: right-click a file in the sidebar, Move to > destination, and it moves (and any open tile for it is handled correctly).
10. Move log and "Recent moves" list show accurate entries; Undo from the list works.

### 2.12 GPU acceleration, fast media switching, autoplay, volume (R14)
**A. Use the GPU everywhere it matters**
- **Decode:** hardware decoding on by default (`hwdec`; prefer Direct3D 11 (`d3d11va`) and allow NVIDIA `nvdec` where available; verify option names against the bundled mpv). Prefer the zero-copy path where decoded frames stay in GPU memory; the "-copy" variants of hardware decoding copy frames back to system memory and are slower, so use them only as a fallback. Fall back to software decode only if hardware decode fails, and show the "SW decode" badge from section 2.2 when it happens.
- **Render:** use mpv's GPU renderer on Direct3D 11 (check whether `vo=gpu` or `vo=gpu-next` with `gpu-api=d3d11` is the right choice for the bundled mpv; test both and keep the one that is more stable and faster with many tiles). Scaling, zoom, and pan (section 2.9) must run on the GPU, not the CPU.
- **UI:** the interface (sidebar, thumbnails, overlays, tile layout) should be drawn by a GPU-accelerated renderer, not a software one. Report what the upstream toolkit does today and whether it is GPU-backed; if it is not, tell me before changing it.
- **Diagnostics (hidden toggle, `F3`):** show GPU name, driver version, renderer in use, per-tile hardware-decode status (`hwdec-current`), dropped frames, and the latest switch-latency measurement. This is how we prove the GPU is being used. Task Manager's GPU "Video Decode" and "3D" graphs are the independent check.
- Report honestly if the machine's GPU lacks hardware HEVC decode, or if the number of simultaneous hardware decode streams is limited (measure; see section 4).

**B. Very fast media switching**
- **Reuse, don't recreate:** each tile keeps one long-lived player instance and loads new files into it (a "load file" command), rather than destroying and rebuilding a player each time. Creating players is the slow part.
- **Preload the next item:** for any tile that has a queue (section 2.13) and for the focused tile, open the next file in the background (decode the first frame, paused, not shown) so switching is close to instant. Also preload the previous item for the focused tile. Cap preloading (setting "Preload items", default 2 total across the app) to protect memory and decoders.
- **No black flash:** when switching, keep showing the old frame until the new item's first frame is ready, then swap. No empty black tile between items.
- **Never block the UI thread:** opening, probing, and thumbnail work happen on background threads. A slow network drive or a huge file must not freeze the app.
- **Thumbnail cache** (section 2.7) makes browsing instant; double-click on a thumbnail should start the file immediately.
- **Instrument it:** log the time from the user action (key press, double-click, or the previous item ending) to the first rendered frame. Report median and 95th percentile for: 1080p H.264, 1080p HEVC, 4K HEVC, an animated GIF, a 20 MP JPG, each from a local SSD, once with preloading and once cold. **Targets to test against, not guarantees:** under about 150 ms median for a preloaded item and under about 500 ms for a cold 4K HEVC item on my machine. If a target is missed, report the number and the bottleneck instead of hiding it.

**C. Autoplay**
- Setting "Autoplay on add", **default on**: a new tile starts playing as soon as its first frame is ready, with a small loading indicator until then. Images simply display. Setting off: tiles load paused on the first frame.
- Setting "Audio on autoplay": **First tile only (default)**, All tiles, or None (muted). With many tiles autoplaying at once, all-audible is chaotic, so the default plays sound from the first tile only; the rest start muted until I unmute them (master and per-tile volume from section 2.5 still apply). Tell me if you think a different default is better.
- Autoplay applies to files added by drag and drop, from the sidebar, from "Play folder in a tile", and when a tile advances in Next mode.

**D. Volume**
- Master volume/mute, per-tile volume/mute, and the hotkeys from section 2.5 stay exactly as specified. Volume changes must be instant with no clicks, pops, or audio dropouts, including while tiles are switching media. Volume levels carry over when a tile advances to its next file.

**E. Acceptance**
1. The diagnostics overlay and Task Manager both show hardware decode active and GPU rendering for HEVC and H.264; the badge shows "SW decode" only when hardware decode genuinely fails.
2. Switching between files in a tile shows no black frame; the switch-latency table is produced and meets or honestly reports against the targets above.
3. Rapidly pressing Next 20 times in a row (hold the key) does not freeze, crash, leak memory, or leave the wrong file showing; the final state matches the last request.
4. Drop 9 files: all autoplay; with the default setting, only the first has audio.
5. Adding a file from a slow source (network drive, if available) does not block the UI.
6. Volume changes during a switch do not cause audio glitches.

### 2.13 End-of-media behavior: Loop or Next (R15)
**Queue concept.** A tile always has a **queue**: the ordered list of files it can advance through.
- If the tile was created with "Play folder in a tile" (section 2.7), its queue is that folder's media in the sidebar's current sort order and filters.
- Otherwise (a single file added by drag and drop), its queue is **implicit**: the other media files in the same folder as that file, in the sidebar's current sort order and filters. The user never has to build a playlist.
- Setting "At end of queue": **Wrap to start** (default) or **Stop**.
- Optional per-tile Shuffle toggle (default off) that randomizes the queue order. Lowest priority; build only after everything else works.

**Modes (per tile, with a global default).**
| Mode | Behavior |
|---|---|
| **Loop** | Repeat the current item. Videos restart at the end; GIFs keep looping; images stay on screen. |
| **Next** | When the current item ends, advance to the next file in the queue and autoplay it. |
| **Stop** | Hold the last frame (videos) and wait. Optional but cheap. |
- A single mode button on each tile's hover bar cycles Loop / Next / Stop with a clear icon and tooltip. A top-bar control sets the mode for **all** tiles at once; a tile's own setting overrides it afterwards. Settings: global default mode (default **Loop**) and remember each tile's mode in the session file.
- **Images and GIFs** never "end" naturally, so Next mode advances them after a display time: setting "Still/GIF display time" (default 5 s, range 1 to 60 s). For a GIF, play whole cycles until at least that time has passed (so very short GIFs do not flicker through), then advance.
- **Manual navigation:** `PageDown` or `N` = next file, `PageUp` or `P` = previous file on the hovered tile, plus previous/next buttons on the hover bar. In Next mode, going past the last file wraps or stops per the setting above. Switching manually uses the same preloading as automatic advance (section 2.12B).
- **Seamless transition:** when a video ends in Next mode, the next item should already be preloaded so the change shows no black frame. Measure and report the gap between the last frame of one item and the first frame of the next (target: under about 200 ms; report if missed).
- **Sorting workflow:** when a tile has a queue and I move (section 2.11), delete (section 2.10), or remove its current file, setting "After move/delete in a queue": **advance to the next file** (default on for tiles in Next mode) instead of closing the tile. This lets me tab through a folder, press Ctrl+1 to sort each file, and have the next file appear automatically. If the queue is empty, the tile closes.
- Loop mode and a queue interact simply: Loop repeats the current item and ignores the queue until I press Next manually.
- Mode, queue position, and the "Play folder" source are saved in the session so a restart restores them.

**Acceptance**
1. A tile in Loop mode repeats a 10 s video indefinitely with no visible gap larger than about 100 ms and no memory growth over 30 minutes.
2. A tile in Next mode with a folder of 5 mixed files (2 videos, 1 GIF, 2 images) plays through them in the sidebar's sort order, advancing videos at their end and GIFs/images after the display time, then wraps to the start.
3. The top-bar mode control changes all tiles; a per-tile override then holds when the global control is changed again only if I set it afterward (state clearly in the UI which tiles are overridden).
4. `PageDown`/`PageUp` (and `N`/`P`) move through the queue on the hovered tile; holding the key 20 times does not break anything.
5. In Next mode, press `Ctrl+1` on the current file: it moves to destination 1 and the tile shows the next file automatically; `Ctrl+Z` brings back the moved file and shows it again.
6. Changing the sidebar sort order changes the next-file order for implicit queues, and the change takes effect without restarting playback of the current file.
7. Volume, zoom (reset on a new file, per section 2.9), and autoplay audio rules carry over correctly when a tile advances.

---

### 2.14 Layout, footer, and styling (R18, R19)
Reference: the published HTML mockup ("Video Wall Mockup"). Match its structure and behavior; it is a design reference, not code to ship.

- **Three columns plus a footer:** left **Library** (collapsible), center **video wall**, right panel (collapsible), and one **footer** bar spanning the bottom. Both side panels open and close without a gap and without video stutter (section 2.7).
- **Both side panels are collapsible.** Three ways to do it: the footer toggle buttons, a small chevron tab on each inner edge of the wall (faint until hovered, pointing the way the panel will move), and hotkeys `Ctrl+B` (library) and `Ctrl+I` (details panel). Collapsing gives the freed width to the wall with no gap, black bar, or video stutter, and the layout animates briefly (instant if reduced motion is on). Collapsed or open state, and each panel's width, persist across restarts. Panels can be resized by dragging the divider between panel and wall (library 240 to 480 px, right panel 240 to 400 px, double-click the divider to reset). Keyboard and focus must never be trapped in a collapsed panel (collapsed panels are removed from the tab order). Optional setting: "Hide panels in full screen" (default on); entering full screen collapses both, leaving restores them.
- **The footer holds the main controls** (nothing lives in a header): panel toggles (library on the left, details on the right), master volume with master mute and level readout (section 2.5), the global "when a clip ends" switch (Loop / Next, section 2.13), and the window buttons (Maximize, Full screen, section 2.6). Changing the global end behavior sets all tiles; a tile can still override it.
- **Right panel, top to bottom:**
  1. **Details** for the current file. "Current" means the hovered tile; when the mouse leaves the wall, the last viewed tile; or the file selected in the library. Show which source is active. Fields: preview, name, resolution, duration (video/GIF), size, date modified, format/codec, frame rate (video/GIF), audio (video), decode path (hardware or software), location.
  2. **Details actions:** Remove from wall (or Add to wall if not open), Delete file, Show in Explorer, each with its hotkey shown on the button (`Del`, `Shift+Delete`, `Ctrl+E`).
  3. **Send to** (section 2.11): Move/Copy toggle, a line naming the current file, the pinned destination list with Ctrl+1..9 hotkey badges, a "Pin a folder" button, and the "After moving, show the next file" option.
  4. **Hotkeys** reference list (from the table in section 7).
  5. **Recent moves** log (last few).
- **Delete from the Details panel** follows section 2.10 B: Recycle Bin only, confirmation showing file name, path, and size, default button Cancel. The mockup shows an in-app undo toast after delete; in the real app, Ctrl+Z cannot restore from the Recycle Bin unless you implement an explicit restore, so say which you chose in `PROGRESS.md`. Keep the Delete button visible but disabled, with a tooltip, when "Enable delete-from-disk commands" is off.
- **Visual language (Apple-like, Swiss minimal, dark):** one sans-serif typeface (Inter or the system UI font; tabular numerals for times and sizes), a clear size hierarchy, left-aligned text, a consistent 4/8 px spacing grid, hairline dividers instead of boxes and borders, soft translucent fills for buttons and fields (no outlines), 8 to 12 px corner radii, and segmented controls and pill filters in the Apple style. Overlays that float over video (hover controls, menus, dialogs, toasts, the footer) are translucent with background blur. Selected rows in menus and lists fill with the accent color. Use thin 1.5 px line icons. If the UI toolkit cannot do background blur cheaply, fall back to a solid dark gray rather than hurting video performance.
- **No labels on the video itself:** do not draw permanent badges or captions (file type, HW, resolution, file name) on tiles. Tiles show only the picture. The file name and controls appear in the hover bars, and everything else lives in the Details panel and the F3 overlay. The only exception is a small "Enhanced" tag in the hover bar when Enhance is on.
- **Look:** a single **dark theme** (no light theme): near-black background, slightly lighter panels, light text, muted gray secondary text. **One accent color, blue** (about #4C8DFF; tune for contrast), used only for selection, the active tile outline, active toggles, progress fill, and focus rings. **No yellow or orange anywhere.** Red is used only for destructive actions (close-hover, delete). Selected items use a blue outline or a soft blue tint with a blue edge bar.
- **Accessibility:** text and controls meet WCAG AA contrast on the dark background; every control is reachable by keyboard with a visible focus ring; icon buttons have tooltips; respect the OS reduced-motion setting for fades.
- **Acceptance:** side-by-side screenshots against the mockup show the same layout and states (empty wall, 4 tiles, selected file, context menu, delete confirmation); no control lives in a header; the accent color appears only in the listed places; the Details panel updates within one frame of hovering a different tile.

### 2.15 Context menus and drag to wall (R17)
- **Drag from the library to the wall:** files in the library (Grid and List) are draggable. While dragging over the wall, show a dashed blue "Drop to add to the wall" overlay. Dropping adds the file as a new tile (autoplay per section 2.12). Dropping an already-open file shows a toast instead of duplicating it. This is in addition to dragging from Windows Explorer (section 2.1) and to double-click.
- **Close a tile:** an X in the top-right of the tile's top bar (visible on hover), plus `Delete`/`Backspace` (section 2.10). Closing is undoable.
- **Tile context menu (right-click a tile):** a caption with the file name, then: Play/Pause (not for images), Previous file, Next file, Mute/Unmute (videos), "When it ends" choices (Loop, Next file, Stop) with the current one marked, Reset zoom (disabled at fit), **Move to** (submenu of pinned destinations with Ctrl+N hints), **Copy to** (submenu with Ctrl+Shift+N hints), Show in Explorer, Copy path, Close tile, and Delete file (red, last). Submenus flip to the left near the right screen edge. The menu closes on Esc, outside click, or window blur, and its hotkey hints match section 7.
- **Library file context menu (right-click a file):** Add to wall (disabled if already open), Move to, Copy to, Show in Explorer, Copy path, Delete file.
- Right-clicking makes that file the "current" file, so Details and Send to act on it.
- Delete file from any menu or the Details panel always opens the confirmation first and follows section 2.10 B.
- **Acceptance:** drag from the library onto the wall adds a tile in Grid and List views; the drop overlay appears and clears correctly (including when the drag is cancelled); right-click opens the correct menu for a tile versus a library file; every menu action works and matches its hotkey; the menu is positioned correctly at all four screen corners.

### 2.16 Enhance: real-time upscaling and sharpening (R21)
Target machine: Windows PC with an **NVIDIA RTX 5070 Ti**. Method chosen: **mpv GPU shaders** (no extra install, runs inside the render path, works per tile). Do not build a second method.

- **What it does:** when Enhance is on for a tile, the video or image is upscaled with a RAVU-family shader (use the `ravu-lite` variant from the community mpv-prescalers set; verify the exact file names, current version, and license in that repo before bundling) on top of mpv's `ewa_lanczos` scaler, with an optional light sharpen (CAS or adaptive-sharpen shader, off unless the user turns Sharpen on). RAVU was chosen over the anime-oriented shaders because the footage is mostly live-action and renders; one guide I found says anime CNN shaders (Anime4K, ArtCNN) suit animation and that for live-action RAVU or plain `ewa_lanczos` is the safer choice. Verify on real footage.
- **Controls:** `E` toggles Enhance on the current tile (see the "which tile" rule in 2.3); "Enhance" in the tile context menu (section 2.15); a small "ENHANCED" badge on the tile. A setting chooses presets: **Off**, **Standard** (shader upscale only), **Sharp** (upscale plus light sharpen). Default: Off. Setting "Enhance focused tile automatically" (default off).
- **Only when it matters:** upscaling only has an effect when the picture is drawn larger than its source. In a small grid tile it usually will not be. In the diagnostics overlay (F3), show per tile whether Enhance is active and whether it is actually upscaling or idle, so the user is not misled. Do not run shaders on tiles that are drawing at or below source size.
- **Implementation notes (verify, do not assume):** shaders are loaded through mpv's `glsl-shaders` option, ideally changed at runtime per mpv instance without reloading the file. Confirm this works with the repo's embedding and render path (`gpu-next` is often needed for newer shaders; test `gpu` and `gpu-next`). Hardware decode must stay on. GIFs are excluded.
- **Cost rule:** measure GPU time and dropped frames with Enhance on for 1, 4, and 9 tiles of 1080p and 4K HEVC on the 5070 Ti and record the results in `PROGRESS.md`. If Enhance on one 4K tile in focus mode drops frames, say so and propose a lighter preset instead of silently degrading. Limit Enhance to at most N tiles at once (default 2) and show a toast when the limit is reached.
- **Out of scope for now:** Nvidia RTX Video Super Resolution. Public reports list support only in Chrome, Edge, and VLC, and I found nothing confirming it works inside an mpv-based app. If wanted later, run it as a separate time-boxed test, not part of this build.
- **Acceptance:** toggling Enhance applies within about 200 ms with no black frame; visual before/after on a 720p and a 1080p clip shown full screen on a 4K display; badge and F3 report match what is happening; hardware decode graph still active; frame rate stays acceptable in the cost test; Off truly bypasses the shaders (no GPU cost).

## 4. Phase 3: Performance and robustness (R10)

1. **Hardware decode budget:** hardware decoders have a limit on concurrent streams that depends on the GPU. Find the point where it degrades on my machine (e.g. 1080p HEVC: 4, 6, 9, 12, 16 tiles) and record the numbers in `PROGRESS.md`. Do not guess; measure.
2. **Guardrails:** setting "Max simultaneously playing tiles" (default auto-detected from the measurement above). Extra tiles start paused with a visible "paused (limit)" state, never crash.
3. **Offscreen / hidden tiles:** pause video rendering for tiles that are not visible (minimized window, covered by focus mode).
4. **Lower-cost mode for many tiles:** optionally decode large files at reduced resolution when the tile is small (only if mpv/upstream supports it cleanly; otherwise skip and note).
5. **Error handling:** a failed tile shows an inline error with a Retry and Remove button. Log errors to `%LOCALAPPDATA%\<AppName>\logs\app.log` (rotated, max about 5 MB). A "Copy diagnostics" menu item copies GPU, driver, mpv version, and recent errors to the clipboard.
6. **Resource cleanup:** removing a tile or closing the app must terminate its mpv instance and free memory; run a 30-minute soak test with 9 tiles looping and confirm memory stays flat.
7. **Startup time:** cold start to usable window under about 2 seconds on my machine; report the actual number.

---

## 5. Phase 4: Packaging and docs (R9)

1. Build a **release** binary. Produce `dist/<AppName>-portable.zip` containing the exe, the required mpv/FFmpeg DLLs (match what upstream's portable release ships), `LICENSE`, `NOTICE.md`, and a `README.txt` with a 10-line quick start and hotkey table.
2. Verify the zip runs on a **clean** Windows user profile (no dev tools installed). If I have no second machine, use Windows Sandbox if available and tell me what you tested.
3. Check whether the app needs the Microsoft HEVC Video Extensions to play HEVC. My expectation is that it does not (mpv decodes through FFmpeg and talks to the GPU directly), but this is an inference. Test it and record the result.
4. Add a `README.md` for developers: how to build, how to run, project layout, how to add a feature.
5. Create a `LICENSES.md` listing every bundled library and its license. Because the base is GPL-3.0, the combined app is GPL-3.0. This is fine for internal use. Note in the README that commercial distribution would require a different approach (an LGPL build of libmpv and legal review of HEVC patent royalties) and should not be attempted without that review.
6. Optional: an installer (e.g. Inno Setup or WiX) only if I ask.

---

## 6. Final QA checklist (run before calling it done)

- [ ] Fresh clone builds from the README instructions alone
- [ ] Drop: 1 file, 6 files, folder of 20, mixed media, junk file, corrupt file
- [ ] HEVC 4K and 1080p play with hardware decode (GPU "Video Decode" graph confirms)
- [ ] H.264, VP9, GIF (loop), JPG/PNG/WebP all work
- [ ] Fit: landscape, portrait, square, and rotated files all show the full frame with the longest side touching the tile edge; nothing is cropped or stretched
- [ ] Hover controls on every tile type; no flicker; no interference with window drag
- [ ] GIFs: correct timing, loop, pause; large GIF does not freeze UI; transparent GIF/PNG renders correctly
- [ ] GPU: hardware decode and GPU rendering confirmed by the F3 overlay and Task Manager; switch-latency table produced; no black frames when switching; rapid Next presses are stable
- [ ] Autoplay works (default on); audio on autoplay follows the setting; volume changes are glitch-free
- [ ] Loop and Next modes work per tile and globally; images/GIFs advance after the display time; wrap/stop at queue end; Next-after-move advances the tile
- [ ] Sidebar: folder tree, Grid and List views, all sort options, "recently modified", filters, search, live updates, thumbnail cache; 5,000-file folder stays smooth
- [ ] No speed controls, frame-step, or other advanced-player menus exist anywhere in the UI
- [ ] Images: EXIF rotation correct, 8000x6000 image smooth, HEIC/AVIF support reported honestly (works or documented as unsupported)
- [ ] Remove: X button, Delete key, context menu, multi-select, Clear all, toast Undo, Ctrl+Z / redo, memory freed
- [ ] Send to folder: destinations persist; move via hover button, Ctrl+1..9, right-click, and sidebar; copy via Ctrl+Shift+1..9; undo works; name collisions never overwrite silently; cross-drive move verifies before deleting; playing/locked files handled; every move logged
- [ ] Delete-from-disk is off by default; when on, goes to Recycle Bin only, always confirms, logs, and handles locked files
- [ ] Zoom/pan/scrub on the hovered tile: wheel zooms toward cursor; middle-drag and Shift+arrows pan, clamped, per-tile; left-drag scrubs with natural direction (drag left = forward) and a click toggles play/pause; GIFs and images ignore left-drag; reset works; wheel ignored over controls; hardware decode still active while zoomed
- [ ] Master volume/mute plus per-tile volume combine correctly; solo-audio option works
- [ ] Normal (all edges resize), maximize/restore, and full screen all work; transitions are clean; Esc/F10/F11 behave; no borderless mode exists
- [ ] Enhance (if built): E and the context menu toggle it per tile; Off costs nothing; F3 shows whether it is actually upscaling; the 1/4/9-tile cost results are recorded
- [ ] Single-video use: with one file the window shows one full-size tile; "Open one file at a time" replaces instead of adding; Next/Previous (PageDown/N, PageUp/P) work with the mouse outside the window and with one tile, and wrap per section 2.13
- [ ] Sidebar opens/closes with no gap and no video stutter; add via double-click and via drag from the library onto the wall
- [ ] Both panels collapse and expand by footer button, edge chevron, and Ctrl+B / Ctrl+I; width and state persist; no gap or stutter; collapsed panels are not focusable
- [ ] No permanent labels or badges on tiles (names and controls only on hover); look matches the mockup's Apple-like Swiss dark style
- [ ] Layout matches the mockup: footer holds the main controls; right panel shows Details, Send to, Hotkeys, Recent moves; dark theme with a single blue accent and no yellow
- [ ] Right-click menus (tile and library file) work, including Move to / Copy to submenus; Details panel Delete and Remove buttons work and show their hotkeys
- [ ] Session restore and playlist save/load work; corrupt settings recover
- [ ] 30-minute soak with 9 tiles: no crash, memory flat
- [ ] Portable zip runs on a clean profile
- [ ] `PROGRESS.md`, `ARCHITECTURE.md`, `NOTICE.md`, `LICENSES.md`, `README.md` are current

---

## 7. Hotkey reference (target)

| Key | Action |
|---|---|
| Drag file/folder onto window | Add tiles |
| Space | Play/pause hovered tile |
| Left / Right | Seek 5 s on hovered tile |
| Up / Down | Per-tile volume |
| M | Mute hovered tile |
| Ctrl+Up / Ctrl+Down | Master volume |
| Ctrl+M | Master mute |
| Ctrl+Shift+M | Mute all except focused tile |
| Double-click tile | Focus / unfocus tile |
| Mouse wheel over video | Zoom hovered tile toward cursor |
| Middle-drag on zoomed tile | Pan |
| Left-drag on a video (drag left = forward) | Scrub |
| Horizontal trackpad swipe on a video | Scrub |
| Click on video (no drag) | Play/pause |
| Right-click tile or library file | Context menu |
| Drag file from library onto wall | Add as a tile |
| Shift + arrow keys | Pan hovered tile when zoomed |
| + / - | Zoom hovered tile in / out |
| 0 | Reset zoom and pan (fit) |
| 1 | Jump to 100% native size (if implemented) |
| Delete / Backspace | Remove hovered or selected tile(s) from the grid (undoable) |
| Ctrl+Z / Ctrl+Shift+Z | Undo / redo tile removal |
| Ctrl+click / Shift+click / Ctrl+A | Multi-select tiles |
| Ctrl+Shift+Delete | Clear all tiles (confirms if more than 3; undoable) |
| Shift+Delete | Delete file to Recycle Bin (only if enabled in settings; always confirms) |
| Ctrl+1 ... Ctrl+9 | Move hovered/selected file(s) to destination 1 to 9 |
| Ctrl+Shift+1 ... Ctrl+Shift+9 | Copy hovered/selected file(s) to destination 1 to 9 |
| PageDown / N | Next file in the current tile's queue (works without hovering; with one tile it acts on that tile) |
| PageUp / P | Previous file in the current tile's queue (same rule) |
| Mouse back / forward buttons (optional) | Previous / next file |
| E | Toggle Enhance on the current tile |
| Ctrl+Shift+G / Ctrl+Shift+L | Sidebar Grid view / List view |
| F3 | Toggle diagnostics overlay (GPU, hwdec, latency) |
| Left / Right (focused image tile) | Previous / next image in the folder |
| Ctrl+B | Toggle library sidebar |
| Ctrl+I | Toggle details panel |
| F10 | Maximize / restore |
| Ctrl+E | Show current file in Explorer |
| F11 | Toggle full screen |
| Ctrl+T | Always on top |
| T | Tags for the current file (R22) |
| Ctrl+P | Add current/selected file(s) to a playlist (R22) |
| Esc | Exit full screen or focus mode |

---

## 8. Reporting format

After each phase, reply to me with:
1. What you did (3 to 5 lines)
2. Test results (pass/fail table)
3. Anything unverified or surprising
4. The next step you propose, and whether you need my decision

Start now with Phase 1. Do not write feature code until the Phase 1.5 report is delivered and I have approved it.
