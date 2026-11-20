# Handoff to the Windows session

Last cloud session ended at the Phase 1 decision gate (2026-11-19). Continue on the Windows PC.

## Before you start
1. Clone and check out the branch:
   `git clone https://github.com/kitaedesigns/utada; cd utada; git checkout claude/multi-video-player-build-5pxs6s`
2. The full build plan is saved at `docs/BUILD-PLAN.md` (with R22 added). Tell the new session: "Read `docs/BUILD-PLAN.md`, `HANDOFF.md`, `PROGRESS.md`, `ARCHITECTURE.md` and `docs/R22-playlists-and-tags.md`, then continue Phase 1 on this Windows PC."

## What the next session should do (remaining Phase 1)
1. Record GPU and driver: `Get-CimInstance Win32_VideoController | Select Name, DriverVersion`.
2. Install prerequisites, telling you first: Git, FFmpeg (`winget install Gyan.FFmpeg`), optionally ExifTool; Rust MSVC + VS C++ Build Tools (primary candidate); Python 3.11+ (backup).
3. Regenerate test media (not in git): run `tools/make_testmedia.sh testmedia` from Git Bash. HEIC needs a real photo in `testmedia/`.
4. Build and run both candidates; for MosaicPlayer also try its published portable zip.
5. Run the plan's 1.4 matrix on both, focusing on the proceed rule: HEVC with hardware decode (`hwdec-current`, Task Manager "Video Decode"), and 6/9/12 tiles of 1080p HEVC without dropped frames. Check whether OpenGL rendering forces a copy-back decode path (see `ARCHITECTURE.md`).
6. Fill in the U cells in `PROGRESS.md`, then deliver the 1.5 decision report.

## Decisions so far
- R22 added; tags go on files (confirmed).
- Current lean: MosaicPlayer, pending Windows measurements. Not approved yet.
- No feature code until the 1.5 report is approved.
