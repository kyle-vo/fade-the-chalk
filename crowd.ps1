# Crowd refresh (no Odds API credits): re-pull Kalshi/Robinhood money for props and moneylines, regrade, rebuild, push.
# Scheduled hourly by Task Scheduler ("FadeTheChalk crowd refresh"); run by hand any time.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
python -X utf8 kalshi.py
python -X utf8 ml.py --crowd-only
python -X utf8 grade.py
python -X utf8 build_site.py
python -X utf8 taker.py
python -X utf8 build_ml.py
git add -A
git commit -q -m "crowd refresh $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
if ($?) { git push -q }
