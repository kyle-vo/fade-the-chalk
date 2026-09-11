"""Lock predictions for past MLB dates, THEN grade against box scores.
Usage: python backtest.py 2026-09-03 2026-09-10
Note: season stats are as-of today, so a few days of results leak into the rates (small bias in the model's favor)."""
import sys, os, json, datetime, math, collections
import requests
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fetch_data, model

S = requests.Session(); S.headers['User-Agent'] = 'Mozilla/5.0'
start, end = sys.argv[1], sys.argv[2]
d0, d1 = datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)
BT = os.path.join(HERE, 'backtest'); os.makedirs(BT, exist_ok=True)

# ---- 1. lock predictions (no results touched) ----
preds = []
d = d0
while d <= d1:
    ds = d.isoformat(); lock = os.path.join(BT, f'pred_{ds}.json')
    if os.path.exists(lock):
        preds += json.load(open(lock, encoding='utf-8'))
    else:
        os.environ['EDGE_DATE'] = ds
        fetch_data.fetch_mlb()
        rows = [r for r in model.mlb() if r['lineupPosted']]   # only real lineups count
        for r in rows: r['date'] = ds
        json.dump(rows, open(lock, 'w', encoding='utf-8'))
        preds += rows
    print(f"{ds}: {sum(1 for p in preds if p['date'] == ds)} locked predictions")
    d += datetime.timedelta(days=1)

# ---- 2. now grade ----
games = {}
for ds in sorted({p['date'] for p in preds}):
    sch = S.get("https://statsapi.mlb.com/api/v1/schedule", params=dict(sportId=1, date=ds), timeout=40).json()
    for g in sch['dates'][0]['games']:
        if g['status']['detailedState'] not in ('Final', 'Completed Early', 'Game Over'): continue
        box = S.get(f"https://statsapi.mlb.com/api/v1/game/{g['gamePk']}/boxscore", timeout=40).json()
        for side in ('home', 'away'):
            for pid, pl in box['teams'][side]['players'].items():
                b = pl.get('stats', {}).get('batting', {})
                if b: games[(ds, pl['person']['id'])] = (b.get('homeRuns', 0), b.get('plateAppearances', 0))
graded = []
for p in preds:
    k = (p['date'], p['id'])
    if k not in games: continue
    hr, pa = games[k]
    if pa == 0: continue   # scratched
    graded.append({**p, 'hit': 1 if hr > 0 else 0, 'actualPA': pa})
json.dump(graded, open(os.path.join(BT, 'graded.json'), 'w', encoding='utf-8'))

n = len(graded); exp = sum(g['prob'] for g in graded); act = sum(g['hit'] for g in graded)
base = act / n
brier_m = sum((g['prob'] - g['hit']) ** 2 for g in graded) / n
brier_b = sum((base - g['hit']) ** 2 for g in graded) / n
ll = lambda p, y: -(y * math.log(p) + (1 - y) * math.log(1 - p))
ll_m = sum(ll(min(max(g['prob'], .01), .99), g['hit']) for g in graded) / n; ll_b = sum(ll(base, g['hit']) for g in graded) / n
print(f"\n=== {n} graded hitter-games, {start}..{end} ===")
print(f"predicted HR-games {exp:.1f} | actual {act} | ratio {act / exp:.2f}")
print(f"Brier model {brier_m:.4f} vs constant {brier_b:.4f} ({(1 - brier_m / brier_b) * 100:+.1f}% skill) | logloss model {ll_m:.4f} vs constant {ll_b:.4f}")
print("\nby model-% bucket (does 25% mean 25%?)")
buckets = [(0, .08), (.08, .12), (.12, .16), (.16, .20), (.20, .25), (.25, 1)]
for lo, hi in buckets:
    b = [g for g in graded if lo <= g['prob'] < hi]
    if b: print(f"  {lo * 100:>4.0f}-{hi * 100:<4.0f}%  n={len(b):4d}  predicted {sum(g['prob'] for g in b) / len(b) * 100:5.1f}%  actual {sum(g['hit'] for g in b) / len(b) * 100:5.1f}%")
print("\ntop-N of each day by model % (hit rate)")
for N in (5, 10, 20):
    hits = tot = 0
    for ds in sorted({g['date'] for g in graded}):
        day = sorted([g for g in graded if g['date'] == ds], key=lambda g: -g['prob'])[:N]
        hits += sum(g['hit'] for g in day); tot += len(day)
    print(f"  top {N:2d}: {hits}/{tot} = {hits / tot * 100:.1f}%  (base rate {base * 100:.1f}%)")
print("\nby HEAT (the rigged test: do the crowd's guys underperform their own numbers?)")
for lo, hi, lab in ((0, 35, 'cold  <35'), (35, 60, 'warm 35-60'), (60, 101, 'hot  60+')):
    b = [g for g in graded if lo <= g['heat'] < hi]
    if b: print(f"  {lab}: n={len(b):4d}  predicted {sum(g['prob'] for g in b) / len(b) * 100:5.1f}%  actual {sum(g['hit'] for g in b) / len(b) * 100:5.1f}%  actual/pred {sum(g['hit'] for g in b) / sum(g['prob'] for g in b):.2f}")
print("\nsleeper filter: model >= 20% and heat < 35")
b = [g for g in graded if g['prob'] >= .2 and g['heat'] < 35]
if b: print(f"  n={len(b)} predicted {sum(g['prob'] for g in b) / len(b) * 100:.1f}% actual {sum(g['hit'] for g in b) / len(b) * 100:.1f}%")
print("chalk filter: model >= 20% and heat >= 60")
b = [g for g in graded if g['prob'] >= .2 and g['heat'] >= 60]
if b: print(f"  n={len(b)} predicted {sum(g['prob'] for g in b) / len(b) * 100:.1f}% actual {sum(g['hit'] for g in b) / len(b) * 100:.1f}%")
print("\nflat-bet sim at FAIR odds for every player with model >= 20% (a book would price these shorter; this is the ceiling)")
b = [g for g in graded if g['prob'] >= .2]
pnl = sum((g['fair'] / 100 if g['hit'] else -1) for g in b)
print(f"  {len(b)} bets, {sum(g['hit'] for g in b)} hits, P/L {pnl:+.1f} units at fair prices")
