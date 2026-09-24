"""Spreads and totals board: no model. Pinnacle's fair price vs Robinhood's (Kalshi) ask at the same line, plus where the crowd's money sits.
For every game on today's MLB lock and the current NFL week lock:
  Pinnacle main spread/total (The Odds API, 2 credits per sport per pull) -> de-vigged fair % for each side
  Kalshi ladder (KXMLBSPREAD/KXMLBTOTAL/KXNFLSPREAD/KXNFLTOTAL, free) -> the strike matching Pinnacle's line: ask for each side, volume, taker tape split
Rows are locked pre-game into backtest/lines_<tag>.json (volumes only ever go up), graded from final scores, and rendered by build_lines.py.
Question this board exists to answer: does the side with more crowd money on spreads and totals cover less than its price says?"""
import os, sys, json, glob, re, time, datetime, requests
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); DATA = os.path.join(HERE, 'data')
S = requests.Session(); S.headers['User-Agent'] = 'Mozilla/5.0'
J = lambda p: json.load(open(p, encoding='utf-8'))
K = "https://api.elections.kalshi.com/trade-api/v2"
f = lambda x: float(x) if x not in (None, '') else 0.0
_raw = os.environ.get('ODDS_API_KEYS') or (open(os.path.join(HERE, 'odds_key.txt')).read().strip() if os.path.exists(os.path.join(HERE, 'odds_key.txt')) else '')
KEYS = [k.strip() for k in _raw.split(',') if k.strip()]
ALIAS = {'MLB': {'CHW': 'CWS', 'WAS': 'WSH', 'OAK': 'ATH', 'ARI': 'AZ', 'SFG': 'SF', 'SDP': 'SD', 'TBR': 'TB', 'KCR': 'KC'}, 'NFL': {'WAS': 'WSH', 'JAC': 'JAX', 'LVR': 'LV', 'LA': 'LAR'}}
canon = lambda c, sp: ALIAS.get(sp, {}).get(c, c)
PRE = ('Scheduled', 'Pre-Game', 'Warmup', 'STATUS_SCHEDULED')
SERIES = {'MLB': ('KXMLBSPREAD', 'KXMLBTOTAL', 'baseball_mlb'), 'NFL': ('KXNFLSPREAD', 'KXNFLTOTAL', 'americanfootball_nfl')}

def kget(path, **p):
    for a in range(5):
        r = S.get(K + path, params=p, timeout=40)
        if r.status_code == 429: time.sleep(1.5 * (a + 1)); continue
        r.raise_for_status(); return r.json()
    r.raise_for_status()

def ladder(series):
    """every open market in the series, grouped by event ticker"""
    out, cur = {}, None
    while True:
        p = {'series_ticker': series, 'status': 'open', 'limit': 200}
        if cur: p['cursor'] = cur
        d = kget('/markets', **p)
        for m in d.get('markets', []): out.setdefault(m['event_ticker'], []).append(m)
        cur = d.get('cursor')
        if not cur: break
    return out

def find_event(lad, home, away, sp):
    """event whose ticker ends with the two team codes (Kalshi uses its own codes: match on both being present after the date)"""
    for ev, ms in lad.items():
        tail = ev.split('-', 1)[1]; tail = re.sub(r'^\d\d[A-Z]{3}\d\d\d*', '', tail)
        if tail == canon(away, sp) + canon(home, sp) or tail == canon(home, sp) + canon(away, sp): return ev, ms
    return None, []

def tape(ticker, max_ts):
    """taker dollars on YES and NO of one market, before max_ts"""
    yes = no = 0.0; n = 0; cur = None
    while True:
        p = {'ticker': ticker, 'limit': 1000, 'max_ts': int(max_ts)}
        if cur: p['cursor'] = cur
        d = kget('/markets/trades', **p)
        for t in d.get('trades', []):
            c = f(t.get('count_fp')); n += 1
            if t.get('taker_side') == 'yes': yes += c * f(t.get('yes_price_dollars'))
            else: no += c * f(t.get('no_price_dollars'))
        cur = d.get('cursor')
        if not cur or not d.get('trades'): break
    return yes, no, n

def pinnacle(sport_key):
    """Pinnacle main spread and total per game: {(home_name, away_name): {'spread': (home_point, home_price, away_price), 'total': (point, over, under)}}"""
    if not KEYS: return {}
    ki = (datetime.datetime.now().timetuple().tm_yday * 24 + datetime.datetime.now().hour) % len(KEYS)
    for a in range(len(KEYS)):
        r = S.get(f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds", params={'apiKey': KEYS[(ki + a) % len(KEYS)], 'markets': 'spreads,totals', 'bookmakers': 'pinnacle', 'oddsFormat': 'american'}, timeout=40)
        if r.status_code in (401, 402, 429): continue
        break
    if r.status_code != 200: print("  pinnacle lines", r.status_code, r.text[:80]); return {}
    print(f"  pinnacle spreads+totals {sport_key}: {len(r.json())} games, {r.headers.get('x-requests-last')} credits")
    out = {}
    for g in r.json():
        for b in g.get('bookmakers', []):
            if b['key'] != 'pinnacle': continue
            d = {}
            for mk in b.get('markets', []):
                o = {x['name']: x for x in mk['outcomes']}
                if mk['key'] == 'spreads' and g['home_team'] in o and g['away_team'] in o: d['spread'] = (f(o[g['home_team']]['point']), o[g['home_team']]['price'], o[g['away_team']]['price'])
                if mk['key'] == 'totals' and 'Over' in o and 'Under' in o: d['total'] = (f(o['Over']['point']), o['Over']['price'], o['Under']['price'])
            out[(g['home_team'], g['away_team'])] = d
    return out

def implied(o): o = float(o); return -o / (-o + 100) if o < 0 else 100 / (o + 100)
def devig(a, b): pa, pb = implied(a), implied(b); s = pa + pb; return pa / s, pb / s
# a half point is worth roughly this much win probability, used only when Pinnacle's line is a whole number and Kalshi only lists half points
HALF_PT = {('NFL', 'spread'): 0.025, ('NFL', 'total'): 0.02, ('MLB', 'spread'): 0.06, ('MLB', 'total'): 0.04}
def pick_strike(ms, side_code, line, sport, kind):
    """the ladder market for this side at Pinnacle's line; if Kalshi has no market there, the nearest strike with the most money, plus how far it moved"""
    cands = [m for m in ms if side_code is None or m['ticker'].rsplit('-', 1)[-1].rstrip('0123456789') == side_code]
    exact = [m for m in cands if abs(f(m.get('floor_strike')) - line) < 0.01]
    if exact: return exact[0], 0.0
    near = [m for m in cands if abs(f(m.get('floor_strike')) - line) <= 0.51]
    if not near: return None, 0.0
    m = max(near, key=lambda m: f(m.get('volume_fp')))
    return m, f(m.get('floor_strike')) - line          # + means Kalshi's line is higher than Pinnacle's

def build(sport, lock_rows, now):
    sp_ser, tot_ser, odds_key = SERIES[sport]
    lad_s, lad_t = ladder(sp_ser), ladder(tot_ser); pin = pinnacle(odds_key)
    rows = []
    for r in lock_rows:
        try: start = datetime.datetime.fromisoformat(r['time'].replace('Z', '+00:00'))
        except Exception: continue
        started = start <= now
        pk = pin.get((r.get('homeName'), r.get('awayName'))) or {}                # lock rows carry the full team names the Odds API uses
        row = {'sport': sport, 'date': r['date'], 'gamePk': r.get('gamePk'), 'eventId': r.get('eventId'), 'home': r['home'], 'away': r['away'], 'time': r['time'], 'state': r.get('state'), 'at': now.isoformat(timespec='minutes')}
        cut = min(start, now).timestamp()
        # ---- spread ----
        ev, ms = find_event(lad_s, r['home'], r['away'], sport)
        if ms and pk.get('spread'):
            hp, hprice, aprice = pk['spread']; fav_home = hp < 0; line = abs(hp)
            fair_fav, fair_dog = devig(hprice, aprice) if fav_home else devig(aprice, hprice)
            fav = r['home'] if fav_home else r['away']; dog = r['away'] if fav_home else r['home']
            m, shift = pick_strike(ms, canon(fav, sport), line, sport, 'spread')
            if shift: fair_fav = fair_fav - shift * 2 * HALF_PT[(sport, 'spread')]; fair_dog = 1 - fair_fav   # a bigger favorite line is harder to cover
            vol = sum(f(x.get('volume_fp')) for x in ms)
            d = {'pinLine': line, 'line': (line + shift) if m else line, 'shift': shift, 'fav': fav, 'dog': dog, 'pinFavFair': round(fair_fav, 4), 'pinDogFair': round(fair_dog, 4), 'ladderVol': round(vol), 'ticker': m['ticker'] if m else None}
            if m:
                ya, yb = f(m.get('yes_ask_dollars')), f(m.get('yes_bid_dollars'))
                d.update({'favAsk': round(ya, 3) if ya else None, 'dogAsk': round(1 - yb, 3) if yb else None, 'vol': round(f(m.get('volume_fp')))})
                y, n, k = tape(m['ticker'], cut); d.update({'tapeFav$': round(y), 'tapeDog$': round(n), 'tapeTrades': k})
            else: d['note'] = 'no Kalshi market at Pinnacle line'
            row['spread'] = d
        # ---- total ----
        ev, ms = find_event(lad_t, r['home'], r['away'], sport)
        if ms and pk.get('total'):
            line, oprice, uprice = pk['total']; fo, fu = devig(oprice, uprice)
            m, shift = pick_strike(ms, None, line, sport, 'total'); vol = sum(f(x.get('volume_fp')) for x in ms)
            if shift: fo = fo - shift * 2 * HALF_PT[(sport, 'total')]; fu = 1 - fo                          # a higher total is harder to go over
            d = {'pinLine': line, 'line': (line + shift) if m else line, 'shift': shift, 'pinOverFair': round(fo, 4), 'pinUnderFair': round(fu, 4), 'ladderVol': round(vol), 'ticker': m['ticker'] if m else None}
            if m:
                ya, yb = f(m.get('yes_ask_dollars')), f(m.get('yes_bid_dollars'))
                d.update({'overAsk': round(ya, 3) if ya else None, 'underAsk': round(1 - yb, 3) if yb else None, 'vol': round(f(m.get('volume_fp')))})
                y, n, k = tape(m['ticker'], cut); d.update({'tapeOver$': round(y), 'tapeUnder$': round(n), 'tapeTrades': k})
            else: d['note'] = 'no Kalshi market at Pinnacle line'
            row['total'] = d
        if 'spread' in row or 'total' in row: rows.append(row)
    return rows

def merge(old, new):
    """pre-game rows refresh (volumes and tape never decrease); started rows are frozen"""
    out = {}
    for r in old: out[str(r.get('gamePk') or r.get('eventId'))] = r
    now = datetime.datetime.now(datetime.timezone.utc)
    for r in new:
        k = str(r.get('gamePk') or r.get('eventId')); o = out.get(k)
        started = datetime.datetime.fromisoformat(r['time'].replace('Z', '+00:00')) <= now
        if o and (started or o.get('frozen')): continue
        if o:
            for mk in ('spread', 'total'):
                if mk in o and mk in r:
                    for fld in ('vol', 'ladderVol', 'tapeFav$', 'tapeDog$', 'tapeOver$', 'tapeUnder$', 'tapeTrades'):
                        if (o[mk].get(fld) or 0) > (r[mk].get(fld) or 0): r[mk][fld] = o[mk][fld]
                elif mk in o: r[mk] = o[mk]
        out[k] = r
    for r in out.values():
        if datetime.datetime.fromisoformat(r['time'].replace('Z', '+00:00')) <= now: r['frozen'] = True
    return list(out.values())

def grade():
    for lf in sorted(glob.glob(os.path.join(BT, 'lines_*.json'))):
        tag = os.path.basename(lf)[6:-5]; rp = os.path.join(BT, f'mlres_{tag}.json')
        if not os.path.exists(rp): continue
        res = J(rp); rows = J(lf); n = 0
        for r in rows:
            g = res.get(str(r.get('gamePk') or r.get('eventId')))
            if not g or not g.get('score') or r.get('graded'): continue
            try: a, h = [int(x) for x in g['score'].split('-')]
            except Exception: continue
            r['finalAway'], r['finalHome'] = a, h
            if 'spread' in r:
                d = r['spread']; margin = (h - a) if d['fav'] == r['home'] else (a - h)
                d['favCovered'] = 1 if margin > d['line'] else 0 if margin < d['line'] else None
            if 'total' in r:
                d = r['total']; d['over'] = 1 if a + h > d['line'] else 0 if a + h < d['line'] else None
            r['graded'] = True; n += 1
        json.dump(rows, open(lf, 'w', encoding='utf-8'))
        if n: print(f"  lines {tag}: graded {n}")

if __name__ == '__main__':
    now = datetime.datetime.now(datetime.timezone.utc); today = os.environ.get('EDGE_DATE') or datetime.date.today().isoformat()
    jobs = []
    mp = os.path.join(BT, f'ml_{today}.json')
    if os.path.exists(mp): jobs.append(('MLB', today, J(mp)))
    wk = sorted(glob.glob(os.path.join(BT, 'ml_2026_wk*.json')))
    if wk: tag = os.path.basename(wk[-1])[3:-5]; jobs.append(('NFL', tag, J(wk[-1])))
    for sport, tag, lock_rows in jobs:
        try: new = build(sport, lock_rows, now)
        except Exception as e: print(f"  lines {sport} failed: {type(e).__name__} {e}"); continue
        lf = os.path.join(BT, f'lines_{tag}.json'); old = J(lf) if os.path.exists(lf) else []
        rows = merge(old, new); json.dump(rows, open(lf, 'w', encoding='utf-8'))
        print(f"  lines {tag}: {len(rows)} games ({sum(1 for r in rows if 'spread' in r)} spreads, {sum(1 for r in rows if 'total' in r)} totals)")
    grade()
