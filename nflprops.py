"""This week's Kalshi (= Robinhood) NFL player-prop lines: anytime TD, receptions, receiving / rushing / passing yards.
For every game on the current week's lock that hasn't kicked off, each open market's ask and bid, refreshed every run and frozen at kickoff.
Writes backtest/nflprops_<week>.json = {eventId: {code, time, at, markets: [{ticker, series, name, strike, ask, bid, vol}]}}.
build_fantasy.py turns these into prop verdicts. Run from lines.py (same workflow step); about 5 Kalshi calls per game."""
import os, json, glob, datetime, re
import lines as L
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest')
SERIES = ('KXNFLTD', 'KXNFLREC', 'KXNFLRECYDS', 'KXNFLRSHYDS', 'KXNFLPASSYDS')
f = L.f

def run():
    locks = sorted(glob.glob(os.path.join(BT, 'nfl_2026_wk*.json')), key=lambda p: int(re.search(r'wk(\d+)', p).group(1)))
    if not locks: return
    wk = os.path.basename(locks[-1])[4:-5]; rows = json.load(open(locks[-1], encoding='utf-8'))
    now = datetime.datetime.now(datetime.timezone.utc)
    games = {}
    for r in rows:
        away, home = re.split(r' @ | VS ', r['game'], maxsplit=1)
        games.setdefault(str(r['eventId']), {'home': home, 'away': away, 'time': r['time']})
    path = os.path.join(BT, f'nflprops_{wk}.json')
    out = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    todo = {ev: g for ev, g in games.items()
            if now < datetime.datetime.fromisoformat(g['time'].replace('Z', '+00:00')) < now + datetime.timedelta(days=4)}
    if not todo: print(f"  nflprops {wk}: no game in the next 4 days"); return
    lad = L.ladder('KXNFLGAME'); n = 0
    for ev, g in todo.items():
        e, _ = L.find_event(lad, g['home'], g['away'], 'NFL')
        if not e: continue
        code = e.split('-', 1)[1]; ms = []
        for s in SERIES:
            try: got = L.kget('/markets', event_ticker=f'{s}-{code}', limit=1000).get('markets', [])
            except Exception as x: print(f"  nflprops {s}-{code}: {type(x).__name__}"); continue
            for m in got:
                t = m.get('title') or ''
                if ':' not in t or m.get('status') not in (None, 'open', 'active'): continue
                ask, bid = f(m.get('yes_ask_dollars')), f(m.get('yes_bid_dollars'))
                if not ask and not bid: continue
                ms.append({'ticker': m['ticker'], 'series': s, 'name': t.split(':')[0].strip(), 'strike': m.get('floor_strike'),
                           'ask': round(ask, 3) or None, 'bid': round(bid, 3) or None, 'vol': round(f(m.get('volume_fp')))})
        if ms: out[ev] = {'code': code, 'time': g['time'], 'at': now.isoformat(timespec='minutes'), 'markets': ms}; n += 1
    json.dump(out, open(path, 'w', encoding='utf-8'))
    print(f"  nflprops {wk}: {n}/{len(todo)} upcoming games priced, {sum(len(v['markets']) for v in out.values())} markets saved")

if __name__ == '__main__':
    run()
