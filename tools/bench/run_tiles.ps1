<#
Phase 1.4 tile benchmark: open N copies of one video in a candidate, full screen, and record
  - per-tile mpv counters from the app's probe (hwdec-current, drops, frames drawn), and
  - per-process Windows counters (CPU, private memory, GPU engine use incl. Video Decode,
    dedicated GPU memory) plus nvidia-smi decoder load.
Then summarize with summarize.py.

  .\run_tiles.ps1 -App mvp    -Tiles 6 -File D:\...\hevc_1080_60.mp4 -OutDir D:\...\bench\mvp-6
  .\run_tiles.ps1 -App mosaic -Tiles 9 -File ... -Decoder auto
#>
param(
    [Parameter(Mandatory)][ValidateSet('mvp', 'mosaic')][string]$App,
    [Parameter(Mandatory)][int]$Tiles,
    [Parameter(Mandatory)][string]$File,
    [Parameter(Mandatory)][string]$OutDir,
    [int]$Seconds = 55,
    [int]$Warmup = 12,
    [string]$Decoder = '',   # mosaic only: auto / cpu / gpu-copy / gpu-zero-copy
    [switch]$Windowed,       # for long runs: leave the desktop usable
    [string]$Candidates = 'D:\Github\utada-candidates'
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $OutDir | Out-Null
$probe = Join-Path $OutDir 'probe.csv'
$procCsv = Join-Path $OutDir 'proc.csv'
Remove-Item $probe, $procCsv -ErrorAction SilentlyContinue
$fileArgs = @(1..$Tiles | ForEach-Object { "`"$File`"" })

if ($App -eq 'mvp') {
    $dist = Join-Path $Candidates 'MultipleVideoPlayer\RustPlayer\dist\MultipleVideoPlayer-0.6.2-win64'
    $data = Join-Path $OutDir 'mvp-data'
    New-Item -ItemType Directory -Force (Join-Path $data 'presets') | Out-Null
    $cols = if ($Tiles -le 4) { 2 } elseif ($Tiles -le 9) { 3 } else { 4 }
    $cells = @(0..($Tiles - 1) | ForEach-Object { @{ id = "cell$_" } })
    $preset = @{ name = 'last'; state = @{ picture = @(0, 0, 0, 0, 0); version = 1; cells = $cells; columns = $cols
            geometry = @(80, 80, 2400, 1200); borderless = $false; fullscreen = (-not $Windowed); muted = $true } }
    $preset | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $data 'presets\last.json') -Encoding utf8
    $env:GRIDPLAYER_DATA_DIR = $data
    $env:MVP_PROBE_PATH = $probe
    $env:MVP_AUTO_CLOSE_MS = [string]($Seconds * 1000)
    $proc = Start-Process -FilePath (Join-Path $dist 'MultipleVideoPlayer-probe.exe') -ArgumentList $fileArgs -PassThru
    $targetPid = $proc.Id
} else {
    $src = Join-Path $Candidates 'mosaicplayer'
    $env:PATH = (Join-Path $src 'mpv') + ';' + $env:PATH
    $a = @("`"$PSScriptRoot\mosaic_probe.py`"", "`"$src`"", "`"$probe`"", '--no-save-config', '--no-confirm',
        '--quit-after', $Seconds)
    if (-not $Windowed) { $a += '--fullscreen' }
    if ($Decoder) { $a += @('--decoder', $Decoder) }
    $proc = Start-Process -FilePath (Join-Path $src '.venv\Scripts\python.exe') -ArgumentList ($a + $fileArgs) -PassThru
    $targetPid = $null  # resolved after warmup (the venv python.exe is a launcher)
}

Start-Sleep -Seconds $Warmup
if (-not $targetPid) {
    # The real interpreter: the python.exe running mosaic_probe.py with the most memory.
    $targetPid = [int](Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*mosaic_probe.py*' } |
        Sort-Object WorkingSetSize -Descending | Select-Object -First 1).ProcessId
}
$sampleSecs = $Seconds - $Warmup - 4
$cores = [Environment]::ProcessorCount
$p = Get-Process -Id $targetPid
$lastCpu = $p.TotalProcessorTime.TotalSeconds; $lastT = Get-Date
"t,cores_used,cpu_pct_machine,private_mb,gpu_dedicated_mb,eng_3d,eng_videodecode,eng_copy,eng_other,smi_gpu,smi_dec,smi_mem_mb" | Set-Content $procCsv
for ($i = 0; $i -lt $sampleSecs; $i++) {
    $c = Get-Counter -Counter @("\GPU Engine(pid_$($targetPid)_*)\Utilization Percentage", "\GPU Process Memory(pid_$($targetPid)_*)\Dedicated Usage") -ErrorAction SilentlyContinue
    $eng = @{ '3D' = 0.0; 'VideoDecode' = 0.0; 'Copy' = 0.0; 'other' = 0.0 }; $ded = 0.0
    foreach ($s in $c.CounterSamples) {
        if ($s.Path -match 'gpu process memory') { $ded += $s.CookedValue; continue }
        if ($s.InstanceName -match 'engtype_(\w+)$') { $k = $Matches[1]; if (-not $eng.ContainsKey($k)) { $k = 'other' }; $eng[$k] += $s.CookedValue }
    }
    $smi = (nvidia-smi --query-gpu=utilization.gpu,utilization.decoder,memory.used --format=csv,noheader,nounits) -split ',\s*'
    $p = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
    if (-not $p) { break }
    $now = Get-Date; $cpu = $p.TotalProcessorTime.TotalSeconds
    $used = ($cpu - $lastCpu) / ($now - $lastT).TotalSeconds; $lastCpu = $cpu; $lastT = $now
    [string]::Format([cultureinfo]::InvariantCulture, "{0:F1},{1:F2},{2:F1},{3:F0},{4:F0},{5:F1},{6:F1},{7:F1},{8:F1},{9},{10},{11}",
        ($now - $proc.StartTime).TotalSeconds, $used, (100 * $used / $cores), ($p.PrivateMemorySize64 / 1MB), ($ded / 1MB),
        $eng['3D'], $eng['VideoDecode'], $eng['Copy'], $eng['other'], $smi[0], $smi[1], $smi[2]) | Add-Content $procCsv
}
if (-not $proc.WaitForExit(($Seconds + 20) * 1000)) { Stop-Process -Id $proc.Id -Force; Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue; 'killed' }
& py -3.12 -I "$PSScriptRoot\summarize.py" $OutDir $Warmup ($Seconds - 8)
