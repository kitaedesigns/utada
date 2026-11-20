# Architecture (Phase 1: candidate analysis)

**Decision (approved 2026-11-20): MosaicPlayer is the base.** Its history is merged into this repo at `004dd93` (see `NOTICE.md`); the app code lives in `mosaicplayer/`. The comparison below is kept as the record of why (`docs/phase1-decision.md`). Statements marked **(inferred)** come from reading code, not from running it on Windows.

| | MultipleVideoPlayer (primary) | MosaicPlayer (backup) |
|---|---|---|
| Repo / commit | github.com/alan52013141314/MultipleVideoPlayer @ `b11f76c` (2026-11-07) | github.com/itsui/mosaicplayer @ `004dd93` (2026-10-20) |
| History | 7 commits, 1 author. Rust rewrite landed 2026-11-06. No git tags. | 60 commits, 1 author. Tag `v0.3.0`. |
| Releases | None. `RustPlayer/native-components.json`: "No public binary release is published". README: repo holds no prebuilt binaries. `build.ps1` fails on Windows 10 (its `tar` cannot open `.7z`). | **None published** (checked 2026-11-20): README links lead to an empty releases page; `release.yml` only creates drafts. Building the portable zip locally with the workflow's steps works (98 MB). |
| License | GPL-3.0-or-later; credits GridPlayer (vzhd1701) | GPL-3.0-or-later; `THIRD-PARTY-NOTICES.md` |
| Language / UI | Rust 2021, **egui/eframe 0.31.1** (immediate-mode), `glow` OpenGL backend | Python ≥3.11, **PySide6 6.8.1** (Qt 6), one `QOpenGLWidget` canvas |
| UI GPU-backed? | Yes, egui draws through OpenGL | Yes for the video canvas (OpenGL); menus and dialogs are standard Qt widgets |
| mpv binding | Hand-written FFI, `libmpv-2.dll` loaded at runtime via `libloading` (`src/player.rs`) | `python-mpv` 1.0.7 (ctypes) |
| mpv build | shinchiro mpv-winbuild-cmake 20261106 (mpv `9028187538`, FFmpeg `9f690c6a4`), fetched by `build.ps1`, SHA-256 checked | System libmpv on Linux; Windows build bundles a libmpv DLL via PyInstaller (`packaging/mosaicplayer.spec`) **(inferred)** |
| Embedding | **mpv render API (OpenGL)** into an FBO per tile, shown as an egui texture | **mpv render API (OpenGL)** per tile in worker threads, composited on one GL canvas with GPU fences (`tile.py`, `render.py`) |
| Overlay "airspace" problem | Does not apply: video is a texture inside the app's own surface | Does not apply: same reason |
| `hwdec` | `auto-safe` for every tile. **Measured on the RTX 5070 Ti: resolves to `nvdec`** (zero-copy, CUDA to OpenGL) | Policy (`tile.py`, `config.py`): default `auto` = CPU decode for videos up to ~1080p30, GPU **copy** mode (`d3d11va-copy` on Windows) above, within a 1200 Mpx/s GPU budget; `gpu-copy`, `gpu-zero-copy`, `cpu` selectable. **Measured: `gpu-zero-copy` falls back to CPU on Windows** (no OpenGL interop for `d3d11va`) |
| Other mpv options | `vo=libmpv`, `keep-open=yes`, `pause=yes`, `hr-seek=yes`, `keepaspect=no` (app computes the rect in `view.rs`) | `keepaspect=yes`, **`panscan=1.0` (crops to fill)**, `loop-file=inf` for Loop, `cache=no`, small demuxer buffers, `vd-lavc-threads=2`, `hr-seek=no` |
| Tiles | Fixed cell count, **1 to 12 hard cap** (`model.rs:192`, `app.rs:127`). Default 6. | Unbounded; README shows 120 |
| Drag and drop | `app.rs:1573` (`dropped_files`) → `open_paths` | `window.py:442` `dropEvent`, filtered by `is_video` |
| Accepted types | Video extensions only (`model.rs:330`); **no GIF, no images** | Video extensions + `.gif` (`playlist.py:27`); **no still images** on drop |
| Hover controls | Per-cell egui control bar (`app.rs` ~900–1300) | Canvas-drawn overlays/stats (`canvas.py`) |
| Window modes | Fullscreen, borderless (`app.rs:622`) | Fullscreen (F/F11), stay on top (T) |
| Volume | Per tile (`v.volume`); no master | Per tile + mute-all (M); no master slider found |
| Zoom/pan | Wheel zoom toward cursor, middle-drag pan (`view.rs`) | Ctrl+wheel zoom via `video-zoom`/`video-pan-*` (`tile.py:420`) |
| End of media | AB loop only | Loop / Next in folder / Random / Stop (`options.py`) |
| Settings | JSON presets in `portable_data` next to exe | `QSettings` (`config.py`) + `.gpls`/`.m3u` playlists |
| Tests | Rust unit tests + `verify`/`seek_perf` binaries (Windows only) | 118 pytest tests, CI workflow |
| Out-of-scope features present | Speed, exact frame stepping, AB loops, brightness/contrast/gamma/hue, borderless | Speed (`set_all_speed`), random start, sync-all |

## Implication for the target app

Both candidates render mpv into OpenGL textures, so hover bars, badges, and menus drawn by the app sit on top of video without the native-child-window problem. Neither has a file-browser sidebar, still-image support, move/copy/delete, or undo; those are new work in either base.

**Measured on the RTX 5070 Ti (2026-11-20, details in `PROGRESS.md`):** with an OpenGL render context on Windows there is no zero-copy interop for `d3d11va`, but `auto-safe` lands on zero-copy `nvdec`, so OpenGL rendering does not force copy back. The cost is memory: about 0.5 GB of GPU memory and 0.65 GB of process memory per 1080p tile in MultipleVideoPlayer (6 tiles: 3.0 GB / 3.9 GB), against about 0.17 / 0.23 GB per tile for MosaicPlayer's `d3d11va-copy` (6 tiles: 1.0 GB / 1.4 GB). With the 6-tile cap both fit easily in 16 GB of GPU memory, and both decode 6 × 1080p60 HEVC and 6 × 4K30 HEVC with no dropped frames.
