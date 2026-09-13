"""Moneyline board: model win% vs Kalshi/Robinhood (same exchange) vs Fliff vs Pinnacle, with the public money split.
python ml.py            -> fetch + model + lock + grade for today (MLB) and this week (NFL); writes backtest/ml_<date>.json, backtest/mlres_<date>.json
MLB model: regressed run-differential team strength + starting pitcher runs-allowed adjustment + home field, combined log5.
NFL model: 2025 point differential power ratings (regressed) + 2.0 home field -> spread -> win% ; Week 1 only, until 2026 games exist."""
import os, re, json, math, glob, datetime, unicodedata, requests
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data'); BT = os.path.join(HERE, 'backtest')
S = requests.Session(); S.headers['User-Agent'] = 'Mozilla/5.0'
get = lambda u, **p: S.get(u, params=p, timeout=40).json()
J = lambda p: json.load(open(p, encoding='utf-8'))
def f(x, d=0.0):
    try: return float(x)
    except (TypeError, ValueError): return d
def implied(o): return (-o) / (-o + 100) if o < 0 else 100 / (o + 100)
def american(p): p = min(max(p, .01), .99); return round(-100 * p / (1 - p)) if p >= .5 else round(100 * (1 - p) / p)
MON = {m: i for i, m in enumerate(('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'), 1)}
ALIAS = {'CHW': 'CWS', 'WAS': 'WSH', 'OAK': 'ATH', 'ARI': 'AZ', 'SFG': 'SF', 'SDP': 'SD', 'TBR': 'TB', 'KCR': 'KC', 'NYK': 'NYY', 'LA': 'LAD', 'JAC': 'JAX', 'LVR': 'LV'}
canon = lambda c: ALIAS.get(c, c)
_raw = os.environ.get('ODDS_API_KEYS') or (open(os.path.join(HERE, 'odds_key.txt')).read().strip() if os.path.exists(os.path.join(HERE, 'odds_key.txt')) else '')
KEYS = [k.strip() for k in _raw.split(',') if k.strip()]
BOOKS = 'fliff,draftkings,fanduel,betmgm,betrivers,bovada,betonlineag,pinnacle'
RETAIL = ('draftkings', 'fanduel', 'betmgm', 'betrivers', 'fliff'); SHARP = ('pinnacle', 'bovada', 'betonlineag')
today = os.environ.get('EDGE_DATE') or datetime.date.today().isoformat()

# ---------------- market feeds ----------------
def kalshi_games(series):
    out, cursor = {}, None
    while True:
        p = {'series_ticker': series, 'status': 'open', 'limit': 200}
        if cursor: p['cursor'] = cursor
        d = get("https://api.elections.kalshi.com/trade-api/v2/markets", **p)
        for m in d.get('markets', []):
            em = re.match(r'[A-Z]+-(\d\d)([A-Z]{3})(\d\d)(\d{0,4})([A-Z]+)$', m.get('event_ticker', ''))
            if not em: continue
            side = m['ticker'].rsplit('-', 1)[-1]; date = f"20{em.group(1)}-{MON[em.group(2)]:02d}-{em.group(3)}"
            bid, ask = f(m.get('yes_bid_dollars')), f(m.get('yes_ask_dollars')); px = (bid + ask) / 2 if bid and ask else (ask or f(m.get('last_price_dollars')))
            out.setdefault(m['event_ticker'], {'date': date, 'codes': em.group(5), 'sides': {}})['sides'][canon(side)] = {'yes': round(px, 3), 'vol': round(f(m.get('volume_fp'))), 'oi': round(f(m.get('open_interest_fp'))), 'title': m['title']}
        cursor = d.get('cursor')
        if not cursor: break
    return out

def book_ml(sport_key):
    if not KEYS: return {}
    rr = os.path.join(DATA, 'odds_key_rr.txt')
    try: ki = int(open(rr).read().strip())
    except Exception: ki = 0
    r = S.get(f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds", params={'apiKey': KEYS[ki % len(KEYS)], 'markets': 'h2h', 'bookmakers': BOOKS, 'oddsFormat': 'american'}, timeout=40)
    if r.status_code != 200: print("  odds ml", r.status_code, r.text[:100]); return {}
    print(f"  moneylines {sport_key}: {len(r.json())} games, {r.headers.get('x-requests-last')} credit")
    out = {}
    for g in r.json():
        books = {}
        for b in g.get('bookmakers', []):
            for mk in b.get('markets', []):
                if mk['key'] != 'h2h': continue
                pr = {o['name']: o['price'] for o in mk['outcomes']}
                if g['home_team'] in pr and g['away_team'] in pr: books[b['key']] = {'home': pr[g['home_team']], 'away': pr[g['away_team']]}
        out[(g['home_team'], g['away_team'])] = {'books': books, 'commence': g['commence_time']}
    return out

def devig(h, a):
    ph, pa = implied(h), implied(a); s = ph + pa; return ph / s, pa / s
def side_prices(books, side):
    fl = books.get('fliff', {}).get(side); pin = books.get('pinnacle')
    sharp = devig(pin['home'], pin['away'])[0 if side == 'home' else 1] if pin else None
    ret = [devig(b['home'], b['away'])[0 if side == 'home' else 1] for k, b in books.items() if k in RETAIL]
    shp = [devig(b['home'], b['away'])[0 if side == 'home' else 1] for k, b in books.items() if k in SHARP]
    skew = round((sum(ret) / len(ret) - sum(shp) / len(shp)) * 100, 1) if ret and shp else None
    return fl, sharp, skew

# ---------------- MLB model ----------------
def mlb_rows():
    sched = J(os.path.join(DATA, 'mlb_schedule.json')); pit = {p['player']['id']: p['stat'] for p in J(os.path.join(DATA, 'mlb_pitching.json'))}
    st = get("https://statsapi.mlb.com/api/v1/standings", leagueId="103,104", season=today[:4])
    rec = {}
    for d in st.get('records', []):
        for t in d.get('teamRecords', []):
            rec[t['team']['id']] = {'w': t['wins'], 'l': t['losses'], 'rs': t['runsScored'], 'ra': t['runsAllowed']}
    lg_ra9 = 9 * sum(r['ra'] for r in rec.values()) / max(1, sum(r['w'] + r['l'] for r in rec.values())) / 1.0  # runs per team-game ~ (uses games)
    lg_rpg = sum(r['rs'] for r in rec.values()) / max(1, sum(r['w'] + r['l'] for r in rec.values()))
    def strength(tid):
        r = rec.get(tid); g = r['w'] + r['l'] if r else 0
        if not r or g == 0: return 0.5
        pyth = r['rs'] ** 1.83 / (r['rs'] ** 1.83 + r['ra'] ** 1.83)
        return (pyth * g + 0.5 * 60) / (g + 60)                                   # regress toward .500 with 60 games of prior
    def sp_adj(pid):
        """starter quality: regressed ERA vs league, converted to win-prob shift over ~5.5 IP"""
        s = pit.get(pid); ip = 0.0
        if s:
            w, _, rmd = str(s.get('inningsPitched', '0')).partition('.'); ip = f(w) + {'1': 1 / 3, '2': 2 / 3}.get(rmd, 0)
        era = f(s.get('era'), 4.3) if s else 4.3; lg = 4.3
        era_r = (era * ip + lg * 60) / (ip + 60)                                   # regress with 60 IP of league average
        runs_saved = (lg - era_r) / 9 * 5.5                                       # runs vs league over a typical start
        return runs_saved / lg_rpg * 0.5 if lg_rpg else 0                          # ~ each run ≈ 0.1 win prob in MLB scale (rpg≈4.4 -> 0.114)
    kal = kalshi_games('KXMLBGAME'); ml = book_ml('baseball_mlb')
    rows = []
    for g in sched:
        if g.get('officialDate', g['gameDate'][:10]) != today: continue
        h, a = g['teams']['home'], g['teams']['away']; hab, aab = h['team']['abbreviation'], a['team']['abbreviation']
        sh, sa = strength(h['team']['id']), strength(a['team']['id'])
        p_log5 = (sh * (1 - sa)) / (sh * (1 - sa) + sa * (1 - sh))
        hp, ap = h.get('probablePitcher'), a.get('probablePitcher')
        p_home = min(.85, max(.15, p_log5 + 0.04 + (sp_adj(hp['id']) if hp else 0) - (sp_adj(ap['id']) if ap else 0)))
        # kalshi: find event whose codes contain both team codes
        kev = next((v for v in kal.values() if v['date'] == today and canon(hab) in v['sides'] and canon(aab) in v['sides']), None)
        kh = kev['sides'].get(canon(hab)) if kev else None; ka = kev['sides'].get(canon(aab)) if kev else None
        bk = next((v for (hn, an), v in ml.items() if hn == h['team']['name'] and an == a['team']['name']), {'books': {}})
        fl_h, sharp_h, skew_h = side_prices(bk['books'], 'home'); fl_a, sharp_a, skew_a = side_prices(bk['books'], 'away')
        vol = (kh['vol'] if kh else 0) + (ka['vol'] if ka else 0)
        rows.append({'sport': 'MLB', 'gamePk': g['gamePk'], 'date': today, 'time': g['gameDate'], 'state': g['status']['detailedState'], 'venue': g['venue']['name'],
            'home': hab, 'away': aab, 'homeName': h['team']['name'], 'awayName': a['team']['name'], 'homeSP': hp['fullName'] if hp else 'TBD', 'awaySP': ap['fullName'] if ap else 'TBD',
            'homeRec': f"{rec.get(h['team']['id'], {}).get('w', 0)}-{rec.get(h['team']['id'], {}).get('l', 0)}", 'awayRec': f"{rec.get(a['team']['id'], {}).get('w', 0)}-{rec.get(a['team']['id'], {}).get('l', 0)}",
            'model': round(p_home, 4), 'kalshi': kh['yes'] if kh else None, 'kalshiAway': ka['yes'] if ka else None, 'kvol': vol, 'kvolHome': kh['vol'] if kh else 0, 'kvolAway': ka['vol'] if ka else 0,
            'pubHome': round(kh['vol'] / vol, 3) if vol and kh else None, 'fliffHome': fl_h, 'fliffAway': fl_a, 'sharpHome': round(sharp_h, 4) if sharp_h else None, 'skewHome': skew_h,
            'books': bk['books'], 'notes': [f"strength home {sh:.3f} away {sa:.3f} (regressed pythag), log5 {p_log5:.3f}, +.04 home", f"SP adj: home {sp_adj(hp['id']) * 100:+.1f} pts, away {sp_adj(ap['id']) * 100:+.1f} pts" if hp and ap else "SP TBD on at least one side"]})
    return rows

# ---------------- NFL model ----------------
def nfl_rows():
    sb = J(os.path.join(DATA, 'nfl_scoreboard.json')); prev = sb['season']['year'] - 1
    stand = get(f"https://site.api.espn.com/apis/v2/sports/football/nfl/standings", season=prev)
    pf = {}
    for grp in stand.get('children', []):
        for e in grp.get('standings', {}).get('entries', []):
            ab = e['team']['abbreviation']; d = {s['name']: f(s.get('value')) for s in e['stats']}
            gp = d.get('gamesPlayed') or (d.get('wins', 0) + d.get('losses', 0) + d.get('ties', 0)) or 17
            pf[ab] = ((d.get('pointsFor', 0) - d.get('pointsAgainst', 0)) / gp) if gp else 0
    rating = {ab: (m * 17) / (17 + 8) for ab, m in pf.items()}                      # regress point diff/game with 8 games of 0
    kal = kalshi_games('KXNFLGAME'); ml = book_ml('americanfootball_nfl')
    wk = f"{sb['season']['year']}_wk{sb['week']['number']}"; rows = []
    for e in sb['events']:
        c = e['competitions'][0]; home = next(x for x in c['competitors'] if x['homeAway'] == 'home'); away = next(x for x in c['competitors'] if x['homeAway'] == 'away')
        hab, aab = home['team']['abbreviation'], away['team']['abbreviation']
        spread_model = rating.get(hab, 0) - rating.get(aab, 0) + 2.0
        p_home = 0.5 * (1 + math.erf(spread_model / (13.5 * math.sqrt(2))))
        o = (c.get('odds') or [{}])[0]; vegas = o.get('details')
        kev = next((v for v in kal.values() if canon(hab) in v['sides'] and canon(aab) in v['sides']), None)
        kh = kev['sides'].get(canon(hab)) if kev else None; ka = kev['sides'].get(canon(aab)) if kev else None
        bk = next((v for (hn, an), v in ml.items() if hn == home['team']['displayName'] and an == away['team']['displayName']), {'books': {}})
        fl_h, sharp_h, skew_h = side_prices(bk['books'], 'home'); fl_a, _, _ = side_prices(bk['books'], 'away')
        p_rating = p_home
        if sharp_h is not None: p_home = 0.25 * p_rating + 0.75 * sharp_h          # early season: ratings are last year's; anchor to Pinnacle until 2026 games accumulate
        vol = (kh['vol'] if kh else 0) + (ka['vol'] if ka else 0)
        rows.append({'sport': 'NFL', 'eventId': e['id'], 'date': wk, 'time': e['date'], 'state': c['status']['type']['name'], 'venue': '',
            'home': hab, 'away': aab, 'homeName': home['team']['displayName'], 'awayName': away['team']['displayName'], 'homeSP': '', 'awaySP': '', 'homeRec': '', 'awayRec': '',
            'model': round(p_home, 4), 'kalshi': kh['yes'] if kh else None, 'kalshiAway': ka['yes'] if ka else None, 'kvol': vol, 'kvolHome': kh['vol'] if kh else 0, 'kvolAway': ka['vol'] if ka else 0,
            'pubHome': round(kh['vol'] / vol, 3) if vol and kh else None, 'fliffHome': fl_h, 'fliffAway': fl_a, 'sharpHome': round(sharp_h, 4) if sharp_h else None, 'skewHome': skew_h,
            'books': bk['books'], 'notes': [f"2025 point diff ratings: {hab} {rating.get(hab, 0):+.1f}, {aab} {rating.get(aab, 0):+.1f}, +2.0 home -> model spread {hab} {-spread_model:+.1f}", f"Vegas: {vegas}" if vegas else '', f"ratings alone said {p_rating * 100:.0f}% home; blended 25/75 with Pinnacle" if sharp_h is not None else '']})
    return rows

# ---------------- lock + grade ----------------
PRE = ('Scheduled', 'Pre-Game', 'Warmup', 'STATUS_SCHEDULED')
def lock(path, new, key):
    old = J(path) if os.path.exists(path) else []
    started = {r[key] for r in new if r['state'] not in PRE}
    keep = [r for r in old if r[key] in started]; frozen = {r[key] for r in keep}
    out = keep + [r for r in new if r[key] not in frozen and r['state'] in PRE] + [dict(r, lateLock=True) for r in new if r[key] in started and r[key] not in frozen]
    json.dump(out, open(path, 'w', encoding='utf-8')); return len(keep), len(out) - len(keep)

def grade():
    for lockf in sorted(glob.glob(os.path.join(BT, 'ml_*.json'))):
        tag = os.path.basename(lockf)[3:-5]; rp = os.path.join(BT, f'mlres_{tag}.json'); res = J(rp) if os.path.exists(rp) else {}
        rows = J(lockf)
        for r in rows:
            k = str(r.get('gamePk') or r.get('eventId'))
            if k in res: continue
            if r['sport'] == 'MLB':
                sch = get("https://statsapi.mlb.com/api/v1/schedule", sportId=1, gamePk=r['gamePk'])
                g = next((g for d in sch.get('dates', []) for g in d['games']), None)
                if g and g['status']['detailedState'] in ('Final', 'Completed Early', 'Game Over'):
                    res[k] = {'homeWin': 1 if g['teams']['home'].get('isWinner') else 0, 'score': f"{g['teams']['away'].get('score')}-{g['teams']['home'].get('score')}"}
            else:
                sm = get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary", event=r['eventId'])
                comp = sm.get('header', {}).get('competitions', [{}])[0]
                if comp.get('status', {}).get('type', {}).get('completed'):
                    hm = next(x for x in comp['competitors'] if x['homeAway'] == 'home'); aw = next(x for x in comp['competitors'] if x['homeAway'] == 'away')
                    res[k] = {'homeWin': 1 if hm.get('winner') else 0, 'score': f"{aw.get('score')}-{hm.get('score')}"}
        json.dump(res, open(rp, 'w', encoding='utf-8')); print(f"  ML {tag}: {len(res)}/{len(rows)} graded")

if __name__ == '__main__':
    m = mlb_rows(); n = nfl_rows()
    print(f"  ML rows: MLB {len(m)} ({sum(1 for r in m if r['kalshi'] is not None)} on Kalshi, {sum(1 for r in m if r['fliffHome'])} on Fliff) | NFL {len(n)} ({sum(1 for r in n if r['kalshi'] is not None)} on Kalshi)")
    if m: k, fr = lock(os.path.join(BT, f'ml_{today}.json'), m, 'gamePk'); print(f"  ML lock {today}: kept {k}, refreshed {fr}")
    if n: k, fr = lock(os.path.join(BT, f"ml_{n[0]['date']}.json"), n, 'eventId'); print(f"  ML lock {n[0]['date']}: kept {k}, refreshed {fr}")
    # snapshot for movement / analysis
    snapf = os.path.join(BT, f'mlsnap_{today}.json'); snaps = J(snapf) if os.path.exists(snapf) else []
    snaps.append({'at': datetime.datetime.now().isoformat(timespec='minutes'), 'rows': [{k2: r.get(k2) for k2 in ('sport', 'gamePk', 'eventId', 'home', 'away', 'kalshi', 'kalshiAway', 'kvolHome', 'kvolAway', 'fliffHome', 'fliffAway', 'sharpHome', 'skewHome', 'state', 'time')} for r in m + n]})
    json.dump(snaps, open(snapf, 'w', encoding='utf-8'))
    grade()
