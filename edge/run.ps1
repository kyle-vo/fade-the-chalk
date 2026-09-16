# Usage:  .\run.ps1            -> today's MLB slate + current NFL week
#         .\run.ps1 2026-09-12 -> a specific MLB date (NFL always pulls the live week)
#         .\run.ps1 -Sport nfl -> only refresh one sport (mlb | nfl | all)
param([string]$Date = "", [string]$Sport = "all")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($Date) { $env:EDGE_DATE = $Date } else { Remove-Item Env:EDGE_DATE -ErrorAction SilentlyContinue }
python fetch_data.py $Sport
python model.py
python build_html.py
Start-Process (Join-Path $PSScriptRoot "output\board.html")
