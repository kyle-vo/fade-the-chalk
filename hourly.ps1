# Hourly pull from this PC (Task Scheduler: "FadeTheChalk hourly"). Same pipeline as run.ps1, minus opening the browser,
# plus a pull before and after so it never collides with the GitHub Actions job. Log: hourly.log (last 200 lines kept).
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$log = Join-Path $PSScriptRoot "hourly.log"
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') ===" | Out-File $log -Append -Encoding utf8
git pull -q --no-rebase -X theirs origin main 2>&1 | Out-File $log -Append -Encoding utf8
foreach ($s in @("fetch_data.py all","model.py","odds.py","kalshi.py","ml.py","lock.py","grade.py","build_site.py","taker.py","lines.py","build_ml.py","build_lines.py")) {
    $parts = $s.Split(' '); $out = & python -X utf8 @parts 2>&1
    $out | Select-Object -Last 4 | Out-File $log -Append -Encoding utf8
}
git add -A
git commit -q -m "hourly $(Get-Date -Format 'yyyy-MM-dd HH:mm')" 2>&1 | Out-Null
git pull -q --no-rebase -X theirs origin main 2>&1 | Out-File $log -Append -Encoding utf8
git push -q origin main 2>&1 | Out-File $log -Append -Encoding utf8
"done $(Get-Date -Format 'HH:mm')" | Out-File $log -Append -Encoding utf8
$lines = Get-Content $log; if ($lines.Count -gt 200) { $lines | Select-Object -Last 200 | Set-Content $log -Encoding utf8 }
