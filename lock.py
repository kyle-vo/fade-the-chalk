"""Freeze today's picks BEFORE games start so they can be graded honestly later.
MLB -> backtest/pred_<date>.json (rows for games still pre-game replace the old snapshot; started games keep their locked rows)
NFL -> backtest/nfl_<season>_wk<N>.json (same per-game rule)."""
import json, os, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); os.makedirs(BT, exist_ok=True)
board = json.load(open(os.path.join(HERE, 'output', 'board.json'), encoding='utf-8'))
PRE = ('Scheduled', 'Pre-Game', 'Warmup', 'STATUS_SCHEDULED')

def merge(path, new_rows, gkey):
    old = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []
    started = {r[gkey] for r in new_rows if r['state'] not in PRE}
    keep = [r for r in old if r[gkey] in started]                      # frozen: game already started at some snapshot
    frozen_games = {r[gkey] for r in keep}
    fresh = [r for r in new_rows if r[gkey] not in frozen_games and r['state'] in PRE]
    # games that started but were never snapshotted pre-game: keep whatever we have, flagged
    late = [dict(r, lateLock=True) for r in new_rows if r[gkey] in started and r[gkey] not in frozen_games]
    out = keep + fresh + late
    json.dump(out, open(path, 'w', encoding='utf-8'))
    return len(keep), len(fresh), len(late)

if board['mlb']:
    date = os.environ.get('EDGE_DATE') or board['mlb'][0]['time'][:10]
    for r in board['mlb']: r['date'] = date
    k, f, l = merge(os.path.join(BT, f'pred_{date}.json'), board['mlb'], 'gamePk')
    print(f"MLB {date}: kept {k} frozen, refreshed {f}, late {l}")
if board['nfl']:
    sb = json.load(open(os.path.join(HERE, 'data', 'nfl_scoreboard.json'), encoding='utf-8'))
    wk = f"{sb['season']['year']}_wk{sb['week']['number']}"
    for r in board['nfl']: r['week'] = wk
    k, f, l = merge(os.path.join(BT, f'nfl_{wk}.json'), board['nfl'], 'eventId')
    print(f"NFL {wk}: kept {k} frozen, refreshed {f}, late {l}")
