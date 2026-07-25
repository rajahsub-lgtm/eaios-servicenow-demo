param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"

& $Python demo_servicenow_storytelling.py
& $Python -m pytest -q -p no:cacheprovider
& $Python smoke_test_visual_demo.py
