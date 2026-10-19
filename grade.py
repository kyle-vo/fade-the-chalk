"""Grade every locked pick whose game is final. Writes backtest/res_<date>.json (MLB) and backtest/nflres_<week>.json.
Never rewrites a lock file - results live beside it."""
import json, os, glob, datetime
import requests
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest')
S = requests.Session(); S.headers['User-Agent'] = 'Mozilla/5.0'
get = lambda u, **p: S.get(u, params=p, timeout=40).json()
FINAL = ('Final', 'Completed Early', 'Game Over')

def grade_mlb():
    for lock in sorted(glob.glob(os.path.join(BT, 'pred_*.json'))):
        date = os.path.basename(lock)[5:15]; res_path = os.path.join(BT, f'res_{date}.json')
        res = json.load(open(res_path, encoding='utf-8')) if os.path.exists(res_path) else {}
        rows = json.load(open(lock, encoding='utf-8'))
        pks = {r['gamePk'] for r in rows if 'gamePk' in r}
        if not pks:   # older lock without gamePk: look up by date
            sch = get("https://statsapi.mlb.com/api/v1/schedule", sportId=1, date=date)
            pks = {g['gamePk'] for d in sch.get('dates', []) for g in d['games']}
        done = set(res.get('_games', []))
        for pk in pks - done:
            box = get(f"https://statsapi.mlb.com/api/v1/game/{pk}/boxscore")
            st = get("https://statsapi.mlb.com/api/v1/schedule", sportId=1, gamePk=pk)
            st = next((g['status']['detailedState'] for d in st.get('dates', []) for g in d['games']), '')
            if st not in FINAL: continue
            for side in ('home', 'away'):
                for pid, pl in box['teams'][side]['players'].items():
                    b = pl.get('stats', {}).get('batting', {})
                    if b: res[str(pl['person']['id'])] = {'hr': b.get('homeRuns', 0), 'pa': b.get('plateAppearances', 0)}
            res.setdefault('_games', []).append(pk)
        json.dump(res, open(res_path, 'w', encoding='utf-8'))
        print(f"MLB {date}: {len(res.get('_games', []))}/{len(pks)} games graded")

def grade_nfl():
    for lock in sorted(glob.glob(os.path.join(BT, 'nfl_*.json'))):
        wk = os.path.basename(lock)[4:-5]; res_path = os.path.join(BT, f'nflres_{wk}.json')
        res = json.load(open(res_path, encoding='utf-8')) if os.path.exists(res_path) else {}
        rows = json.load(open(lock, encoding='utf-8'))
        evs = {r['eventId'] for r in rows}; done = set(res.get('_games', []))
        for ev in evs - done:
            sm = get("https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/summary", event=ev)
            if sm.get('header', {}).get('competitions', [{}])[0].get('status', {}).get('type', {}).get('completed') is not True: continue
            for team in sm.get('boxscore', {}).get('players', []):
                for cat in team.get('statistics', []):
                    if cat['name'] not in ('rushing', 'receiving'): continue
                    ti = cat['labels'].index('TD') if 'TD' in cat['labels'] else None
                    if ti is None: continue
                    for a in cat['athletes']:
                        pid = a['athlete']['id']; td = int(a['stats'][ti] or 0)
                        res[pid] = {'td': res.get(pid, {}).get('td', 0) + td, 'played': True}
            res.setdefault('_games', []).append(ev)
        json.dump(res, open(res_path, 'w', encoding='utf-8'))
        print(f"NFL {wk}: {len(res.get('_games', []))}/{len(evs)} games graded")

def stats_nfl():
    """Full box-score lines for every finished game on an NFL lock (yards, receptions, targets, carries, passing), so yardage and fantasy
    projections can be graded the way touchdowns are. Writes backtest/nflstats_<week>.json = {eventId: {playerId: {team, pos-agnostic stats}}}.
    Separate file and separate pass, so a change in ESPN's layout here can never break the touchdown grading above. Backfills every locked week once."""
    num = lambda v: float(v) if isinstance(v, str) and v.replace('.', '', 1).replace('-', '', 1).isdigit() else v
    for lock in sorted(glob.glob(os.path.join(BT, 'nfl_*.json'))):
        wk = os.path.basename(lock)[4:-5]; path = os.path.join(BT, f'nflstats_{wk}.json')
        out = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
        evs = {r['eventId'] for r in json.load(open(lock, encoding='utf-8'))}; new = 0
        for ev in sorted(evs - set(out)):
            try:
                sm = get("https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/summary", event=ev)
                if sm.get('header', {}).get('competitions', [{}])[0].get('status', {}).get('type', {}).get('completed') is not True: continue
                game = {}
                for team in sm.get('boxscore', {}).get('players', []):
                    ab = team.get('team', {}).get('abbreviation')
                    for cat in team.get('statistics', []):
                        keys = cat.get('keys') or cat.get('labels') or []
                        for a in cat.get('athletes', []):
                            p = game.setdefault(a['athlete']['id'], {'name': a['athlete'].get('displayName'), 'team': ab})
                            for k, v in zip(keys, a.get('stats', [])): p[cat['name'] + '.' + k] = num(v)
                out[ev] = game; new += 1
            except Exception as e: print(f"  stats {wk} {ev}: {type(e).__name__} {e}")
        if new: json.dump(out, open(path, 'w', encoding='utf-8'))
        print(f"NFL stats {wk}: {len(out)}/{len(evs)} games ({new} new)")

if __name__ == '__main__':
    grade_mlb(); grade_nfl()
    try: stats_nfl()
    except Exception as e: print(f"NFL stats failed: {type(e).__name__} {e}")
