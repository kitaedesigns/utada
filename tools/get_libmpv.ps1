<#
Fetch the pinned libmpv used by the release build (same as .github/workflows/release.yml):
shinchiro mpv-winbuild-cmake 20261019, SHA-256 checked, into vendor\mpv\libmpv-2.dll.

Windows 10's built-in tar cannot open these .7z files (no LZMA/BCJ2), so this uses 7-Zip:
an installed 7z.exe if found, else the official standalone 7zr.exe (hash-pinned) in vendor\bin.
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$vendor = Join-Path $root 'vendor'
$mpvDir = Join-Path $vendor 'mpv'
$dll = Join-Path $mpvDir 'libmpv-2.dll'
$release = '20261019'
$asset = 'mpv-dev-x86_64-20261019-git-6a262d11f6.7z'
$assetSha = 'CA8604754170DB6F1B23139D8449782B1AE294A883211131954D30085985F77B'
$sevenZrSha = '256FECA8E274E5DA655E2A284FABAFD9F554365EB164862089DACD4E8276D282'  # 7zr.exe 26.04

if (Test-Path $dll) { "libmpv already present: $dll"; return }
New-Item -ItemType Directory -Force $mpvDir, (Join-Path $vendor 'bin') | Out-Null

$archive = Join-Path $vendor $asset
if (-not (Test-Path $archive)) {
    Invoke-WebRequest "https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/$release/$asset" -OutFile $archive
}
if ((Get-FileHash $archive -Algorithm SHA256).Hash -ne $assetSha) { Remove-Item $archive; throw "Checksum mismatch: $asset" }

$7z = @((Get-Command 7z -ErrorAction SilentlyContinue).Source, "$env:ProgramFiles\7-Zip\7z.exe") | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $7z) {
    $7z = Join-Path $vendor 'bin\7zr.exe'
    if (-not (Test-Path $7z)) { Invoke-WebRequest 'https://www.7-zip.org/a/7zr.exe' -OutFile $7z }
    if ((Get-FileHash $7z -Algorithm SHA256).Hash -ne $sevenZrSha) {
        Remove-Item $7z; throw '7zr.exe checksum mismatch (7-Zip may have released a new version; install 7-Zip or update the pinned hash)'
    }
}
& $7z e -y "-o$mpvDir" $archive libmpv-2.dll | Out-Null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $dll)) { throw 'libmpv extraction failed' }
"libmpv ready: $dll"
