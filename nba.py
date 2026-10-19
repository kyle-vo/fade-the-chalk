"""NBA board data: moneyline, spread and total for today's and tomorrow's games (Pacific dates).
For each game: Robinhood (Kalshi) ask on both sides, Pinnacle's de-vigged fair price at the same line, and the crowd's directional money from
Kalshi's trade tape (each trade credited to the side the taker backed), all frozen at tip-off. Graded from ESPN final scores.
Writes backtest/nba_<date>.json. Rendered by build_nba.py. No model and no backtest yet: the page tracks every read from game one.
Run from lines.py (same workflow step), so it shares that step's Odds API keys; Pinnacle is pulled at most every 90 minutes (3 credits)."""
import os, json, glob, datetime, time, requests
import lines as L
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); DATA = os.path.join(HERE, 'data')
os.makedirs(DATA, exist_ok=True)
J = lambda p: json.load(open(p, encoding='utf-8'))
f = L.f
ESPN = "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
PT = datetime.timezone(datetime.timedelta(hours=-7))
PRE = ('STATUS_SCHEDULED',)
# Kalshi -> ESPN team codes (the board uses ESPN's)
L.ALIAS['NBA'] = {'GSW': 'GS', 'NOP': 'NO', 'NYK': 'NY', 'SAS': 'SA', 'UTA': 'UTAH', 'WAS': 'WSH', 'PHO': 'PHX', 'BRK': 'BKN', 'CHO': 'CHA', 'NOR': 'NO'}
L.HALF_PT[('NBA', 'spread')] = 0.025; L.HALF_PT[('NBA', 'total')] = 0.02
canon = lambda c: L.canon(c, 'NBA')
nick = lambda name: (name or '').split()[-1].lower()                    # 'LA Clippers' / 'Los Angeles Clippers' -> 'clippers'

def espn_games(date):
    d = L.S.get(ESPN, params={'dates': date.replace('-', '')}, timeout=40).json()
    out = []
    for e in d.get('events', []):
        c = e['competitions'][0]; h = next(x for x in c['competitors'] if x['homeAway'] == 'home'); a = next(x for x in c['competitors'] if x['homeAway'] == 'away')
        out.append({'eventId': e['id'], 'date': date, 'time': e['date'], 'state': c['status']['type']['name'], 'completed': c['status']['type'].get('completed'),
                    'home': h['team']['abbreviation'], 'away': a['team']['abbreviation'], 'homeName': h['team']['displayName'], 'awayName': a['team']['displayName'],
                    'scoreHome': f(h.get('score')), 'scoreAway': f(a.get('score'))})
    return out

def pinnacle(need):
    """Pinnacle moneyline, spread and total for every NBA game, cached 90 minutes (3 credits a pull)"""
    cf = os.path.join(DATA, 'nba_pinnacle.json')
    if os.path.exists(cf):
        c = J(cf)
        if time.time() - c.get('at', 0) < 90 * 60 or not need: return c['games']
    if not need or not L.KEYS: return J(cf)['games'] if os.path.exists(cf) else {}
    ki = (datetime.datetime.now().timetuple().tm_yday * 24 + datetime.datetime.now().hour) % len(L.KEYS)
    for a in range(len(L.KEYS)):
        r = L.S.get("https://api.the-odds-api.com/v4/sports/basketball_nba/odds", params={'apiKey': L.KEYS[(ki + a) % len(L.KEYS)], 'markets': 'h2h,spreads,totals', 'bookmakers': 'pinnacle', 'oddsFormat': 'american'}, timeout=40)
        if r.status_code in (401, 402, 429): continue
        break
    if r.status_code != 200: print("  nba pinnacle", r.status_code, r.text[:80]); return J(cf)['games'] if os.path.exists(cf) else {}
    out = {}
    for g in r.json():
        for b in g.get('bookmakers', []):
            if b['key'] != 'pinnacle': continue
            d = {}
            for mk in b.get('markets', []):
                o = {x['name']: x for x in mk['outcomes']}
                if mk['key'] == 'h2h' and g['home_team'] in o and g['away_team'] in o: d['ml'] = (o[g['home_team']]['price'], o[g['away_team']]['price'])
                if mk['key'] == 'spreads' and g['home_team'] in o and g['away_team'] in o: d['spread'] = (f(o[g['home_team']]['point']), o[g['home_team']]['price'], o[g['away_team']]['price'])
                if mk['key'] == 'totals' and 'Over' in o and 'Under' in o: d['total'] = (f(o['Over']['point']), o['Over']['price'], o['Under']['price'])
            out[nick(g['home_team']) + '|' + nick(g['away_team'])] = d
    print(f"  nba pinnacle: {len(out)} games, {r.headers.get('x-requests-last')} credits")
    json.dump({'at': time.time(), 'games': out}, open(cf, 'w', encoding='utf-8')); return out

def strike(ms, side, line, kind):
    """ladder market at Pinnacle's line for this side (Kalshi codes mapped to ESPN's); nearest strike with the most money if none sits exactly there"""
    cands = [m for m in ms if side is None or canon(m['ticker'].rsplit('-', 1)[-1].rstrip('0123456789')) == side]
    exact = [m for m in cands if abs(f(m.get('floor_strike')) - line) < 0.01]
    if exact: return exact[0], 0.0
    near = [m for m in cands if abs(f(m.get('floor_strike')) - line) <= 0.51]
    if not near: return None, 0.0
    m = max(near, key=lambda m: f(m.get('volume_fp'))); return m, f(m.get('floor_strike')) - line

def build_row(g, lad_ml, lad_s, lad_t, pin, now):
    start = datetime.datetime.fromisoformat(g['time'].replace('Z', '+00:00')); cut = min(start, now).timestamp()
    row = {k: g[k] for k in ('eventId', 'date', 'time', 'state', 'home', 'away', 'homeName', 'awayName')}; row['at'] = now.isoformat(timespec='minutes')
    pk = pin.get(nick(g['homeName']) + '|' + nick(g['awayName'])) or {}
    # ---- moneyline: one Kalshi market per team; YES on X and NO on the other team are both money on X ----
    ev, ms = L.find_event(lad_ml, g['home'], g['away'], 'NBA')
    if ms:
        by = {canon(m['ticker'].rsplit('-', 1)[-1]): m for m in ms}
        mh, ma = by.get(g['home']), by.get(g['away'])
        d = {}
        if mh: d['homeAsk'] = round(f(mh.get('yes_ask_dollars')), 3) or None
        if ma: d['awayAsk'] = round(f(ma.get('yes_ask_dollars')), 3) or None
        th = ta = 0.0; n = 0
        for m, mine in ((mh, 'home'), (ma, 'away')):
            if not m: continue
            y, no, k = L.tape(m['ticker'], cut); n += k
            if mine == 'home': th += y; ta += no
            else: ta += y; th += no
        d.update({'tapeHome$': round(th), 'tapeAway$': round(ta), 'tapeTrades': n, 'vol': round(sum(f(m.get('volume_fp')) for m in ms))})
        if pk.get('ml'): fh, fa = L.devig(*pk['ml']); d.update({'pinHome': round(fh, 4), 'pinAway': round(fa, 4)})
        row['ml'] = d
    elif pk.get('ml'):
        fh, fa = L.devig(*pk['ml']); row['ml'] = {'pinHome': round(fh, 4), 'pinAway': round(fa, 4), 'note': 'no Kalshi market found'}
    # ---- spread ----
    ev, ms = L.find_event(lad_s, g['home'], g['away'], 'NBA')
    if pk.get('spread'):
        hp, hprice, aprice = pk['spread']; fav_home = hp < 0; line = abs(hp)
        fair_fav, fair_dog = L.devig(hprice, aprice) if fav_home else L.devig(aprice, hprice)
        fav = g['home'] if fav_home else g['away']; dog = g['away'] if fav_home else g['home']
        d = {'pinLine': line, 'line': line, 'shift': 0.0, 'fav': fav, 'dog': dog, 'pinFavFair': round(fair_fav, 4), 'pinDogFair': round(fair_dog, 4)}
        if ms:
            m, shift = strike(ms, fav, line, 'spread')
            if m:
                if shift: fair_fav -= shift * 2 * L.HALF_PT[('NBA', 'spread')]; d.update({'line': line + shift, 'shift': shift, 'pinFavFair': round(fair_fav, 4), 'pinDogFair': round(1 - fair_fav, 4)})
                ya, yb = f(m.get('yes_ask_dollars')), f(m.get('yes_bid_dollars'))
                y, no, k = L.tape(m['ticker'], cut)
                d.update({'ticker': m['ticker'], 'favAsk': round(ya, 3) or None, 'dogAsk': round(1 - yb, 3) if yb else None, 'vol': round(f(m.get('volume_fp'))), 'ladderVol': round(sum(f(x.get('volume_fp')) for x in ms)),
                          'tapeFav$': round(y), 'tapeDog$': round(no), 'tapeTrades': k})
        row['spread'] = d
    # ---- total ----
    ev, ms = L.find_event(lad_t, g['home'], g['away'], 'NBA')
    if pk.get('total'):
        line, op, up = pk['total']; fo, fu = L.devig(op, up)
        d = {'pinLine': line, 'line': line, 'shift': 0.0, 'pinOverFair': round(fo, 4), 'pinUnderFair': round(fu, 4)}
        if ms:
            m, shift = strike(ms, None, line, 'total')
            if m:
                if shift: fo -= shift * 2 * L.HALF_PT[('NBA', 'total')]; d.update({'line': line + shift, 'shift': shift, 'pinOverFair': round(fo, 4), 'pinUnderFair': round(1 - fo, 4)})
                ya, yb = f(m.get('yes_ask_dollars')), f(m.get('yes_bid_dollars'))
                y, no, k = L.tape(m['ticker'], cut)
                d.update({'ticker': m['ticker'], 'overAsk': round(ya, 3) or None, 'underAsk': round(1 - yb, 3) if yb else None, 'vol': round(f(m.get('volume_fp'))), 'ladderVol': round(sum(f(x.get('volume_fp')) for x in ms)),
                          'tapeOver$': round(y), 'tapeUnder$': round(no), 'tapeTrades': k})
        row['total'] = d
    return row

def merge(old, new):
    """keep anything the new pull lacks; tape dollars only ever go up before tip-off"""
    out = dict(new)
    for k in ('ml', 'spread', 'total'):
        o, n = old.get(k) or {}, new.get(k) or {}
        if o and not n: out[k] = o; continue
        if o and n:
            same_line = o.get('ticker') == n.get('ticker')
            m = dict(o, **{kk: vv for kk, vv in n.items() if vv is not None})
            if same_line:
                for t in ('tapeHome$', 'tapeAway$', 'tapeFav$', 'tapeDog$', 'tapeOver$', 'tapeUnder$', 'tapeTrades', 'vol', 'ladderVol'):
                    if (o.get(t) or 0) > (n.get(t) or 0): m[t] = o[t]
            out[k] = m
    return out

def grade(rows, games):
    byid = {g['eventId']: g for g in games}
    for r in rows:
        g = byid.get(r['eventId'])
        if not g or not g.get('completed') or r.get('final'): continue
        h, a = g['scoreHome'], g['scoreAway']; r['final'] = True; r['finalHome'], r['finalAway'] = h, a; r['homeWin'] = 1 if h > a else 0
        sp = r.get('spread')
        if sp and sp.get('fav'):
            marg = (h - a) if sp['fav'] == r['home'] else (a - h)
            sp['favCovered'] = None if marg == sp['line'] else (1 if marg > sp['line'] else 0)
        to = r.get('total')
        if to: to['over'] = None if h + a == to['line'] else (1 if h + a > to['line'] else 0)

def run():
    now = datetime.datetime.now(datetime.timezone.utc); today = now.astimezone(PT).date()
    dates = [(today + datetime.timedelta(days=i)).isoformat() for i in (-1, 0, 1)]   # yesterday (late finishes to grade), today, tomorrow
    games = {d: espn_games(d) for d in dates}
    upcoming = [g for d in dates[1:] for g in games[d] if g['state'] in PRE]
    if not upcoming and not any(os.path.exists(os.path.join(BT, f'nba_{d}.json')) for d in dates): print("  nba: no games"); return
    soon = any(datetime.datetime.fromisoformat(g['time'].replace('Z', '+00:00')) - now < datetime.timedelta(hours=8) for g in upcoming)
    pin = pinnacle(need=soon)
    lad_ml, lad_s, lad_t = (L.ladder(s) for s in ('KXNBAGAME', 'KXNBASPREAD', 'KXNBATOTAL')) if upcoming else ({}, {}, {})
    for d in dates:
        path = os.path.join(BT, f'nba_{d}.json'); old = {r['eventId']: r for r in J(path)} if os.path.exists(path) else {}
        if not games[d] and not old: continue
        rows = []
        for g in games[d]:
            start = datetime.datetime.fromisoformat(g['time'].replace('Z', '+00:00'))
            o = old.get(g['eventId'])
            if (start <= now or g['state'] not in PRE) and o: rows.append(o); continue           # tipped off: frozen
            if start <= now or g['state'] not in PRE:                                             # first seen after tip-off: keep a bare row so it still grades
                rows.append({k: g[k] for k in ('eventId', 'date', 'time', 'state', 'home', 'away', 'homeName', 'awayName')} | {'lateLock': True}); continue
            try: rows.append(merge(o or {}, build_row(g, lad_ml, lad_s, lad_t, pin, now)))
            except Exception as e: print(f"  nba {g['away']}@{g['home']}: {type(e).__name__} {e}"); o and rows.append(o)
        grade(rows, games[d])
        json.dump(rows, open(path, 'w', encoding='utf-8'))
        miss = [f"{r['away']}@{r['home']}" for r in rows if r['state'] in PRE and not (r.get('ml') or {}).get('tapeTrades') and not r.get('lateLock')]
        print(f"  nba {d}: {len(rows)} games ({sum(1 for r in rows if r.get('final'))} final, {sum(1 for r in rows if (r.get('spread') or {}).get('ticker'))} with a Kalshi spread)" + (f"; no Kalshi moneyline yet: {', '.join(miss)}" if miss else ''))

if __name__ == '__main__':
    run()
