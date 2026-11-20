# Progress

## Status: Phase 1 (recon) complete on Windows. Waiting for your approval of the 1.5 decision report (`docs/phase1-decision.md`). No feature code until then.

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
- No upstream code copied into this repo yet, so no `NOTICE.md`/`LICENSES.md` yet.

## Open questions for you
1. Approve the 1.5 decision (`docs/phase1-decision.md`).
2. Optional: one real iPhone HEIC photo, to confirm tile-grid HEIC decoding.
3. R22: smart (tag-rule) playlists are included, per your instruction.
