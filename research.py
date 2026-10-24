"""One-off data pulls that the hourly job does not need, run by .github/workflows/research.yml (workflow_dispatch). Output lands in research/.
  props <EVENT>   every Kalshi NFL market on one game (TD, yards, receptions, ...): volume, and the crowd's taker $ split pre-kick vs live.
                  EVENT is Kalshi's game code, e.g. 26OCT19WASSF.  -> research/props_<EVENT>.json
  nba_hist        last season's NBA games (2025-26): Kalshi moneyline / main spread / main total price and crowd tape at tip, ESPN result,
                  so the NBA rules can be backtested.  Resumable: re-running continues where it stopped.  -> research/nba_hist_2025.json"""
import os, sys, json, time, datetime, re
import lines as L
import nba
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'research'); os.makedirs(OUT, exist_ok=True)
f = L.f
T0 = time.time(); TRADE_ERR = {}

def _trades(path, ticker, max_ts, split):
    """taker $ on YES / NO, trade count and the last YES price (newest first from max_ts back); with split, trades after it are counted apart as 'live'"""
    pre = {'yes$': 0.0, 'no$': 0.0, 'trades': 0}; live = dict(pre); last = None; cur = None
    while True:
        p = {'ticker': ticker, 'limit': 1000}
        if max_ts: p['max_ts'] = int(max_ts)
        if cur: p['cursor'] = cur
        d = L.kget(path, **p); ts = d.get('trades', [])
        for t in ts:
            c = f(t.get('count_fp') or t.get('count'))
            yp = f(t.get('yes_price_dollars')) or f(t.get('yes_price')) / 100
            np_ = f(t.get('no_price_dollars')) or f(t.get('no_price')) / 100
            at = datetime.datetime.fromisoformat(t['created_time'].replace('Z', '+00:00')).timestamp() if split and t.get('created_time') else 0
            b = live if split and at >= split else pre
            if b is pre and last is None: last = yp
            b['trades'] += 1
            if t.get('taker_side') == 'yes': b['yes$'] += c * yp
            else: b['no$'] += c * np_
        cur = d.get('cursor')
        if not cur or not ts: break
    rd = lambda x: {k: round(v) for k, v in x.items()}
    return rd(pre) | {'lastYes': last} | ({'live': rd(live)} if split else {})

def trades(ticker, max_ts=None, split=None):
    """markets settled before Kalshi's historical cutoff only answer on /historical/trades: try the live path, then the archive"""
    for path in ('/markets/trades', '/historical/trades'):
        try: r = _trades(path, ticker, max_ts, split)
        except Exception as e:
            r = None
            if not TRADE_ERR.get(path): TRADE_ERR[path] = 1; print(f"  trades {path} {ticker}: {type(e).__name__} {str(e)[:90]}")
        if r and (r['trades'] or r.get('live', {}).get('trades')): return r | {'path': path}
    return {'yes$': 0, 'no$': 0, 'trades': 0, 'lastYes': None}

# ---------------------------------------------------------------- props: where the money went on one NFL game
def props(code):
    code = code.strip().upper()
    sers, cur = [], None
    while True:
        p = {'category': 'Sports', 'limit': 1000}
        if cur: p['cursor'] = cur
        try: d = L.kget('/series', **p)
        except Exception as e: print("  /series:", type(e).__name__, str(e)[:80]); break
        sers += [s['ticker'] for s in d.get('series', []) if s['ticker'].startswith('KXNFL')]
        cur = d.get('cursor')
        if not cur or not d.get('series'): break
    sers = sorted(set(sers) | {'KXNFLANYTD', 'KXNFLFIRSTTD', 'KXNFL2TD', 'KXNFLTD', 'KXNFLPASSYDS', 'KXNFLRUSHYDS', 'KXNFLRECYDS', 'KXNFLREC', 'KXNFLPASSTDS', 'KXNFLGAME', 'KXNFLSPREAD', 'KXNFLTOTAL'}); print(f"props {code}: {len(sers)} KXNFL series")
    # kickoff from the NFL lock (ESPN time), so the tape can be split pre-kick vs live
    kick = None
    for path in sorted(os.listdir(os.path.join(HERE, 'backtest'))):
        if not path.startswith('lines_2026'): continue
        for r in json.load(open(os.path.join(HERE, 'backtest', path), encoding='utf-8')):
            if (r.get('spread') or {}).get('ticker', '').split('-')[1:2] == [code]: kick = datetime.datetime.fromisoformat(r['time'].replace('Z', '+00:00')).timestamp()
    print("  kickoff", kick and datetime.datetime.fromtimestamp(kick, datetime.timezone.utc).isoformat())
    ms = []
    for s in sers:
        try: got = L.kget('/markets', event_ticker=f'{s}-{code}', limit=1000).get('markets', [])
        except Exception as e: got = []
        if not got:                                                   # event ticker not '<series>-<code>': look through the series' recent events
            try: got = [m for e in L.kget('/events', series_ticker=s, limit=200, with_nested_markets='true').get('events', []) if code in e['event_ticker'] for m in e.get('markets') or []]
            except Exception as e: got = []
        for m in got: m['_series'] = s; ms.append(m)
    print(f"  {len(ms)} markets on the game")
    ms.sort(key=lambda m: -f(m.get('volume_fp') or m.get('volume')))
    rows = []
    for i, m in enumerate(ms):
        vol = f(m.get('volume_fp') or m.get('volume'))
        row = {'series': m['_series'], 'ticker': m['ticker'], 'title': m.get('title'), 'yes': m.get('yes_sub_title'), 'no': m.get('no_sub_title'),
               'strike': m.get('floor_strike'), 'volume': vol, 'result': m.get('result'), 'status': m.get('status')}
        if vol >= 200 and i < 400 and time.time() - T0 < 50 * 60:
            t = trades(m['ticker'], split=kick); row['live'] = t.pop('live', None); row['pre'] = t
        rows.append(row)
    json.dump({'event': code, 'kickoff': kick, 'markets': rows}, open(os.path.join(OUT, f'props_{code}.json'), 'w', encoding='utf-8'), indent=0)
    for r in rows[:60]:
        pre = r.get('pre') or {}
        print(f"  {r['series']:<18} {(r['title'] or '')[:60]:<60} {r.get('yes') or '':<28} vol {r['volume']:>9,.0f}  pre $Y {pre.get('yes$', 0):>8,} $N {pre.get('no$', 0):>8,}  {r.get('result') or ''}")

# ---------------------------------------------------------------- nba_hist: last season, for the backtest
SEASON = ('2025-10-01', '2026-10-18')                                # 2025 preseason through last season's Finals and this month's preseason
def events(series):
    """every settled event in the series with its markets, live path then historical archive"""
    out = {}
    for path in ('/events', '/historical/events'):
        cur = None
        while True:
            p = {'series_ticker': series, 'status': 'settled', 'with_nested_markets': 'true', 'limit': 200}
            if path != '/events': p.pop('status')
            if cur: p['cursor'] = cur
            try: d = L.kget(path, **p)
            except Exception as e: print(f"  {path} {series}: {type(e).__name__} {str(e)[:80]}"); break
            for e in d.get('events', []):
                if e['event_ticker'] not in out and e.get('markets'): out[e['event_ticker']] = e['markets']
            cur = d.get('cursor')
            if not cur or not d.get('events'): break
        # historical events may come without nested markets: fill from /historical/markets
        print(f"  {series} after {path}: {len(out)} events")
    if True:                                                          # older seasons sit only in Kalshi's archive: always merge it in
        cur = None
        while True:
            p = {'series_ticker': series, 'limit': 1000}
            if cur: p['cursor'] = cur
            try: d = L.kget('/historical/markets', **p)
            except Exception as e: print(f"  /historical/markets {series}: {type(e).__name__} {str(e)[:80]}"); break
            for m in d.get('markets', []):
                if m['ticker'] not in {x['ticker'] for x in out.get(m['event_ticker'], [])}: out.setdefault(m['event_ticker'], []).append(m)
            cur = d.get('cursor')
            if not cur or not d.get('markets'): break
        print(f"  {series} after /historical/markets: {len(out)} events")
    return out

MON = 'JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC'.split()
def code_date(ev):
    m = re.match(r'^[A-Z]+-(\d\d)([A-Z]{3})(\d\d)', ev)
    return m and datetime.date(2000 + int(m.group(1)), MON.index(m.group(2)) + 1, int(m.group(3))).isoformat()

def espn_day(date):
    d = L.S.get(nba.ESPN, params={'dates': date.replace('-', '')}, timeout=40).json(); out = []
    for e in d.get('events', []):
        c = e['competitions'][0]; h = next(x for x in c['competitors'] if x['homeAway'] == 'home'); a = next(x for x in c['competitors'] if x['homeAway'] == 'away')
        if not c['status']['type'].get('completed'): continue
        o = (c.get('odds') or [{}])[0]
        out.append({'eventId': e['id'], 'time': e['date'], 'home': h['team']['abbreviation'], 'away': a['team']['abbreviation'],
                    'scoreHome': f(h.get('score')), 'scoreAway': f(a.get('score')), 'type': (e.get('season') or {}).get('slug'),
                    'espnLine': o.get('details'), 'espnTotal': o.get('overUnder')})
    return out

def nba_hist():
    path = os.path.join(OUT, 'nba_hist_2025.json')
    done = {r['eventId']: r for r in json.load(open(path, encoding='utf-8')) if r.get('ml')} if os.path.exists(path) else {}   # unmatched rows get another try
    lad = {s: events(s) for s in ('KXNBAGAME', 'KXNBASPREAD', 'KXNBATOTAL')}
    bydate = {s: {} for s in lad}
    for s, evs in lad.items():
        for ev, ms in evs.items(): bydate[s].setdefault(code_date(ev), {})[ev] = ms
    print("  kalshi dates:", {s: len(v) for s, v in bydate.items()}, "first/last ML date:", min(bydate['KXNBAGAME'] or ['-']), max(bydate['KXNBAGAME'] or ['-']))
    d0, d1 = (datetime.date.fromisoformat(x) for x in SEASON); day = d0; new = 0
    while day <= d1 and time.time() - T0 < 75 * 60:
        ds = day.isoformat(); day += datetime.timedelta(days=1)
        try: games = espn_day(ds)
        except Exception as e: print(f"  espn {ds}: {e}"); continue
        for g in games:
            if g['eventId'] in done: continue
            tip = datetime.datetime.fromisoformat(g['time'].replace('Z', '+00:00')); et = (tip - datetime.timedelta(hours=4)).date().isoformat()
            r = dict(g, date=ds)
            try:
                ev, ms = L.find_event(bydate['KXNBAGAME'].get(et, {}), g['home'], g['away'], 'NBA')
                if ms:
                    by = {nba.canon(m['ticker'].rsplit('-', 1)[-1]): m for m in ms}; d = {}
                    for side in ('home', 'away'):
                        m = by.get(g[side])
                        if m: d[side] = trades(m['ticker'], tip.timestamp()) | {'ticker': m['ticker'], 'result': m.get('result')}
                    r['ml'] = d
                ev, ms = L.find_event(bydate['KXNBASPREAD'].get(et, {}), g['home'], g['away'], 'NBA')
                if ms:
                    # main line = the strike ESPN's book line points at, else the busiest strike
                    pick = None; mm = re.match(r'^([A-Z]+) -([\d.]+)$', (g.get('espnLine') or '').strip())
                    if mm:
                        fav = nba.canon(mm.group(1)); line = float(mm.group(2))
                        c = [m for m in ms if nba.canon(m['ticker'].rsplit('-', 1)[-1].rstrip('0123456789')) == fav]
                        c = sorted(c, key=lambda m: abs(f(m.get('floor_strike')) - line))
                        if c and abs(f(c[0].get('floor_strike')) - line) <= 1.01: pick = c[0]
                    if not pick: pick = max(ms, key=lambda m: f(m.get('volume_fp') or m.get('volume')))
                    fav = nba.canon(pick['ticker'].rsplit('-', 1)[-1].rstrip('0123456789'))
                    r['spread'] = trades(pick['ticker'], tip.timestamp()) | {'ticker': pick['ticker'], 'fav': fav, 'line': f(pick.get('floor_strike')), 'result': pick.get('result'),
                                                                               'ladderVol': round(sum(f(m.get('volume_fp') or m.get('volume')) for m in ms))}
                ev, ms = L.find_event(bydate['KXNBATOTAL'].get(et, {}), g['home'], g['away'], 'NBA')
                if ms:
                    pick = None
                    if g.get('espnTotal'):
                        c = sorted(ms, key=lambda m: abs(f(m.get('floor_strike')) - f(g['espnTotal'])))
                        if abs(f(c[0].get('floor_strike')) - f(g['espnTotal'])) <= 1.01: pick = c[0]
                    if not pick: pick = max(ms, key=lambda m: f(m.get('volume_fp') or m.get('volume')))
                    r['total'] = trades(pick['ticker'], tip.timestamp()) | {'ticker': pick['ticker'], 'line': f(pick.get('floor_strike')), 'result': pick.get('result')}
            except Exception as e: print(f"  {ds} {g['away']}@{g['home']}: {type(e).__name__} {str(e)[:100]}"); continue
            done[g['eventId']] = r; new += 1
            if new % 25 == 0: json.dump(list(done.values()), open(path, 'w', encoding='utf-8')); print(f"  {ds}: {len(done)} games saved ({time.time() - T0:.0f}s)")
    json.dump(list(done.values()), open(path, 'w', encoding='utf-8'))
    have = lambda k: sum(1 for r in done.values() if r.get(k))
    print(f"nba_hist: {len(done)} games ({new} new), with ML {have('ml')}, spread {have('spread')}, total {have('total')}; stopped at {day}")

# ---------------------------------------------------------------- props_hist: every NFL player-prop market for the season so far
PROP_SERIES = ('KXNFLTD', 'KXNFLFIRSTTD', 'KXNFLREC', 'KXNFLRECYDS', 'KXNFLRSHYDS', 'KXNFLPASSYDS')
def markets_of(params):
    """all markets for a query, live path then the historical archive, de-duplicated by ticker"""
    out = {}
    for path in ('/markets', '/historical/markets'):
        cur = None
        while True:
            p = dict(params, limit=1000)
            if cur: p['cursor'] = cur
            try: d = L.kget(path, **p)
            except Exception as e: break
            for m in d.get('markets', []): out.setdefault(m['ticker'], m)
            cur = d.get('cursor')
            if not cur or not d.get('markets'): break
    return list(out.values())

def props_hist():
    """For each 2026 NFL game already played: every TD / receptions / yards market with its last price before kickoff, the crowd's taker $
    before kickoff and the settlement. One file per week, resumable: research/nflprops_<week>.json"""
    from concurrent.futures import ThreadPoolExecutor
    games = {}
    for path in sorted(os.listdir(os.path.join(HERE, 'backtest'))):
        mm = re.match(r'^nfl_(2026_wk\d+)\.json$', path)
        if not mm: continue
        for r in json.load(open(os.path.join(HERE, 'backtest', path), encoding='utf-8')):
            away, home = re.split(r' @ | VS ', r['game'], maxsplit=1)
            games.setdefault(r['eventId'], {'week': mm.group(1), 'eventId': r['eventId'], 'home': home, 'away': away, 'time': r['time']})
    now = time.time()
    games = {k: g for k, g in games.items() if datetime.datetime.fromisoformat(g['time'].replace('Z', '+00:00')).timestamp() < now - 4 * 3600}
    gm = markets_of({'series_ticker': 'KXNFLGAME'}); lad = {}
    for m in gm: lad.setdefault(m['event_ticker'], []).append(m)
    print(f"props_hist: {len(games)} finished games, {len(lad)} KXNFLGAME events on Kalshi")
    for wk in sorted({g['week'] for g in games.values()}):
        path = os.path.join(OUT, f'nflprops_{wk}.json')
        have = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
        for g in [g for g in games.values() if g['week'] == wk and g['eventId'] not in have]:
            if time.time() - T0 > 80 * 60: break
            kick = datetime.datetime.fromisoformat(g['time'].replace('Z', '+00:00'))
            et = (kick - datetime.timedelta(hours=4)).strftime('%y%b%d').upper()
            sub = {ev: ms for ev, ms in lad.items() if ev.split('-')[1].startswith(et)}
            ev, _ = L.find_event(sub, g['home'], g['away'], 'NFL')
            if not ev: print(f"  {wk} {g['away']}@{g['home']}: no Kalshi event ({et})"); continue
            code = ev.split('-', 1)[1]
            ms = [m for s in PROP_SERIES for m in markets_of({'event_ticker': f'{s}-{code}'})]
            ms = [m for m in ms if f(m.get('volume_fp') or m.get('volume')) >= 50]
            def one(m):
                t = trades(m['ticker'], max_ts=kick.timestamp())
                return {'ticker': m['ticker'], 'series': m['ticker'].split('-')[0], 'title': m.get('title'), 'strike': m.get('floor_strike'),
                        'volume': f(m.get('volume_fp') or m.get('volume')), 'result': m.get('result'), 'pxKick': t.get('lastYes'),
                        'yes$': t['yes$'], 'no$': t['no$'], 'trades': t['trades']}
            with ThreadPoolExecutor(8) as ex: rows = list(ex.map(one, ms))
            have[g['eventId']] = {'code': code, 'home': g['home'], 'away': g['away'], 'time': g['time'], 'markets': rows}
            json.dump(have, open(path, 'w', encoding='utf-8'))
            print(f"  {wk} {code}: {len(rows)} markets, {sum(1 for r in rows if r['pxKick'] is not None)} priced ({time.time() - T0:.0f}s)")
        print(f"{wk}: {len(have)} games saved")

# ---------------------------------------------------------------- books: which bookmaker keys The Odds API serves (for FliffJam's target list)
def books():
    """one moneyline pull per region for NFL and NBA (about 1 credit each): every bookmaker key returned, with how many games it prices.
    Answers which exchanges / apps (Kalshi, Polymarket, Novig, ProphetX, ...) can be FliffJam targets. -> research/odds_api_books.json"""
    out = {}
    for sport in ('americanfootball_nfl', 'basketball_nba'):
        for region in ('us', 'us2', 'us_ex', 'us_dfs', 'eu'):
            r = None
            for k in L.KEYS:
                r = L.S.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds", params={'apiKey': k, 'regions': region, 'markets': 'h2h', 'oddsFormat': 'american'}, timeout=40)
                if r.status_code not in (401, 402, 429): break
            if r is None or r.status_code != 200: print(f"  {sport} {region}: HTTP {getattr(r, 'status_code', None)} {getattr(r, 'text', '')[:80]}"); continue
            c = {}
            for g in r.json():
                for b in g.get('bookmakers', []): c[b['key']] = c.get(b['key'], 0) + 1
            out[f'{sport}|{region}'] = c
            print(f"  {sport} {region}: {c}  (credits left {r.headers.get('x-requests-remaining')})")
    json.dump(out, open(os.path.join(OUT, 'odds_api_books.json'), 'w', encoding='utf-8'), indent=1)

# ---------------------------------------------------------------- props_books: who prices NBA player props on The Odds API
def props_books():
    """one NBA game, points / rebounds / assists, every bookmaker in us, us_ex and eu (about 9 credits): which books carry props,
    so the NBA prop +EV board knows its sharp reference and its bettable venues. -> research/odds_api_prop_books.json"""
    ev = None
    for k in L.KEYS:
        r = L.S.get("https://api.the-odds-api.com/v4/sports/basketball_nba/events", params={'apiKey': k}, timeout=40)
        if r.status_code == 200: ev = r.json(); break
    if not ev: print("no events"); return
    now = datetime.datetime.now(datetime.timezone.utc)
    ev = [e for e in ev if datetime.datetime.fromisoformat(e['commence_time'].replace('Z', '+00:00')) > now]
    e = ev[0]; out = {'event': f"{e['away_team']} @ {e['home_team']}", 'time': e['commence_time'], 'regions': {}}
    for region in ('us', 'us_ex', 'eu'):
        for k in L.KEYS:
            r = L.S.get(f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{e['id']}/odds",
                        params={'apiKey': k, 'regions': region, 'markets': 'player_points,player_rebounds,player_assists', 'oddsFormat': 'american'}, timeout=40)
            if r.status_code not in (401, 402, 429): break
        if r.status_code != 200: print(region, r.status_code, r.text[:100]); continue
        c = {}
        for b in r.json().get('bookmakers', []):
            c[b['key']] = {m['key']: len(m['outcomes']) for m in b.get('markets', [])}
        out['regions'][region] = c
        print(f"  {region}: {c}  (credits left on that key {r.headers.get('x-requests-remaining')}, used {r.headers.get('x-requests-last')})")
    json.dump(out, open(os.path.join(OUT, 'odds_api_prop_books.json'), 'w', encoding='utf-8'), indent=1)

if __name__ == '__main__':
    job = sys.argv[1] if len(sys.argv) > 1 else ''
    arg = sys.argv[2] if len(sys.argv) > 2 else ''
    if job == 'props': props(arg or '26OCT19WASSF')
    elif job == 'nba_hist': nba_hist()
    elif job == 'props_hist': props_hist()
    elif job == 'books': books()
    elif job == 'props_books': props_books()
    else: print("unknown job", job)
