"""Check what a given libmpv build decodes, headless (vo=null, hwdec=no).

Usage: python engine_check.py <dir-with-libmpv-2.dll> <file>...
Prints one JSON line per file: codec, size, EXIF rotation and the output size after it,
frames shown, wall time to end of file vs. container duration, and errors.
"""
import json
import os
import sys
import threading
import time

dll_dir, *files = sys.argv[1:]
os.environ["PATH"] = dll_dir + os.pathsep + os.environ["PATH"]
os.add_dll_directory(dll_dir)
import mpv  # noqa: E402

for path in files:
    p = mpv.MPV(vo="null", ao="null", hwdec="no", keep_open="no", loop_file="no",
                image_display_duration=1.0, terminal=False, config=False)
    done = threading.Event()
    end = {}

    @p.event_callback("end-file")
    def _end(ev, end=end, done=done):
        d = ev.data
        end["reason"] = getattr(d, "reason", None)
        end["error"] = getattr(d, "error", None)
        done.set()

    info = {"file": os.path.basename(path)}
    t0 = time.monotonic()
    p.play(path)
    frames, vparams, oparams = 0, None, None
    while not done.wait(0.02) and time.monotonic() - t0 < 30:
        try:
            vparams = p.video_params or vparams
            oparams = p.video_out_params or oparams
            frames = max(frames, p.estimated_frame_number or 0)
            if "codec" not in info and p.video_codec:
                info.update(codec=p.video_codec, duration=p.duration, fps=p.container_fps,
                            frame_count=p.estimated_frame_count)
        except Exception:
            pass
    info["wall_s"] = round(time.monotonic() - t0, 2)
    if vparams:
        info.update(w=vparams.get("w"), h=vparams.get("h"), rotate=vparams.get("rotate"),
                    pixfmt=vparams.get("hw-pixelformat") or vparams.get("pixelformat"))
    if oparams:
        info.update(out_w=oparams.get("dw"), out_h=oparams.get("dh"))
    info["frames_seen"] = frames
    info["end"] = str(end.get("reason")) if end else "timeout"
    if end.get("error"):
        info["error"] = str(end["error"])
    p.terminate()
    print(json.dumps(info), flush=True)
