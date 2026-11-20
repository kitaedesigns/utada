# Progress

## Status: Phase 2.2 done (2026-11-20). Next: 2.3 tile layout (fit instead of crop, auto grid, single-video use, focus mode).

## Phase 2.2: media handling (R2, R3), done 2026-11-20
**What changed**
- **Hardware decoding for every video by default** (`gpu-copy`, which is `d3d11va-copy` on Windows; budget 6000 Mpx/s). MosaicPlayer's default decoded videos up to 1080p30 on the CPU, a choice made for 100+ tiles. Saved settings still at the old defaults move over once (config v3); a decoder you chose yourself is kept.
- Each tile logs its decode path when it changes ("decoding with d3d11va-copy" / "CPU").
- **Software fallback is never silent:** if a video asked for the GPU but decodes on the CPU, a notice says so once, the log records it, and the hover bar says "SW decode".
- **No badges on the picture:** plan 2.2 asks for a type badge and an "SW decode" badge on tiles, but plan 2.14 (later and more specific) forbids permanent labels. So type, resolution, file size, time and decode path show in the hover bar, e.g. "hevc_1080_60  VIDEO  1920×1080  35.0 MB  0:02 / 1:00  GPU decode".
- **GIFs and stills never take a GPU decoder** (GIF has none).
- **Animated WebP/AVIF** are detected from mpv's track info and behave like GIFs (they play, pause and loop; labelled "ANIM").
- **Stills:** no timeline and no pause.
- **Left/Right on a GIF or image tile** flips through the folder's GIFs and images, in natural order and wrapping. Files shown in other tiles are skipped unless duplicates are allowed. The plan lists this for focused image tiles; it is on for every GIF and image tile, since neither has anything to seek.
- **Transparency:** dark by default; setting "Transparent GIFs and images: show the background / a checkerboard", applied live. mpv 0.41's own default is the checkerboard.
- **"Loading…"** shows in a tile until its first frame.
- **Files without audio** are detected; the speaker icon is hidden for them and the hover bar says "no audio".
- **UI freeze fixed:** adding videos froze the UI for 50–230 ms per video, because the decoder policy asked mpv for the frame rate synchronously while mpv was busy opening the file. It now uses the frame rate mpv reports by itself, and changes the decoder asynchronously. Adding 6 files now stalls the UI by at most about 50–80 ms (creating six players).

**Measured in the real app with every file in `testmedia/`**
| Check | Result |
|---|---|
| Every video on hardware decode: H.264 1080p, H.264 4K MKV, HEVC 1080p60 / 4K30 / 10-bit, VP9, portrait | Pass: all `d3d11va-copy`, no software fallback |
| Windows' Video Decode engine (Task Manager's graph) with 3 HEVC tiles | 18% (it moves) |
| GIF variable frame delays (10 × 100 ms, then 10 × 500 ms) | Pass: median 99 ms and 504 ms |
| GIFs loop; GIF loop count | Loop: pass. A GIF's own loop count (e.g. `anim_once.gif`) is not honoured: mpv's GIF reader ignores it, so GIFs loop until the end-of-media mode says otherwise (2.13) |
| 68 MB GIF | First frame in 0.3–0.5 s; UI stall at most 79 ms; no conversion fallback needed |
| 8000×6000 JPG | First frame in 0.4 s; UI stall at most 77 ms |
| Stills stay up (8 s), EXIF photo upright, HEIC, AVIF, BMP, TIFF, WebP, PNG | Pass |
| Transparent PNG and GIF, dark and checkerboard | Pass |
| Corrupt file | Error tile, no crash |
| File without audio | Detected |

**Test media fixed again:** `transparent.png` was fully transparent (FFmpeg's `drawbox` left alpha at 0), so it tested nothing. It now has a 70%-opaque box.

**Not done here:** loading a GIF through an FFmpeg conversion when the engine can't play it. Every test GIF plays correctly, so there was nothing to fall back from.

**Noted for later:** some UI-thread calls still ask mpv for values synchronously: switching files (2.12) and the hover bar's time readout. They are fast in the tests, but 2.12's switching work will move them off the UI thread.

**Suite:** pyflakes clean; unit 100 passed, 2 skipped, plus the 2 speed-sensitive layout tests; GUI 34 passed (7 new). The unit suite adds step-in-folder, animated-image and settings-migration tests.

## Phase 2.1: drag and drop and the media list (R1), done 2026-11-20
**What changed**
- **Media items:** each tile's `Entry` is the media item: a session `id`, absolute `path`, `kind` (video / gif / image, from the extension), volume, muted, end-of-media action (on the tile), and position = its place in `Canvas.tiles`, the single ordered list the wall draws from.
- **Accepted:** videos, GIFs and images (JPG, PNG, WebP, BMP, TIFF, HEIC/HEIF, AVIF), folders and playlists. Images stay on screen (`image-display-duration=inf`) and never take a GPU decoder slot.
- **Folders:** one level by default, natural name order; setting "Dropped folders include their subfolders" (off). File > "Add folder (with subfolders)" still includes them, as its name says.
- **Order:** a multi-file drop is sorted by name. Explorer lists a selection starting with the file you grabbed, so drop order alone isn't predictable.
- **Duplicates:** a file already on the wall is not added again, with a notice. Setting "Allow the same file on the wall more than once" (off). Paths are compared case-insensitively on Windows.
- **Rejected with one notice (no dialog), grouped by reason:** not a video, GIF or image; not found; web addresses; folders with no media; files that didn't fit. A file that has the right extension but won't play becomes an error tile ("cannot play this file"); nothing crashes.
- **6-tile wall:** files beyond the room left are not added, and the notice names them. On a full wall, one file dropped on a tile replaces that tile; dropped anywhere else (or opened with Ctrl+O or the command line), a banner asks you to click the tile to replace (Esc or right-click cancels). Replacing reuses the tile's player, keeps its volume and mute, and resets zoom. The "add it to that tile's queue" option comes with queues in 2.13.
- **Drop zone:** while dragging, a dashed blue overlay says "Drop to add to the wall (room for N more)". On a full wall, the tile under the cursor is outlined: "Replace 'name'".
- **Empty wall:** "Drag videos here" with a short line on what's accepted.
- **Network removed (plan rule 7):** the update check, File > Open URL and yt-dlp are gone; web addresses in playlists or drops are skipped.
- **Removed:** the "more than 64 videos" question, which the 6-tile cap replaces. `--no-confirm` is kept as a no-op for old scripts.
- **Playlists:** a playlist only becomes the Ctrl+S target if all of it made it onto the wall, so saving can't overwrite an 8-video playlist with the 6 shown.

**Bug found and fixed:** photos with EXIF rotation and phone videos with a rotation tag got a tile of their unrotated shape. With the default crop, a rotated landscape photo was cut to a portrait strip. mpv reports the shape before rotation; tiles now use the shape as shown. The Phase 1 test photo hid this: its pixels held upright text, so a correct viewer shows it sideways. `make_testmedia.sh` now stores the pixels turned, so correct display is upright, landscape text.

**Acceptance (plan 2.1), tested in the real app and in GUI tests (`tests/test_app_smoke.py`)**
| Test | Result |
|---|---|
| Drop 1 file | Pass |
| Drop 6 files | Pass |
| Drop a folder of 20 | Pass: first 6 by name; the notice names the other 14 |
| Drop video + GIF + JPG + txt | Pass: 3 tiles, `.txt` named in the notice |
| Order stable | Pass: sorted by name |
| No crash on corrupt / non-media files | Pass: error tile for each |
| Drop overlay appears, and clears on drop and on drag cancel | Pass |
| Empty-state hint | Pass |
| Duplicates off by default; setting allows them | Pass |
| 7th file: replace the tile it's dropped on, or pick a tile; Esc cancels | Pass |
| Real test media: 4K HEVC (`d3d11va-copy`), variable-delay GIF, HEIC, 8000×6000 JPG, EXIF photo upright | Pass. The big JPG adds without blocking the UI |

**Not verified by me:** a drag from Windows Explorer with the real mouse. The tests send Qt's drop events directly, which is what Qt builds from an Explorer drop, but the Explorer-to-Qt step itself was not exercised.

**Suite:** pyflakes clean; unit 97 passed, 2 skipped, plus the 2 speed-sensitive layout tests; GUI 27 passed. That includes 9 new tests and 3 new unit tests.

## Phase 2 groundwork (2026-11-20)
- MosaicPlayer's history merged into this repo at `004dd93` (remote `upstream`); `NOTICE.md` added; the project is GPL-3.0-or-later.
- `tools/dev.ps1 setup | run | test` (venv with Python 3.12, app + dev dependencies) and `tools/get_libmpv.ps1` (pinned libmpv 20261019, SHA-256 checked, into `vendor/`, git-ignored).
- **Two Windows bugs fixed** in `mosaicplayer/playlist.py`: `file:///C:/...` URIs (VLC .m3u files, dropped URIs) became `/C:/...`; reading a Latin-1 .m3u crashed (`os.fsdecode` raises on Windows).
- **Test suite green on Windows** (was 86 passed / 11 failed / 21 GUI tests skipped): 114 passed, 2 skipped (POSIX-only: signals; permission bits and symlinks), 2 marked speed-sensitive (100+ tile layout time budgets; non-strict xfail). Tests now use platform paths; GUI tests run on Windows; pytest's faulthandler is off on Windows (it crashed the test process while reporting LuaJIT's handled exceptions inside libmpv). `dev.ps1 test` runs lint, unit and GUI tests in separate processes, like upstream CI.

## Environment (Windows PC, measured 2026-11-19/20)
| Item | Value |
|---|---|
| OS | Windows 10 Home 22H2 (19045) |
| GPU | NVIDIA GeForce RTX 5070 Ti, 16 GB, PCIe 4.0 x16. Driver 610.88 (Windows 32.0.16.1088, 2026-07-21) |
| Display | 3440 × 1440 at 144 Hz (single monitor; Parsec/Virtual Desktop/Meta virtual adapters also installed) |
| CPU / RAM | AMD Threadripper 3960X, 24 cores / 48 threads; 128 GB |
| Toolchain | Rust 1.90 MSVC (your default toolchain stays GNU; builds select MSVC per command), VS 2022 Community + MSVC 14.44, **Windows SDK 10.0.26100 (installed this session)**, Python 3.12, FFmpeg 8.1.2 (Gyan full), **ExifTool 13.64 (installed)**, Git 2.49 |
| Engines | MultipleVideoPlayer: shinchiro libmpv 20261106. MosaicPlayer: shinchiro libmpv 20261019. Both SHA-256 verified. |

Installed only after your OK: Windows SDK (VS Installer), ExifTool (winget). Everything else is local to `D:\Github\utada-candidates\` (candidate clones, a venv for MosaicPlayer, a tools venv with pillow-heif and py7zr, the official standalone `7zr.exe`).

## Done
- Test media regenerated on Windows (`tools/make_testmedia.sh`, Git Bash). Script fixes: explicit font for FFmpeg `drawtext` on Windows (it segfaults otherwise); HEIC via pillow-heif when `heif-enc` is missing; two stream-copied long clips (60 s 10-bit HEVC, 10 min 1080p60 HEVC). EXIF orientation 6 written with ExifTool. **All files generated, including HEIC.**
- MultipleVideoPlayer built from unmodified source with MSVC (49 s); 13/13 Rust unit tests pass.
- MosaicPlayer run from source; Windows test run: 86 passed, 11 failed, 21 skipped (see below). Its **published portable zip does not exist**: the README's "latest release" link leads to an empty releases page (the release workflow only makes drafts). I built the same zip locally with its release workflow steps (PyInstaller, pinned libmpv): 98 MB, runs, hardware decode active.
- Measurement tools in `tools/bench/` (probe for each app, Windows counter sampler, matrix runner, engine check). MultipleVideoPlayer needed a small measurement-only patch, kept as `tools/bench/mvp-probe.patch` (applied only in the local clone, branch `utada-probe`). MosaicPlayer is measured from a wrapper with no source change. Raw results: `docs/phase1-results/`.

## Build notes
- **MultipleVideoPlayer `build.ps1` fails on Windows 10**: it unpacks `.7z` with `tar`, and Windows 10's tar has no LZMA. Worked around by running its steps with `7zr.exe`. Its own `verify.exe` decoded all 300 frames and matched every seek position exactly, but its pixel comparison failed every frame (likely a harness issue; unresolved).
- **MosaicPlayer tests on Windows**: the 11 failures are tests that assume `/` paths, need symlink privileges, or a layout timing budget (0.48 s vs 0.4 s); 2 folder-expansion tests return nothing on Windows and may be real bugs, but dropping a folder worked live. The 21 GUI tests skip on Windows. CI runs on Linux only.

## How to read the numbers
"Drops" counts mpv's frame-drop + decoder-drop counters per tile over the steady-state window (15 s to run end − 8 s; about 32 s). Because these apps render through the mpv render API, a late frame can also show up as playback running slower than real time, so each tile's **speed** (playback seconds per wall second) and **frames drawn per second** are checked too. "Smooth" = 0 drops, speed 1.00, drawn = source fps. Memory = process private bytes and dedicated GPU memory; Video Decode = the same per-process counter as Task Manager's "Video Decode" graph. Full screen 3440 × 1440, tiles muted. Another app used about 13% of the GPU's 3D engine in the background during all runs (same for both candidates).

## Proceed rule (plan 1.4)
| | MultipleVideoPlayer | MosaicPlayer |
|---|---|---|
| Hardware HEVC decode active | **Yes**: `nvdec` on every tile (CUDA to OpenGL, no copy back) | **Yes**: `d3d11va-copy` for videos above ~1080p30 (copy back, by design); CPU for 1080p30 and smaller |
| **6 × 1080p60 HEVC** (now the maximum) | **Pass**: 0 drops, every tile 1.00× and 60.0 fps drawn | **Pass**: 0 drops, every tile 1.00× and 60.0 fps drawn |
| 9 × 1080p60 HEVC (headroom) | 3 drops in total (≤1 per tile) | 8 drops in total (≤5 per tile) |
| 12 × 1080p60 HEVC (headroom) | 1–13 drops per tile; one tile jumped back 11 s mid-run (likely an accidental click while you answered a question; excluded) | 4 drops in total (9 tiles GPU + 3 CPU by its GPU budget) |
| 6 × 4K30 HEVC | **Pass**: 0 drops | **Pass**: 0 drops (4 tiles GPU + 2 CPU by budget) |
| 6 × 1080p30 10-bit HEVC | **Pass**: 0 drops | **Pass**: 0 drops (CPU decode by design) |

**Both candidates meet the proceed rule.** The question in `ARCHITECTURE.md` is answered: OpenGL rendering does **not** force copy back; MultipleVideoPlayer's `auto-safe` lands on zero-copy `nvdec`. MosaicPlayer's own "GPU zero-copy" mode does **not** work on Windows: with its default `d3d11va` API there is no OpenGL interop, and it silently falls back to CPU decoding (12 tiles: 0% Video Decode, 6.5 cores).

## Resource use at 6 × 1080p60 HEVC
| | MultipleVideoPlayer | MosaicPlayer |
|---|---|---|
| CPU | 0.7 cores (1.3% of machine) | 1.9 cores (4.1%) |
| Private memory / GPU memory | 3.9 GB / 3.0 GB | 1.4 GB / 1.0 GB |
| at 6 × 4K30 HEVC | 8.3 GB / 6.7 GB | 2.6 GB / 2.2 GB |
| GPU Video Decode / 3D | 17% / 39% | 28% / 44% |

## Baseline test matrix (plan 1.4)
P = pass, F = fail/absent, ~ = partial. "src" = from reading source, not running.

| Test | MultipleVideoPlayer | MosaicPlayer |
|---|---|---|
| Drop 1 / 6 files / folder | **~**: files load, but always into the last-hovered cell, not the one under the cursor (`app.rs:1664`; winit 0.30 gives no drop position). You could only fill the left column. | **P** (portable build, by you): 1 file, 5 files at once, GIF, folder |
| HEVC 4K smooth | P (4× and 6×, 0 drops) | P (4× and 6×, 0 drops) |
| Hardware decode active | P (`nvdec`, zero-copy) | P (`d3d11va-copy`) |
| GIF animates and loops | F: refused by its extension filter (the engine plays GIFs correctly) | P: animates and loops; variable frame delays timed correctly (5.61 s vs 5.6 s) |
| Still images | F: refused | ~: JPG and HEIC display when opened from the command line; the drop filter excludes images (`playlist.py:27`, src) |
| HEIC / AVIF / animated WebP | Engine decodes all three (both builds); the app refuses them | Engine decodes all three; the app shows them from the command line, the drop filter excludes them |
| EXIF orientation | Engine: P (rotated to 800 × 1200), both builds | same |
| Removing a tile frees memory | **F**: removing 3 playing tiles freed 82 MB RAM and no GPU memory; each removed player stays alive (~0.6 GB RAM + 0.5 GB VRAM) | **P**: freed 342 MB RAM and 387 MB GPU memory |
| Move/copy/delete feature | F | F |
| Renderer / hwdec path | OpenGL render API, `nvdec` zero-copy | OpenGL render API, `d3d11va-copy` |
| Switch latency (same tile, alternating 1080p H.264/HEVC, the app's own "next"/replace) | **29 ms** median (28–56; first switch 649 ms) | **359 ms** median (47–641) |
| Startup to first video frame | 1.9 s (window at 0.8 s) | 4.5 s from source; about 7.5 s on the first launch of the portable build |
| Autoplay / loop-next / sidebar / thumbnails | P / F (stops on the last frame; AB loop and manual previous/next only) / F / F | P / P (Loop is the default and seamless; Next in folder, Random) / F / F |
| Speed controls to remove | Present (plus frame step, AB, picture adjustments) | Present (speed) |
| Hover controls | src: per-cell control bar | P: title on hover, canvas overlays |
| Zoom / pan / scrub | src: wheel zoom, middle-drag pan, timeline drag | src: Ctrl+wheel zoom |
| Per-tile volume / mute | src: yes | src: yes; Del removes the hovered tile |
| Maximize / full screen / resize | P: full screen, maximize, 800 × 500, 2400 × 1200, no interruption | P: same |
| Corrupt file / non-media | ~: no crash; the .txt is refused with a banner; the corrupt MP4's cell stays black with no message | P: "cannot play this file" tiles, no crash |
| 10-minute memory, 6 × 1080p60 HEVC (windowed) | **P**: flat at 3.90 GB RAM / 2.85 GB GPU from minute 2 to 10; 0 drops, all tiles 1.00× | **~**: stable while playing (1.25 → 1.28 GB RAM, 0.91 GB GPU), but the window was minimized at 1.6 min and the app pauses all videos when minimized (by design), so only 1.6 min of playback was measured. Not re-run, at your call. |
| Interface language | Mostly Traditional Chinese | English |

## Engine checks (Windows libmpv builds, headless)
Both builds give identical results: JPG, PNG, WebP, BMP, TIFF, AVIF, **HEIC** (synthetic single-image file; a real iPhone photo with tile grids is still untested), transparent PNG, 8000 × 6000 JPG, **animated WebP** (works on Windows, unlike Linux FFmpeg 6.1), all GIFs, VP9, 10-bit HEVC. Corrupt MP4 and .txt fail cleanly ("unknown format").

## Requirements changes
- 2026-11-19: **R22 Playlists and tags** added at your request. Spec, interpretation and acceptance tests in `docs/R22-playlists-and-tags.md`. Not built (Phase 1 gate). It replaces the separate "Save/Open playlist" in plan 2.8, so the app has one playlist concept.
- 2026-11-20: **Maximum 6 videos at once.** The wall holds at most 6 tiles (confirmed: a cap on tiles, not only on how many play). Opening a 7th file asks which tile to replace, or adds it to that tile's queue. This is the Phase 3 tile limit that R22's "Open playlist on the wall" respects. The proceed rule's 9- and 12-tile runs are kept as headroom data only; 6 × 4K HEVC is added as the new worst case.

## Decisions made
- Benchmarks run full screen with tiles muted; long runs (10 min) windowed so the PC stays usable.
- Screenshots capture only the test app's own window (`PrintWindow`), never the whole screen.
- MosaicPlayer merged 2026-11-20; `NOTICE.md` added. `LICENSES.md` comes in Phase 4.
- Rendering stays on OpenGL. Plan 2.12A asks for mpv on Direct3D 11 (`gpu-api=d3d11`), but libmpv's render API, which lets the app draw controls over video, only supports OpenGL. Direct3D 11 would mean a native child window per tile and the "airspace" problem (plan 2.4). Hardware decode is unaffected.
- Where the plan says 9 or 12 tiles (layout, hover, zoom and sidebar acceptance, "drop 9 files", the 30-minute soak, the Enhance cost test), use 6, the wall maximum. Plan Phase 3 step 2 ("max simultaneously playing tiles") is covered by the 6-tile cap.

## Plan vs. MosaicPlayer: changes Phase 2 must make
- **Remove (plan rule 7 and the out-of-scope list):** ~~the update check, Open URL and yt-dlp~~ (done in 2.1); "Random positions" and the speed setting.
- **Remove the menu bar:** plan 2.14 puts the main controls in a footer, with nothing in a header.
- **Fit, not crop, by default:** MosaicPlayer crops to fill (`panscan=1.0`); plan 2.3 wants the full frame (`panscan=0`), with crop as an opt-in setting.
- **Settings:** MosaicPlayer stores them with `QSettings`; plan 2.8 wants a versioned `%APPDATA%\<AppName>\settings.json`.
- **Hotkeys that clash with plan section 7:** Space and M act on all videos (the plan: hovered tile); Ctrl+M shows the menu bar (the plan: master mute); T is stay-on-top (the plan: tags; Ctrl+T is stay-on-top); F is a second full-screen key; S and R are random positions and puzzle reshuffle.

## Open questions for you
1. ~~Approve the 1.5 decision~~ Approved 2026-11-20: MosaicPlayer.
2. ~~Paste the full build plan~~ Saved as `docs/BUILD-PLAN.md` (2026-11-20). The mockup it refers to (2.14) is your "Video Wall Mockup" artifact; I'll read it when the layout and hover-bar work starts.
3. Optional: one real iPhone HEIC photo, to confirm tile-grid HEIC decoding.
4. R22: smart (tag-rule) playlists are included, per your instruction.
5. The app's name (for the window title, `%APPDATA%\<AppName>`, installer). Until then the code keeps the `mosaicplayer` package name.
