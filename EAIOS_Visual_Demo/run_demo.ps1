param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv .venv
}

if (-not $SkipInstall) {
    & $venvPython -m pip install -r requirements.txt
}

& $venvPython demo_servicenow_storytelling.py
& $venvPython -m pytest -q
& $venvPython -m streamlit run eaios_story_app.py
