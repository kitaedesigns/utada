<#
Phase 1.4 app-level checks that need no mouse: launch a candidate with files on the command line
(the same open path as drag and drop in both apps), let it run, sample its probe, take a screenshot,
optionally resize/maximize its window, and report whether it is still alive.

  .\app_checks.ps1 -App mvp|mosaic|mosaic-portable -Name types -Files a.gif,b.jpg -Seconds 15 [-Windowed] [-Resize]
Output: <OutRoot>\<app>-<name>\{probe.csv, shot-*.png, metrics.txt, result.json}
#>
param(
    [Parameter(Mandatory)][ValidateSet('mvp', 'mosaic', 'mosaic-portable')][string]$App,
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][string[]]$Files,
    [int]$Seconds = 15,
    [int]$Cells = 6,
    [switch]$Windowed,
    [switch]$Resize,
    [string]$OutRoot = 'D:\Github\utada-candidates\bench',
    [string]$Candidates = 'D:\Github\utada-candidates'
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type -Namespace W -Name U -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int hh, uint f);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
public struct RECT { public int Left, Top, Right, Bottom; }
'@ -ErrorAction SilentlyContinue
$out = Join-Path $OutRoot "$App-$Name"
New-Item -ItemType Directory -Force $out | Out-Null
Get-ChildItem $out -File | Remove-Item
$probe = Join-Path $out 'probe.csv'
$quoted = @($Files | ForEach-Object { "`"$_`"" })
function Shot($tag) {
    # Capture ONLY the test app's own window (PrintWindow on its handle), never the screen:
    # a screen grab picks up whatever other window happens to be on top.
    $h = (Get-Process -Id $target -ErrorAction SilentlyContinue).MainWindowHandle
    if (-not $h -or $h -eq [IntPtr]::Zero) { return }
    $r = New-Object W.U+RECT; [W.U]::GetWindowRect($h, [ref]$r) | Out-Null
    $w = $r.Right - $r.Left; $hh = $r.Bottom - $r.Top; if ($w -le 0 -or $hh -le 0) { return }
    $bmp = New-Object System.Drawing.Bitmap $w, $hh
    $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
    [W.U]::PrintWindow($h, $dc, 2) | Out-Null  # PW_RENDERFULLCONTENT
    $g.ReleaseHdc($dc)
    $small = New-Object System.Drawing.Bitmap $bmp, ([int]($w / 2)), ([int]($hh / 2))
    $small.Save((Join-Path $out "shot-$tag.png"), [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose(); $small.Dispose()
}
$t0 = Get-Date
if ($App -eq 'mvp') {
    $dist = Join-Path $Candidates 'MultipleVideoPlayer\RustPlayer\dist\MultipleVideoPlayer-0.6.2-win64'
    $data = Join-Path $out 'mvp-data'; New-Item -ItemType Directory -Force (Join-Path $data 'presets') | Out-Null
    $cols = if ($Cells -le 4) { 2 } elseif ($Cells -le 9) { 3 } else { 4 }
    $cellList = @(0..($Cells - 1) | ForEach-Object { @{ id = "cell$_" } })
    @{ name = 'last'; state = @{ picture = @(0, 0, 0, 0, 0); version = 1; cells = $cellList; columns = $cols
            geometry = @(100, 100, 1600, 900); borderless = $false; fullscreen = (-not $Windowed); muted = $true } } |
        ConvertTo-Json -Depth 6 | Set-Content (Join-Path $data 'presets\last.json') -Encoding utf8
    $env:GRIDPLAYER_DATA_DIR = $data; $env:MVP_PROBE_PATH = $probe; $env:MVP_METRICS_PATH = Join-Path $out 'metrics.txt'
    Set-Content $env:MVP_METRICS_PATH '' ; $env:MVP_AUTO_CLOSE_MS = [string]($Seconds * 1000)
    $proc = Start-Process (Join-Path $dist 'MultipleVideoPlayer-probe.exe') -ArgumentList $quoted -PassThru
    $target = $proc.Id
} elseif ($App -eq 'mosaic') {
    $src = Join-Path $Candidates 'mosaicplayer'
    $env:PATH = (Join-Path $src 'mpv') + ';' + $env:PATH
    $a = @("`"$PSScriptRoot\mosaic_probe.py`"", "`"$src`"", "`"$probe`"", '--no-save-config', '--no-confirm', '--quit-after', $Seconds)
    if (-not $Windowed) { $a += '--fullscreen' }
    $proc = Start-Process (Join-Path $src '.venv\Scripts\python.exe') -ArgumentList ($a + $quoted) -PassThru
    $target = $null
} else {
    $exe = Join-Path $Candidates 'mosaic-portable\MosaicPlayer\MosaicPlayer.exe'
    $a = @('--no-save-config', '--no-confirm', '--quit-after', $Seconds); if (-not $Windowed) { $a += '--fullscreen' }
    $proc = Start-Process $exe -ArgumentList ($a + $quoted) -PassThru
    $target = $proc.Id
}
Start-Sleep -Seconds ([Math]::Min(8, $Seconds - 4))
if (-not $target) {
    $target = [int](Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*mosaic_probe.py*' } |
        Sort-Object WorkingSetSize -Descending | Select-Object -First 1).ProcessId
}
Shot 'a'
$events = @()
if ($Resize) {
    $h = (Get-Process -Id $target).MainWindowHandle
    [W.U]::ShowWindow($h, 3) | Out-Null; $events += "maximize@$([int]((Get-Date) - $t0).TotalSeconds)s"; Start-Sleep 2; Shot 'max'
    [W.U]::ShowWindow($h, 9) | Out-Null; [W.U]::SetWindowPos($h, [IntPtr]::Zero, 50, 50, 800, 500, 0x0040) | Out-Null
    $events += "800x500@$([int]((Get-Date) - $t0).TotalSeconds)s"; Start-Sleep 2; Shot 'small'
    [W.U]::SetWindowPos($h, [IntPtr]::Zero, 50, 50, 2400, 1200, 0x0040) | Out-Null
    $events += "2400x1200@$([int]((Get-Date) - $t0).TotalSeconds)s"; Start-Sleep 2; Shot 'large'
}
$gpu = (Get-Counter "\GPU Engine(pid_$($target)_*engtype_VideoDecode)\Utilization Percentage" -ErrorAction SilentlyContinue).CounterSamples |
    Measure-Object CookedValue -Sum
$alive = -not (Get-Process -Id $target -ErrorAction SilentlyContinue).HasExited
$mem = [int]((Get-Process -Id $target).PrivateMemorySize64 / 1MB)
$exited = $proc.WaitForExit(($Seconds + 15) * 1000)
if (-not $exited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue; Stop-Process -Id $target -Force -ErrorAction SilentlyContinue }
$result = [ordered]@{ app = $App; name = $Name; alive_during_run = $alive; exited_cleanly = $exited; exit_code = $(if ($exited) { $proc.ExitCode }); private_mb = $mem
    video_decode_pct = [math]::Round($gpu.Sum, 1); events = $events }
$result | ConvertTo-Json | Set-Content (Join-Path $out 'result.json')
$result | ConvertTo-Json -Compress
