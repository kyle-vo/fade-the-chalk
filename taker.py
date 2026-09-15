"""Directional crowd money from Kalshi's trade tape (Robinhood orders route to the same book).
For every locked moneyline game, pull all trades BEFORE first pitch / kickoff on both team markets and credit each trade
to the team the taker (the aggressor who crossed the spread) bet on:
  taker buys YES on team X market  -> money on X   = count * yes_price
  taker buys NO  on team X market  -> money on opp = count * no_price
Adds fields to the locked rows (never removes any): takerHome$, takerAway$, takerPubHome, takerTrades, takerAt.
Cached per game in backtest/taker/<gamekey>.json, so finished games are fetched once.
python taker.py            -> every locked game whose start time has passed or that is within 36h
python taker.py --all      -> also refresh games further out (current partial tape)"""
import os, sys, json, glob, time, datetime, requests
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); CACHE = os.path.join(BT, 'taker'); os.makedirs(CACHE, exist_ok=True)
API = "https://api.elections.kalshi.com/trade-api/v2"
S = requests.Session(); S.headers['User-Agent'] = 'Mozilla/5.0'
J = lambda p: json.load(open(p, encoding='utf-8'))
MON = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')
ALIAS = {'CHW': 'CWS', 'WAS': 'WSH', 'OAK': 'ATH', 'ARI': 'AZ', 'SFG': 'SF', 'SDP': 'SD', 'TBR': 'TB', 'KCR': 'KC', 'JAC': 'JAX', 'LVR': 'LV'}
canon = lambda c: ALIAS.get(c, c)
def f(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0

def get(path, **p):
    for attempt in range(5):
        r = S.get(API + path, params=p, timeout=40)
        if r.status_code == 429: time.sleep(1.5 * (attempt + 1)); continue
        r.raise_for_status(); return r.json()
    r.raise_for_status()

_events = {}
def find_event(sport, home, away, start):
    """locate the Kalshi game event (any status) for this matchup by team codes + date."""
    series = 'KXMLBGAME' if sport == 'MLB' else 'KXNFLGAME'
    d = start.astimezone(datetime.timezone(datetime.timedelta(hours=-4)))              # Kalshi tickers use US Eastern calendar date
    tag = f"{d.strftime('%y')}{MON[d.month - 1]}{d.strftime('%d')}"
    key = (series, tag)
    if key not in _events:
        evs, cursor = [], None
        for status in ('settled', 'closed', 'open'):
            cursor = None
            while True:
                p = {'series_ticker': series, 'status': status, 'limit': 200}
                if cursor: p['cursor'] = cursor
                dd = get('/markets', **p); evs += [m for m in dd.get('markets', []) if tag in m.get('event_ticker', '')]
                cursor = dd.get('cursor')
                if not cursor or status == 'open': break
                if all(tag not in m.get('event_ticker', '') for m in dd.get('markets', [])) and any(m.get('event_ticker', '') < f"{series}-{tag}" for m in dd.get('markets', [])): break
        _events[key] = evs
    mk = {}
    for m in _events[key]:
        side = canon(m['ticker'].rsplit('-', 1)[-1])
        if side in (canon(home), canon(away)) and canon(home) in m['event_ticker'] and canon(away) in m['event_ticker']: mk[side] = m['ticker']
    return mk if canon(home) in mk and canon(away) in mk else None

def tape(ticker, max_ts):
    """sum pre-game trades on one team market by taker direction."""
    yes_d = no_d = 0.0; n = 0; cursor = None
    while True:
        p = {'ticker': ticker, 'limit': 1000, 'max_ts': int(max_ts)}
        if cursor: p['cursor'] = cursor
        d = get('/markets/trades', **p)
        for t in d.get('trades', []):
            c = f(t.get('count_fp')); n += 1
            if t.get('taker_side') == 'yes': yes_d += c * f(t.get('yes_price_dollars'))
            else: no_d += c * f(t.get('no_price_dollars'))
        cursor = d.get('cursor')
        if not cursor or not d.get('trades'): break
    return yes_d, no_d, n

def run(include_future=False):
    now = datetime.datetime.now(datetime.timezone.utc); done = 0
    for lockf in sorted(glob.glob(os.path.join(BT, 'ml_*.json'))):
        rows = J(lockf); changed = False
        for r in rows:
            try: start = datetime.datetime.fromisoformat(r['time'].replace('Z', '+00:00'))
            except Exception: continue
            started = start <= now
            if not started and not include_future and (start - now).total_seconds() > 36 * 3600: continue
            gkey = f"{r['sport']}_{r.get('gamePk') or r.get('eventId')}"; cf = os.path.join(CACHE, gkey + '.json')
            if started and os.path.exists(cf):
                c = J(cf)
            else:
                mk = find_event(r['sport'], r['home'], r['away'], start)
                if not mk: continue
                cut = min(start, now).timestamp()
                hy, hn, n1 = tape(mk[canon(r['home'])], cut); ay, an, n2 = tape(mk[canon(r['away'])], cut)
                home_d = hy + an; away_d = ay + hn                                        # YES on home + NO on away = money on home
                c = {'home': r['home'], 'away': r['away'], 'homeD': round(home_d), 'awayD': round(away_d), 'trades': n1 + n2, 'final': started, 'at': now.isoformat(timespec='minutes'), 'tickers': mk}
                json.dump(c, open(cf, 'w', encoding='utf-8'))
                print(f"  {r['sport']} {r['away']}@{r['home']}: ${home_d:,.0f} on {r['home']} / ${away_d:,.0f} on {r['away']} ({n1 + n2:,} trades){'' if started else '  (partial, game not started)'}")
            tot = c['homeD'] + c['awayD']
            r.update({'takerHome$': c['homeD'], 'takerAway$': c['awayD'], 'takerPubHome': round(c['homeD'] / tot, 3) if tot else None, 'takerTrades': c['trades'], 'takerAt': c['at']})
            changed = True; done += 1
        if changed: json.dump(rows, open(lockf, 'w', encoding='utf-8'))
    print(f"taker tape attached to {done} locked games")

if __name__ == '__main__':
    run('--all' in sys.argv)
