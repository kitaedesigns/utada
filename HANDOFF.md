# Handoff

Phase 1 approved 2026-11-20: **MosaicPlayer is the base**, merged into this repo (app code in `mosaicplayer/`). Phase 2 groundwork is done (see `PROGRESS.md`); the next step is Phase 2 of the build plan.

## Developing
`.\tools\dev.ps1 setup` once, then `.\tools\dev.ps1 run [files]` and `.\tools\dev.ps1 test` (pass pytest arguments quoted, e.g. `.\tools\dev.ps1 test 'tests/test_playlist.py' '-q'`).

## Before you start
1. Branch `claude/multi-video-player-build-5pxs6s`. Paste the full build plan as the first message (it is not in this repo). Read `PROGRESS.md`, `ARCHITECTURE.md`, `docs/R22-playlists-and-tags.md`, `docs/phase1-decision.md`.
2. Requirements added since the plan: R22 playlists and tags (tags on files/videos, smart tag-rule playlists included); **maximum 6 tiles on the wall** (see `PROGRESS.md`, Requirements changes).

## Local setup on the Windows PC (outside this repo)
- `D:\Github\utada-candidates\MultipleVideoPlayer` (branch `utada-probe` = measurement patch, also in `tools/bench/mvp-probe.patch`); staged build in `RustPlayer\dist\MultipleVideoPlayer-0.6.2-win64\`.
- `D:\Github\utada-candidates\mosaicplayer` with `.venv` (PySide6 6.8.1, python-mpv 1.0.7) and `mpv\libmpv-2.dll` (20261019, verified); portable build in `dist\` and unpacked in `..\mosaic-portable\`.
- `D:\Github\utada-candidates\tools-venv` (pillow-heif, py7zr), `bin\7zr.exe`, raw bench output in `bench\`.
- Rust: build with `$env:RUSTUP_TOOLCHAIN='stable-x86_64-pc-windows-msvc'` (the default toolchain is GNU).
- Python: use `py -3.12`; plain `python` is the Microsoft Store stub.

## Reproducing Phase 1 measurements
- Test media: `HEIF_PYTHON=/d/Github/utada-candidates/tools-venv/Scripts/python.exe tools/make_testmedia.sh testmedia` (Git Bash, ExifTool on PATH).
- Tile runs: `tools/bench/run_tiles.ps1`, `run_matrix.ps1`; app checks: `app_checks.ps1`; engine check: `engine_check.py`. Close games and other GPU-heavy apps first.
