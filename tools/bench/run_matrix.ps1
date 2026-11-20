# Phase 1.4 proceed-rule matrix: 6/9/12 tiles of 1080p60 HEVC and 4 tiles of 4K HEVC, both candidates,
# alternating apps so background drift affects both equally. Results: <OutRoot>\<run>\summary.json
param([string]$OutRoot = 'D:\Github\utada-candidates\bench', [string]$Media = 'D:\Github\utada\testmedia')
$runs = @(
    @{ n = 'mvp-hevc1080x6';     app = 'mvp';    t = 6;  f = 'hevc_1080_60.mp4' },
    @{ n = 'mosaic-hevc1080x6';  app = 'mosaic'; t = 6;  f = 'hevc_1080_60.mp4' },
    @{ n = 'mvp-hevc1080x9';     app = 'mvp';    t = 9;  f = 'hevc_1080_60.mp4' },
    @{ n = 'mosaic-hevc1080x9';  app = 'mosaic'; t = 9;  f = 'hevc_1080_60.mp4' },
    @{ n = 'mvp-hevc1080x12';    app = 'mvp';    t = 12; f = 'hevc_1080_60.mp4' },
    @{ n = 'mosaic-hevc1080x12'; app = 'mosaic'; t = 12; f = 'hevc_1080_60.mp4' },
    @{ n = 'mosaic-hevc1080x12-gpucopy';  app = 'mosaic'; t = 12; f = 'hevc_1080_60.mp4'; d = 'gpu-copy' },
    @{ n = 'mosaic-hevc1080x12-zerocopy'; app = 'mosaic'; t = 12; f = 'hevc_1080_60.mp4'; d = 'gpu-zero-copy' },
    @{ n = 'mvp-hevc4kx4';       app = 'mvp';    t = 4;  f = 'hevc_4k_30.mp4' },
    @{ n = 'mosaic-hevc4kx4';    app = 'mosaic'; t = 4;  f = 'hevc_4k_30.mp4' }
)
foreach ($r in $runs) {
    $p = @{ App = $r.app; Tiles = $r.t; File = (Join-Path $Media $r.f); OutDir = (Join-Path $OutRoot $r.n); Seconds = 55; Warmup = 15 }
    if ($r.d) { $p.Decoder = $r.d }
    Write-Output "== $($r.n)"
    & "$PSScriptRoot\run_tiles.ps1" @p
    Start-Sleep -Seconds 3
}
