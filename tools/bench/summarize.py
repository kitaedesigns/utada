"""Summarize one run_tiles.ps1 run: python summarize.py <outdir> <warmup-seconds>

Reads probe.csv (per-tile mpv counters, 1 row per tile per second, plus "app" rows)
and proc.csv (Windows/NVIDIA counters), writes summary.json and prints one line.
Counter deltas are taken between the first and last probe row after the warmup.
"""
import csv
import json
import os
import statistics as st
import sys

out, warmup = sys.argv[1], float(sys.argv[2])
COLS = ["t", "tile", "file", "hwdec", "time_pos", "container_fps", "est_vf_fps",
        "frame_drops", "decoder_drops", "vo_delayed", "frames_drawn", "app_fps"]


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


rows = []
with open(os.path.join(out, "probe.csv"), encoding="utf-8") as f:
    for r in csv.reader(f):
        if len(r) >= len(COLS):
            rows.append(dict(zip(COLS, r)))
end = max(num(r["t"]) for r in rows)
# Stop well before the end: MosaicPlayer's --quit-after starts closing tiles ~6 s before the
# run length. A fixed cut (argv[3], seconds) is used rather than detecting the freeze, which
# could hide a real mid-run stall.
stop = float(sys.argv[3]) if len(sys.argv) > 3 else end - 4
win = [r for r in rows if warmup <= num(r["t"]) <= stop]
app_fps = [num(r["app_fps"]) for r in win if r["tile"] == "app" and num(r["app_fps"]) is not None]
tiles = {}
for r in win:
    if r["tile"] != "app":
        tiles.setdefault(r["tile"], []).append(r)

per_tile = []
for k, rs in sorted(tiles.items(), key=lambda kv: int(kv[0])):
    a, b = rs[0], rs[-1]
    wall = num(b["t"]) - num(a["t"])
    if wall <= 0:
        continue

    def d(c):
        x, y = num(a[c]), num(b[c])
        return None if x is None or y is None else y - x

    per_tile.append({
        "tile": int(k), "file": b["file"], "hwdec": sorted({r["hwdec"] or "no" for r in rs}),
        "wall_s": round(wall, 1),
        "speed": round(d("time_pos") / wall, 3) if d("time_pos") is not None else None,
        "container_fps": num(b["container_fps"]), "est_vf_fps": num(b["est_vf_fps"]),
        "frame_drops": d("frame_drops"), "decoder_drops": d("decoder_drops"),
        "vo_delayed": d("vo_delayed"),
        "drawn_per_s": round(d("frames_drawn") / wall, 1) if d("frames_drawn") is not None else None,
    })

proc = []
pp = os.path.join(out, "proc.csv")
if os.path.exists(pp):
    with open(pp, encoding="utf-8") as f:
        proc = [{k: num(v) for k, v in r.items()} for r in csv.DictReader(f)]
    proc = [r for r in proc if r.get("t") is not None and r["t"] <= stop]


def avg(key, src=proc):
    v = [r[key] for r in src if r.get(key) is not None]
    return round(st.mean(v), 1) if v else None


def peak(key, src=proc):
    v = [r[key] for r in src if r.get(key) is not None]
    return round(max(v), 1) if v else None


drops = [(t["frame_drops"] or 0) + (t["decoder_drops"] or 0) for t in per_tile]
summary = {
    "tiles": len(per_tile),
    "hwdec": sorted({h for t in per_tile for h in t["hwdec"]}),
    "total_drops": sum(drops), "max_tile_drops": max(drops) if drops else None,
    "min_speed": min((t["speed"] for t in per_tile if t["speed"] is not None), default=None),
    "min_drawn_per_s": min((t["drawn_per_s"] for t in per_tile if t["drawn_per_s"] is not None), default=None),
    "app_fps_mean": round(st.mean(app_fps), 1) if app_fps else None,
    "app_fps_min": round(min(app_fps), 1) if app_fps else None,
    "cores_used": avg("cores_used"), "cpu_pct_machine": avg("cpu_pct_machine"),
    "private_mb_peak": peak("private_mb"), "gpu_dedicated_mb_peak": peak("gpu_dedicated_mb"),
    "eng_videodecode": avg("eng_videodecode"), "eng_3d": avg("eng_3d"), "eng_copy": avg("eng_copy"),
    "smi_dec": avg("smi_dec"), "smi_gpu": avg("smi_gpu"),
    "per_tile": per_tile,
}
with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=1)
print(json.dumps({k: v for k, v in summary.items() if k != "per_tile"}))
