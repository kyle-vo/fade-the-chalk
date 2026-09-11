"""Pull real sportsbook prop odds from The Odds API (free key: https://the-odds-api.com).
Key: put it in odds_key.txt next to this file, or set ODDS_API_KEY.
Writes data/props.json  {sport: {normalized name: {'best': +250, 'books': {'draftkings': +250, ...}}}}
and appends a snapshot to backtest/odds_<date>.json so line movement can be measured (money coming in = crowd)."""
import os, json, sys, datetime, unicodedata, re, requests
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data'); BT = os.path.join(HERE, 'backtest')
os.makedirs(DATA, exist_ok=True); os.makedirs(BT, exist_ok=True)
KEYF = os.path.join(HERE, 'odds_key.txt')
_raw = os.environ.get('ODDS_API_KEYS') or os.environ.get('ODDS_API_KEY') or (open(KEYF).read().strip() if os.path.exists(KEYF) else '')
KEYS = [k.strip() for k in _raw.split(',') if k.strip()]; KEY = KEYS[0] if KEYS else ''
_ki = 0
_rr = os.path.join(DATA, 'odds_key_rr.txt')
try: _ki = (int(open(_rr).read().strip()) + 1) % max(1, len(KEYS))
except Exception: _ki = 0
if KEYS: KEY = KEYS[_ki]; open(_rr, 'w').write(str(_ki))
def rget(url, params, **kw):
    """GET with key rotation: on 401/402/429 (bad, exhausted, throttled) move to the next key."""
    global _ki, KEY
    for _ in range(len(KEYS)):
        params['apiKey'] = KEY
        r = requests.get(url, params=params, timeout=30, **kw)
        if r.status_code in (401, 402, 429):
            print(f"  key #{_ki + 1} {r.status_code}, rotating"); _ki = (_ki + 1) % len(KEYS); KEY = KEYS[_ki]; continue
        return r
    return r
API = "https://api.the-odds-api.com/v4"
REGION = os.environ.get('ODDS_REGION', 'us')         # one region = 1 credit per event per market
BOOKS = os.environ.get('ODDS_BOOKS', '')             # e.g. "draftkings,fanduel" to narrow; blank = all in region
MARKETS = {'MLB': ('baseball_mlb', 'batter_home_runs'), 'NFL': ('americanfootball_nfl', 'player_anytime_td')}
norm = lambda s: re.sub(r'[^a-z ]', '', unicodedata.normalize('NFD', s or '').encode('ascii', 'ignore').decode().lower()).strip()

def pull(sport_key, market, day_filter=None):
    r = rget(f"{API}/sports/{sport_key}/events", {})
    if r.status_code != 200: print(f"  events {sport_key}: {r.status_code} {r.text[:120]}"); return {}
    out = {}; used = 0
    for ev in r.json():
        if day_filter and not day_filter(ev['commence_time']): continue
        p = {'apiKey': KEY, 'regions': REGION, 'markets': market, 'oddsFormat': 'american'}
        if BOOKS: p['bookmakers'] = BOOKS
        o = rget(f"{API}/sports/{sport_key}/events/{ev['id']}/odds", p)
        used = f"{o.headers.get('x-requests-used', '?')} used / {o.headers.get('x-requests-remaining', '?')} left on key #{_ki + 1}"
        if o.status_code != 200: continue
        for bk in o.json().get('bookmakers', []):
            for mk in bk.get('markets', []):
                for oc in mk.get('outcomes', []):
                    if oc.get('name') not in ('Yes', 'Over') and 'point' in oc and oc['point'] != 0.5: continue
                    if oc.get('name') == 'No' or oc.get('name') == 'Under': continue
                    nm = norm(oc.get('description') or oc.get('name'))
                    out.setdefault(nm, {'books': {}, 'game': f"{ev['away_team']} @ {ev['home_team']}"})['books'][bk['key']] = int(oc['price'])
    for v in out.values(): v['best'] = max(v['books'].values())
    print(f"  {sport_key}/{market}: {len(out)} players priced (credits used this month: {used})")
    return out

if __name__ == '__main__':
    if not KEYS:
        print("no odds key - put your The Odds API key in odds_key.txt (free at https://the-odds-api.com). Skipping."); sys.exit(0)
    date = os.environ.get('EDGE_DATE') or datetime.date.today().isoformat()
    cache = os.path.join(DATA, 'props.json'); ttl = int(os.environ.get('ODDS_CACHE_MIN', '90'))
    if os.path.exists(cache) and '--force' not in sys.argv:
        try:
            c = json.load(open(cache, encoding='utf-8')); age = (datetime.datetime.now() - datetime.datetime.fromisoformat(c.get('_at', '2000-01-01T00:00'))).total_seconds() / 60
            if c.get('_date') == date and age < ttl and (c.get('MLB') or c.get('NFL')):
                print(f"odds cache is {age:.0f} min old (limit {ttl}) - reusing, 0 credits. Use --force or ODDS_CACHE_MIN=0 to re-pull."); sys.exit(0)
        except Exception: pass
    # MLB: only that calendar day's games (US Eastern-ish: commence within date .. date+1 05:00Z)
    lo = f"{date}T04:00:00Z"; hi = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat() + "T09:00:00Z"
    props = {'_at': datetime.datetime.now().isoformat(timespec='minutes'), '_date': date, 'MLB': pull(*MARKETS['MLB'], day_filter=lambda t: lo <= t <= hi), 'NFL': pull(*MARKETS['NFL'], day_filter=lambda t: t <= (datetime.date.fromisoformat(date) + datetime.timedelta(days=7)).isoformat())}
    json.dump(props, open(os.path.join(DATA, 'props.json'), 'w', encoding='utf-8'))
    snap_path = os.path.join(BT, f'odds_{date}.json')
    snaps = json.load(open(snap_path, encoding='utf-8')) if os.path.exists(snap_path) else []
    snaps.append({'at': props['_at'], 'MLB': {k: v['best'] for k, v in props['MLB'].items()}, 'NFL': {k: v['best'] for k, v in props['NFL'].items()}, 'books': {sp: {k: v['books'] for k, v in props[sp].items()} for sp in ('MLB', 'NFL')}})
    print(f"key #{_ki + 1} used this run")
    json.dump(snaps, open(snap_path, 'w', encoding='utf-8'))
    print(f"snapshot {len(snaps)} saved for {date}")
