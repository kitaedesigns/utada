<#
Developer entry point on Windows.
  .\tools\dev.ps1 setup          # .venv (Python 3.12) with app + dev dependencies, and libmpv
  .\tools\dev.ps1 run [args]     # run the app from source
  .\tools\dev.ps1 test [args]    # run the test suite (pytest args pass through)
#>
param([ValidateSet('setup', 'run', 'test')][string]$Command = 'run', [Parameter(ValueFromRemainingArguments)][string[]]$Rest)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'

if ($Command -eq 'setup' -or -not (Test-Path $py)) {
    if (-not (Test-Path $py)) { & py -3.12 -m venv (Join-Path $root '.venv') }  # plain 'python' may be the Store stub
    & $py -m pip install -q --upgrade pip
    & $py -m pip install -q -e "$root[dev]"
    & (Join-Path $PSScriptRoot 'get_libmpv.ps1')
    if ($Command -eq 'setup') { return }
}
# python-mpv finds libmpv-2.dll through PATH on Windows.
$env:PATH = (Join-Path $root 'vendor\mpv') + ';' + $env:PATH
Push-Location $root
try {
    if ($Command -eq 'test' -and $Rest) { & $py -m pytest @Rest; exit $LASTEXITCODE }
    if ($Command -eq 'test') {
        # Like CI: the GUI smoke tests in their own process. Their leftover player threads
        # otherwise take CPU from the time-budgeted layout tests that follow them.
        & $py -m pyflakes mosaicplayer tests; $lint = $LASTEXITCODE
        & $py -m pytest -q tests/test_layout.py tests/test_playlist.py tests/test_config.py; $unit = $LASTEXITCODE
        & $py -m pytest -q tests/test_app_smoke.py; $gui = $LASTEXITCODE
        "pyflakes: $lint  unit: $unit  gui: $gui"
        exit [int]($lint -or $unit -or $gui)
    }
    & $py -m mosaicplayer @Rest
    exit $LASTEXITCODE
} finally { Pop-Location }
