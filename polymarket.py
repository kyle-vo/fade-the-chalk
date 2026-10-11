"""Polymarket moneyline money, the same way taker.py reads Kalshi: every pre-game trade on a game's moneyline market is credited to the
team the bettor backed (BUY team X = money on X; SELL team X = money on the other team at 1 - price). Free public API, no key.

Adds fields to the locked moneyline rows (never removes any): pmHome$, pmAway$, pmPubHome, pmTrades, pmVol, pmAt.
Games are matched by team names and start time. Started games are frozen from a cache (backtest/poly/) so a result never changes them.
"""
import os, sys, json, glob, datetime, requests

HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); CACHE = os.path.join(BT, 'poly')
os.makedirs(CACHE, exist_ok=True)
J = lambda p: json.load(open(p, encoding='utf-8'))
GAMMA = 'https://gamma-api.polymarket.com'; DATA = 'https://data-api.polymarket.com'
S = requests.Session(); S.headers['User-Agent'] = 'Mozilla/5.0 (fade-the-chalk)'


def events(tag, lo, hi):
    """single-game events (slug '<tag>-away-home-date') ending in [lo, hi], with their moneyline market"""
    out = []
    for off in range(0, 20000, 100):
        try:
            ev = S.get(f'{GAMMA}/events', params={'tag_slug': tag, 'limit': 100, 'offset': off, 'end_date_min': lo, 'end_date_max': hi}, timeout=30).json()
        except Exception as e:
            print(f'  polymarket {tag} events failed: {e}'); break
        out += ev
        if len(ev) < 100: break
    games = []
    for e in out:
        if not e.get('slug', '').startswith(tag + '-') or ' - ' in e.get('title', ''): continue
        ml = [m for m in e.get('markets', []) if m.get('sportsMarketType') == 'moneyline']
        if not ml: continue
        m = ml[0]
        try: outcomes = json.loads(m.get('outcomes') or '[]')
        except ValueError: continue
        if len(outcomes) != 2: continue
        st = m.get('gameStartTime') or e.get('endDate')
        st = (st or '').replace(' ', 'T').replace('Z', '+00:00')
        if st.endswith('+00'): st += ':00'
        try: start = datetime.datetime.fromisoformat(st)
        except Exception: continue
        games.append({'slug': e['slug'], 'cid': m['conditionId'], 'outcomes': outcomes, 'start': start, 'vol': m.get('volumeNum') or 0})
    return games


def same_team(outcome, full, abbr):
    o = (outcome or '').lower().strip(); f = (full or '').lower().strip()
    return bool(o) and (o == f or f.endswith(' ' + o) or o == (abbr or '').lower())


def tape(cid, cut_ts, outcomes):
    """pre-game taker dollars by team: {outcome: dollars}, trade count"""
    d = {outcomes[0]: 0.0, outcomes[1]: 0.0}; n = 0; off = 0
    while off <= 20000:
        try: page = S.get(f'{DATA}/trades', params={'market': cid, 'limit': 500, 'offset': off, 'takerOnly': 'true'}, timeout=30).json()
        except Exception as e: print(f'  polymarket trades failed: {e}'); break
        if not page: break
        for t in page:
            if t.get('timestamp', 0) >= cut_ts: continue
            o = t.get('outcome'); other = outcomes[1] if o == outcomes[0] else outcomes[0]
            if o not in d: continue
            size, price = float(t.get('size') or 0), float(t.get('price') or 0)
            if t.get('side') == 'BUY': d[o] += size * price
            else: d[other] += size * (1 - price)
            n += 1
        off += 500
    return d, n


def run(backfill=False):
    """normal run: games from 3 days ago to 8 days ahead. --backfill: every game in every lock file (one-time history pull)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    pools = {}; done = 0
    for lockf in sorted(glob.glob(os.path.join(BT, 'ml_*.json'))):
        if os.path.basename(lockf).startswith('mlboard'): continue
        rows = J(lockf); changed = False
        times = []
        for r in rows:
            try: times.append(datetime.datetime.fromisoformat(r['time'].replace('Z', '+00:00')))
            except Exception: pass
        if not times: continue
        if not backfill and (max(times) < now - datetime.timedelta(days=3) or min(times) > now + datetime.timedelta(days=8)): continue
        lo = (min(times) - datetime.timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z'); hi = (max(times) + datetime.timedelta(days=10)).strftime('%Y-%m-%dT00:00:00Z')   # MLB events carry an end date about a week after first pitch
        for r in rows:
            try: start = datetime.datetime.fromisoformat(r['time'].replace('Z', '+00:00'))
            except Exception: continue
            if not backfill and (start < now - datetime.timedelta(days=3) or start > now + datetime.timedelta(days=8)): continue
            started = start <= now
            gkey = f"{r['sport']}_{r.get('gamePk') or r.get('eventId')}"; cf = os.path.join(CACHE, gkey + '.json')
            if started and os.path.exists(cf) and J(cf).get('final'):
                c = J(cf)
            else:
                pk = (r['sport'], lo, hi)
                if pk not in pools: pools[pk] = events(r['sport'].lower(), lo, hi)
                g = next((g for g in pools[pk] if abs((g['start'] - start).total_seconds()) < 6 * 3600
                          and any(same_team(o, r.get('homeName'), r['home']) for o in g['outcomes'])
                          and any(same_team(o, r.get('awayName'), r['away']) for o in g['outcomes'])), None)
                if not g: continue
                d, n = tape(g['cid'], min(start, now).timestamp(), g['outcomes'])
                ho = next(o for o in g['outcomes'] if same_team(o, r.get('homeName'), r['home'])); ao = g['outcomes'][1] if ho == g['outcomes'][0] else g['outcomes'][0]
                c = {'home': r['home'], 'away': r['away'], 'homeD': round(d[ho]), 'awayD': round(d[ao]), 'trades': n, 'vol': round(g['vol']), 'final': started,
                     'at': now.isoformat(timespec='minutes'), 'slug': g['slug']}
                old = J(cf) if os.path.exists(cf) else {}
                if (old.get('homeD', 0) + old.get('awayD', 0)) > (c['homeD'] + c['awayD']):   # never go down (API hiccup / paging cap)
                    c.update({k: old[k] for k in ('homeD', 'awayD', 'trades')})
                json.dump(c, open(cf, 'w', encoding='utf-8'))
                if not backfill: print(f"  {r['sport']} {r['away']}@{r['home']}: ${c['homeD']:,} on {r['home']} / ${c['awayD']:,} on {r['away']} ({c['trades']:,} trades, ${c['vol']:,} traded){'' if started else '  (partial, game not started)'}")
            tot = c['homeD'] + c['awayD']
            r.update({'pmHome$': c['homeD'], 'pmAway$': c['awayD'], 'pmPubHome': round(c['homeD'] / tot, 3) if tot else None, 'pmTrades': c['trades'], 'pmVol': c.get('vol'), 'pmAt': c['at']})
            changed = True; done += 1
        if changed: json.dump(rows, open(lockf, 'w', encoding='utf-8'))
    print(f'polymarket tape attached to {done} games')


if __name__ == '__main__':
    run('--backfill' in sys.argv)
