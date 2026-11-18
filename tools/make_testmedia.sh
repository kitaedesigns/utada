#!/usr/bin/env bash
# Generates the synthetic test media set from the build plan (section 1.3).
# Usage: tools/make_testmedia.sh [outdir]   (default: testmedia/)
# Needs ffmpeg with libx265, libx264, libvpx-vp9, libwebp. Optional: heif-enc, exiftool.
# A PowerShell port is planned for the Windows machine; the ffmpeg lines are identical.
set -euo pipefail
OUT="${1:-testmedia}"
mkdir -p "$OUT"
cd "$OUT"
FF="ffmpeg -hide_banner -loglevel error -y"
# Video source: test pattern with a large frame counter and timestamp burned in.
vsrc() { # w h fps dur
  echo "testsrc2=size=$1x$2:rate=$3:duration=$4,drawtext=text='%{frame_num}  %{pts\\:hms}':fontsize=$(( $2 / 8 )):fontcolor=white:box=1:boxcolor=black@0.6:x=(w-tw)/2:y=(h-th)/2"
}
tone() { echo "sine=frequency=$1:duration=$2:sample_rate=48000"; }

$FF -f lavfi -i "$(vsrc 3840 2160 30 60)" -f lavfi -i "$(tone 440 60)" -c:v libx265 -preset ultrafast -tag:v hvc1 -pix_fmt yuv420p -c:a aac -shortest hevc_4k_30.mp4
$FF -f lavfi -i "$(vsrc 1920 1080 60 60)" -f lavfi -i "$(tone 660 60)" -c:v libx265 -preset ultrafast -tag:v hvc1 -pix_fmt yuv420p -c:a aac -shortest hevc_1080_60.mp4
$FF -f lavfi -i "$(vsrc 1920 1080 30 20)" -f lavfi -i "$(tone 550 20)" -c:v libx265 -preset ultrafast -profile:v main10 -pix_fmt yuv420p10le -tag:v hvc1 -c:a aac -shortest hevc_10bit.mp4
$FF -f lavfi -i "$(vsrc 1920 1080 30 60)" -f lavfi -i "$(tone 880 60)" -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -shortest h264_1080_30.mp4
$FF -f lavfi -i "$(vsrc 3840 2160 30 30)" -f lavfi -i "$(tone 330 30)" -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -shortest h264_4k_30.mkv
$FF -f lavfi -i "$(vsrc 1280 720 30 20)" -f lavfi -i "$(tone 770 20)" -c:v libvpx-vp9 -deadline realtime -cpu-used 8 -b:v 2M -c:a libopus -shortest vp9.webm
$FF -f lavfi -i "$(vsrc 1280 720 30 20)" -c:v libx264 -preset veryfast -pix_fmt yuv420p no_audio.mp4
# Portrait and short loop clips (for fit-rule and Loop/Next tests)
$FF -f lavfi -i "$(vsrc 1080 1920 30 10)" -f lavfi -i "$(tone 990 10)" -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -shortest portrait_1080x1920.mp4
$FF -f lavfi -i "$(vsrc 1280 720 30 10)" -f lavfi -i "$(tone 495 10)" -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -shortest loop_10s.mp4
# Corrupt: first ~40% of a valid file (moov atom is at the end -> unplayable)
head -c $(( $(stat -c %s h264_1080_30.mp4) * 2 / 5 )) h264_1080_30.mp4 > corrupt.mp4

# GIFs
$FF -f lavfi -i "$(vsrc 480 270 15 3)" -vf "split[a][b];[a]palettegen[p];[b][p]paletteuse" -loop 0 anim.gif
$FF -f lavfi -i "$(vsrc 480 270 15 2)" -vf "split[a][b];[a]palettegen[p];[b][p]paletteuse" -loop -1 anim_once.gif
# Variable delays: frames 0-9 at 10 fps, frames 10-19 at 2 fps (setpts changes timing; gif muxer keeps per-frame delay)
$FF -f lavfi -i "$(vsrc 320 180 10 2)" -vf "setpts='if(lt(N,10),N/10,1+(N-10)/2)/TB',split[a][b];[a]palettegen[p];[b][p]paletteuse" -fps_mode passthrough -loop 0 anim_variable.gif
# Large GIF (target >= 50 MB): noisy 1280x720, 25 s
$FF -f lavfi -i "testsrc2=size=1280x720:rate=25:duration=3,noise=alls=60:allf=t" -vf "split[a][b];[a]palettegen=max_colors=256[p];[b][p]paletteuse=dither=none" -loop 0 anim_large.gif
# Transparent GIF: moving opaque box on transparent background
$FF -f lavfi -i "color=c=red:size=320x240:rate=10:duration=2,format=rgba,geq=r='255':g='0':b='0':a='if(between(X,T*80,T*80+80)*between(Y,80,160),255,0)'" -vf "split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse=alpha_threshold=128" -gifflags -offsetting -loop 0 anim_transparent.gif

# Stills
$FF -f lavfi -i "testsrc2=size=1920x1080" -frames:v 1 still.jpg
$FF -f lavfi -i "testsrc2=size=1920x1080" -frames:v 1 still.png
$FF -f lavfi -i "testsrc2=size=1920x1080" -frames:v 1 -c:v libwebp still.webp
$FF -f lavfi -i "testsrc2=size=1920x1080" -frames:v 1 still.bmp
$FF -f lavfi -i "testsrc2=size=1920x1080" -frames:v 1 still.tiff
$FF -f lavfi -i "$(vsrc 480 270 10 2)" -c:v libwebp_anim -loop 0 anim.webp
$FF -f lavfi -i "color=c=black@0.0:size=800x600,format=rgba,drawbox=x=200:y=150:w=400:h=300:color=blue@0.7:t=fill" -frames:v 1 transparent.png
$FF -f lavfi -i "testsrc2=size=8000x6000" -frames:v 1 -q:v 3 big_8000x6000.jpg
# EXIF orientation 6: pixels stored landscape with "UP" text; viewer must rotate 90 deg CW to read it.
$FF -f lavfi -i "color=c=gray:size=1200x800,drawtext=text='UP ->':fontsize=200:fontcolor=white:x=(w-tw)/2:y=(h-th)/2" -frames:v 1 exif_rotated.jpg
if command -v exiftool >/dev/null; then exiftool -q -overwrite_original -Orientation=6 -n exif_rotated.jpg; else echo "WARN: exiftool missing, exif_rotated.jpg has no orientation tag"; fi
# AVIF (ffmpeg muxer)
$FF -f lavfi -i "testsrc2=size=1920x1080" -frames:v 1 -c:v libaom-av1 -still-picture 1 still.avif || echo "WARN: AVIF not generated"
# HEIC (needs heif-enc from libheif-examples)
if command -v heif-enc >/dev/null; then heif-enc -q 80 still.png -o still.heic || echo "WARN: HEIC not generated"; else echo "WARN: heif-enc missing; HEIC not generated"; fi

echo "not a video" > notamedia.txt
ls -la
