# Progress

## Status: Phase 1 (recon), partially complete. Waiting at the decision gate.

### Blocker
This session runs in a **Linux cloud container (Ubuntu 24.04, 4 CPU, 15 GB RAM, no GPU)**, not on the Windows PC. These Phase 1 steps cannot be done here:
- GPU model and driver (`Get-CimInstance Win32_VideoController`). The plan names an RTX 5070 Ti; unconfirmed.
- MSVC build and run of either app on Windows; hardware decode; Task Manager readings; Explorer drag and drop; multi-tile performance; switch latency.

The **proceed rule** (HEVC with hardware decode + 6 tiles without dropped frames on your machine) **cannot be evaluated yet**.

## Environment (this container)
| Item | Value |
|---|---|
| OS | Ubuntu 24.04.5 (Linux 6.18) |
| GPU | None (software OpenGL via Mesa llvmpipe) |
| Rust | stable toolchain present; `x86_64-pc-windows-gnu` target added |
| FFmpeg | 6.1.1 (Ubuntu) |
| mpv / libmpv | 0.37.0 (Ubuntu) — **not** the build either candidate ships on Windows |
| Python | 3.13 |

## Done
- Cloned both candidates; recorded commits, history, licenses, structure, mpv options → `ARCHITECTURE.md`.
- MultipleVideoPlayer: `cargo check --release --target x86_64-pc-windows-gnu --bins` **passes** (type-check only; not linked with MSVC, not run).
- MosaicPlayer: test suite **117 passed, 1 skipped** under Xvfb with software OpenGL (an earlier run with Qt's `offscreen` platform failed 3 GUI tests for lack of an OpenGL FBO; that was the harness, not the app).
- MosaicPlayer live run (Linux, software decode + software GL): 11 files → 9 playing tiles, `corrupt.mp4` and `notamedia.txt` shown as "cannot play this file" tiles, no crash. HEVC 1080p60 kept real time (frame 803 at 13.38 s). RSS 881 MB, CPU 321%.
- Test media generator `tools/make_testmedia.sh` and the media set in `testmedia/` (git-ignored).

## Test media notes
- All files in plan section 1.3 generated, plus `portrait_1080x1920.mp4`, `loop_10s.mp4`, `still.bmp`, `still.tiff`.
- `anim_large.gif` is 71 MB (first attempt was 590 MB; shortened).
- `anim_transparent.gif`: first version was malformed (box not drawn); fixed and verified.
- **HEIC not generated**: this libheif has no HEVC encoder. Need a real sample from you.
- **Animated WebP does not decode with FFmpeg 6.1** ("image data not found"). Whether the Windows mpv build decodes it is untested.

## Engine checks (Linux mpv 0.37 — indicative only)
| Check | Result |
|---|---|
| EXIF orientation 6 | Handled: mpv inserts `autorotate`, `rot=90` |
| AVIF still | Decodes |
| Variable-delay GIF timing | Correct: 5.67 s wall vs 5.6 s expected |
| Looping GIF duration | 3.08 s vs 3.0 s |
| Corrupt MP4 / .txt | Fail cleanly ("moov atom not found", "Failed to recognize file format") |
| Animated WebP | **Fails** with FFmpeg 6.1 |

## Baseline test matrix (plan 1.4)
P = pass, F = fail/absent, U = unknown (needs Windows). "src" = from source reading, not running.

| Test | MultipleVideoPlayer | MosaicPlayer |
|---|---|---|
| Drop 1 / 6 files / folder | U (src: supported) | U on Windows; P via CLI on Linux |
| HEVC 4K smooth | U | U |
| Hardware decode active | U (src: `hwdec=auto-safe`) | U (src: CPU by default ≤1080p30) |
| GIF animates and loops | F (src: `.gif` not accepted) | P on Linux |
| Still images | F (src: not accepted) | F on drop (src: not in extension list) |
| HEIC / AVIF / animated WebP | U | U |
| Removing a tile frees memory | U | P (`test_closed_tiles_are_freed`) |
| Move/copy/delete feature | F | F |
| Renderer / hwdec path | src: render API OpenGL, `auto-safe` | src: render API OpenGL, copy mode above ~1080p30 |
| Switch latency | U | U |
| Autoplay / loop-next / sidebar / thumbnails | F / F (AB loop only) / F / F | P / P / F / F |
| Speed controls to remove | Present (plus frame step, AB, picture adj.) | Present (speed) |
| Hover controls | src: yes | src: canvas overlays |
| Zoom / pan / scrub | src: wheel zoom, middle pan, timeline drag | src: Ctrl+wheel zoom |
| Per-tile volume / mute | src: yes | src: yes |
| Maximize / full screen / resize | U | U |
| Corrupt file / non-media | U | P on Linux (error tile) |
| 6/9/12 tiles HEVC 1080p, 4× 4K, 10-min memory | U | U |

## Requirements changes
- 2026-11-19: **R22 Playlists and tags** added at your request. Spec, interpretation and acceptance tests in `docs/R22-playlists-and-tags.md`. Not built (Phase 1 gate). It replaces the separate "Save/Open playlist" in plan 2.8, so the app has one playlist concept.

## Decisions made
- Did not install anything on your machine (none attached).
- Did not create `NOTICE.md`/`LICENSES.md` yet: no upstream code has been copied into this repo.

## Open questions for you
1. ~~How to run on Windows~~ Decided: continue in a local Claude Code session in Cursor on the Windows PC. See `HANDOFF.md`.
2. Confirm the GPU (plan says RTX 5070 Ti).
3. A HEIC sample photo.
4. Candidate choice (see report).
5. R22: tags on files **confirmed**. Smart (tag-rule) playlists assumed wanted unless you say otherwise.
