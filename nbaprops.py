"""NBA player props vs the sharp price, for the +EV page (ev.py reads what this saves).

For every NBA game tipping within the next 3 hours, one Odds API call (all books in one request, so about 1 credit per market:
4 credits a game) pulls points / rebounds / assists / threes from:
  sharp  : Pinnacle (de-vigged with the power method, which doesn't overrate longshots); if Pinnacle doesn't list the player,
           the median de-vigged price of BetOnline / FanDuel / DraftKings (marked 'consensus', less trustworthy)
  venues : Novig, ProphetX, Polymarket (exchanges), Bovada, BetOnline, FanDuel, DraftKings
Each game is pulled again at most every 75 minutes, so the last pull before tip doubles as the closing line.
Writes backtest/nbaprops_<date>.json = {eventId: {at, time, game, books: {book: [[player, market, side, line, american], ...]}}}.
Kalshi's player props are not on The Odds API; Kalshi stays on game lines (ev.py)."""
import os, json, datetime, time
import lines as L
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest')
MARKETS = 'player_points,player_rebounds,player_assists,player_threes'
BOOKS = 'pinnacle,novig,prophetx,polymarket,bovada,betonlineag,fanduel,draftkings'
SPORT = 'basketball_nba'

def get(url, **p):
    for k in L.KEYS:
        r = L.S.get(url, params=dict(p, apiKey=k), timeout=40)
        if r.status_code in (401, 402, 429): continue
        return r
    return None

def run():
    if not L.KEYS: return
    now = datetime.datetime.now(datetime.timezone.utc)
    pt = (now - datetime.timedelta(hours=7)).date().isoformat()
    path = os.path.join(BT, f'nbaprops_{pt}.json'); saved = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    r = get(f"https://api.the-odds-api.com/v4/sports/{SPORT}/events")                    # free: no credits
    if r is None or r.status_code != 200: print("  nbaprops: events", getattr(r, 'status_code', None)); return
    soon = [e for e in r.json() if timedelta_ok(e['commence_time'], now)]
    pulled = 0
    for e in soon:
        old = saved.get(e['id'])
        if old and (now - datetime.datetime.fromisoformat(old['at'])).total_seconds() < 75 * 60: continue
        r = get(f"https://api.the-odds-api.com/v4/sports/{SPORT}/events/{e['id']}/odds", markets=MARKETS, bookmakers=BOOKS, oddsFormat='american')
        if r is None or r.status_code != 200: print("  nbaprops odds", e['id'], getattr(r, 'status_code', None)); continue
        books = {}
        for b in r.json().get('bookmakers', []):
            rows = books.setdefault(b['key'], [])
            for m in b.get('markets', []):
                for o in m.get('outcomes', []):
                    if o.get('point') is None or o.get('description') is None: continue
                    rows.append([o['description'], m['key'], o['name'], o['point'], o['price']])
        saved[e['id']] = {'at': now.isoformat(timespec='minutes'), 'time': e['commence_time'], 'game': f"{e['away_team']} @ {e['home_team']}", 'books': books}
        pulled += 1; time.sleep(0.3)
    json.dump(saved, open(path, 'w', encoding='utf-8'))
    print(f"  nbaprops {pt}: {pulled} games pulled now, {len(saved)} saved ({len(soon)} tipping within 3h)")
    try: box_scores()
    except Exception as e: print(f"  nbabox failed: {type(e).__name__} {e}")

def box_scores():
    """ESPN box scores for finished NBA games on dates we priced props for: backtest/nbabox_<date>.json = {player name: {pts, reb, ast, 3PM}}"""
    import glob, re
    for pp in sorted(glob.glob(os.path.join(BT, 'nbaprops_*.json')))[-3:]:
        d = pp[-15:-5]; bp = os.path.join(BT, f'nbabox_{d}.json'); box = json.load(open(bp, encoding='utf-8')) if os.path.exists(bp) else {}
        done = set(box.get('_games', [])); new = 0
        sb = L.S.get("https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard", params={'dates': d.replace('-', '')}, timeout=40).json()
        for e in sb.get('events', []):
            if e['id'] in done or not e['competitions'][0]['status']['type'].get('completed'): continue
            sm = L.S.get("https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/summary", params={'event': e['id']}, timeout=40).json()
            for team in sm.get('boxscore', {}).get('players', []):
                for st in team.get('statistics', []):
                    keys = st.get('keys') or []
                    for a in st.get('athletes', []):
                        v = dict(zip(keys, a.get('stats', [])))
                        if not v or a.get('didNotPlay'): continue
                        num = lambda x: float(x) if re.fullmatch(r'-?\d+(\.\d+)?', str(x or '')) else 0.0
                        three = str(v.get('threePointFieldGoalsMade-threePointFieldGoalsAttempted', '0-0')).split('-')[0]
                        box[a['athlete']['displayName']] = {'player_points': num(v.get('points')), 'player_rebounds': num(v.get('rebounds')),
                                                            'player_assists': num(v.get('assists')), 'player_threes': num(three)}
            box.setdefault('_games', []).append(e['id']); new += 1
        if new: json.dump(box, open(bp, 'w', encoding='utf-8')); print(f"  nbabox {d}: {new} games added")

def timedelta_ok(t, now):
    s = datetime.datetime.fromisoformat(t.replace('Z', '+00:00'))
    return now < s <= now + datetime.timedelta(hours=3)

# ---- pricing, used by ev.py
def devig_power(p_over, p_under):
    """power method: find k with p_over^k + p_under^k = 1 (removes more vig from the longshot side than the proportional method)"""
    lo, hi = 0.5, 3.0
    for _ in range(60):
        k = (lo + hi) / 2; s = p_over ** k + p_under ** k
        if s > 1: lo = k
        else: hi = k
    return p_over ** k, p_under ** k

imp = lambda a: 100 / (a + 100) if a > 0 else -a / (-a + 100)

def fair_prices(books):
    """{(player, market, line): (fair_over, fair_under, source)} from Pinnacle, else the median of BetOnline / FanDuel / DraftKings"""
    def pairs(rows):
        d = {}
        for pl, mk, side, line, price in rows: d.setdefault((pl, mk, line), {})[side] = price
        return {k: v for k, v in d.items() if 'Over' in v and 'Under' in v}
    out = {}
    for k, v in pairs(books.get('pinnacle', [])).items():
        fo, fu = devig_power(imp(v['Over']), imp(v['Under'])); out[k] = (fo, fu, 'pinnacle')
    cons = {}
    for bk in ('betonlineag', 'fanduel', 'draftkings'):
        for k, v in pairs(books.get(bk, [])).items():
            if k in out: continue
            cons.setdefault(k, []).append(devig_power(imp(v['Over']), imp(v['Under']))[0])
    for k, fos in cons.items():
        if len(fos) >= 2:
            fo = sorted(fos)[len(fos) // 2]; out[k] = (fo, 1 - fo, 'consensus')
    return out

LABEL = {'player_points': 'pts', 'player_rebounds': 'reb', 'player_assists': 'ast', 'player_threes': '3PM'}

if __name__ == '__main__':
    run()
