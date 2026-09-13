# Fade The Chalk

**Live site:** https://kyle-vo.github.io/fade-the-chalk/ — Today's board, Moneyline, past days with results, and the Track scorecard.

Contrarian MLB home run / NFL anytime touchdown board. Two layers per player:

1. **Model %** - what the numbers say.
   - MLB: regressed season HR/PA x hitter platoon split x starter HR/BF (platoon-aware, damped)
     x bullpen HR rate for the late PAs x park factor x weather (temp, wind in/out) x run environment
     x a tiny hot-hand nudge, over expected plate appearances for the lineup slot.
   - NFL: spread + total -> implied team points -> expected offensive TDs -> player's regressed
     share of team TDs (2025 rates, positional priors, roster-normalized, injuries removed).
2. **Heat** - how obvious / over-bet the name is today (leaderboard rank, hot streak, narrative park,
   bad pitcher, primetime, big favorite). Type a real public-bet % into the board and it replaces heat.

Verdicts: **SLEEPER** (edge, nobody on him), **VALUE**, **TRAP** (crowd on him, no edge), **FADE**
(public 60%+ and negative edge), **CHALK** (hot name, no price entered yet).

## Run it

```powershell
.\run.ps1                 # today's MLB slate + current NFL week, opens output\board.html
.\run.ps1 2026-09-12      # specific MLB date (run again after lineups post, ~2-4h before first pitch)
.\run.ps1 -Sport nfl      # refresh one sport only
```

Then open `output\board.html`, expand "Paste the book's odds board", paste lines like
`Kyle Schwarber +165 62%` (odds, then optional public %) and hit Apply. Edge, verdicts and the
nasty score recompute live. Entered numbers are remembered in the browser.

Files: `fetch_data.py` (public MLB StatsAPI + ESPN feeds -> data/), `model.py` (-> output/board.json),
`build_html.py` (-> output/board.html), `serve.py` (optional local preview on :8765).
Requires Python 3 with `requests`.

## Knobs worth touching

- `model.py` PARK - HR park factors (100 = neutral). Update yearly.
- `model.py` heat formulas - what "the crowd is on him" means to you.
- `build_html.py` verdict thresholds (edge >= 4 pts, heat < 45, etc.) and the nasty score.
