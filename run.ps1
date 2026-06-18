# make-free runner for Windows PowerShell. Delegates to the cross-platform tasks.py.
#   .\run.ps1 all          # up + seed + discover + validate + usecases
#   .\run.ps1 up seed
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run python tasks.py @args
} else {
    python tasks.py @args
}
