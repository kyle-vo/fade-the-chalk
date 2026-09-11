# Daily pipeline:  fetch -> model -> lock today's picks -> grade finished games -> build site -> push to GitHub Pages
# Usage:  .\run.ps1              today's MLB slate + current NFL week
#         .\run.ps1 2026-09-12   a specific MLB date
#         .\run.ps1 -NoPush      build locally only
param([string]$Date = "", [switch]$NoPush)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($Date) { $env:EDGE_DATE = $Date } else { Remove-Item Env:EDGE_DATE -ErrorAction SilentlyContinue }
python -X utf8 fetch_data.py all
python -X utf8 model.py
python -X utf8 lock.py
python -X utf8 grade.py
python -X utf8 build_site.py
if (-not $NoPush) {
    git add -A
    git commit -m "board $(Get-Date -Format 'yyyy-MM-dd HH:mm')" --quiet
    if ($?) { git push --quiet; Write-Host "pushed - live in ~1 min at https://kyle-vo.github.io/fade-the-chalk/" } else { Write-Host "nothing new to push" }
}
Start-Process (Join-Path $PSScriptRoot "docs\index.html")
