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
            out.setdefault(m['event_ticker'], {'date': date, 'codes': em.group(5), 'sides': {}})['sides'][canon(side)] = {'yes': round(px, 3), 'ask': round(ask, 3) if ask else round(px, 3), 'bid': round(bid, 3), 'vol': round(f(m.get('volume_fp'))), 'oi': round(f(m.get('open_interest_fp'))), 'title': m['title']}
        cursor = d.get('cursor')
        if not cursor: break
    return out

def book_ml(sport_key):
    if not KEYS: return {}
    rr = os.path.join(DATA, 'odds_key_rr.txt')
    try: ki = int(open(rr).read().strip())
    except Exception:                                                # no pointer file on a clean GitHub runner: pick the starting key by the clock, same as odds.py
        _n = datetime.datetime.now(); ki = _n.timetuple().tm_yday * 24 + _n.hour
    for attempt in range(len(KEYS)):                                 # a spent or rejected key must not kill the Pinnacle pull: try the next one
        r = S.get(f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds", params={'apiKey': KEYS[(ki + attempt) % len(KEYS)], 'markets': 'h2h', 'bookmakers': BOOKS, 'oddsFormat': 'american'}, timeout=40)
        if r.status_code in (401, 402, 429): print(f"  odds ml key #{(ki + attempt) % len(KEYS) + 1} {r.status_code}, trying the next key"); continue
        break
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
    ret = [devig(b['home'], b['away'])[0 if side == 'home' else 1] for k, b in books.items() if k in RETAIL]
    shp = [devig(b['home'], b['away'])[0 if side == 'home' else 1] for k, b in books.items() if k in SHARP]
    # Pinnacle when posted; until then the other sharp books (bovada/betonline) stand in so the column is never blank
    sharp = devig(pin['home'], pin['away'])[0 if side == 'home' else 1] if pin else (sum(shp) / len(shp) if shp else None)
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
        rows.append({'sport': 'MLB', 'kalshiAsk': kh['ask'] if kh else None, 'kalshiAwayAsk': ka['ask'] if ka else None, 'gamePk': g['gamePk'], 'date': today, 'time': g['gameDate'], 'state': g['status']['detailedState'], 'venue': g['venue']['name'],
            'home': hab, 'away': aab, 'homeName': h['team']['name'], 'awayName': a['team']['name'], 'homeSP': hp['fullName'] if hp else 'TBD', 'awaySP': ap['fullName'] if ap else 'TBD',
            'homeRec': f"{rec.get(h['team']['id'], {}).get('w', 0)}-{rec.get(h['team']['id'], {}).get('l', 0)}", 'awayRec': f"{rec.get(a['team']['id'], {}).get('w', 0)}-{rec.get(a['team']['id'], {}).get('l', 0)}",
            'model': round(p_home, 4), 'kalshi': kh['yes'] if kh else None, 'kalshiAway': ka['yes'] if ka else None, 'kvol': vol, 'kvolHome': kh['vol'] if kh else 0, 'kvolAway': ka['vol'] if ka else 0, 'koiHome': kh['oi'] if kh else 0, 'koiAway': ka['oi'] if ka else 0,
            'pubHome': round(kh['vol'] / vol, 3) if vol and kh else None, 'fliffHome': fl_h, 'fliffAway': fl_a, 'sharpHome': round(sharp_h, 4) if sharp_h else None, 'sharpSrc': 'pinnacle' if 'pinnacle' in bk['books'] else ('sharp avg' if sharp_h else None), 'skewHome': skew_h,
            'books': bk['books'], 'notes': [f"strength home {sh:.3f} away {sa:.3f} (regressed pythag), log5 {p_log5:.3f}, +.04 home", f"SP adj: home {sp_adj(hp['id']) * 100:+.1f} pts, away {sp_adj(ap['id']) * 100:+.1f} pts" if hp and ap else "SP TBD on at least one side"]})
    return rows

# ---------------- NFL model ----------------
def nfl_rows():
    sb = J(os.path.join(DATA, 'nfl_scoreboard.json')); prev = sb['season']['year'] - 1
    stand = get(f"https://site.web.api.espn.com/apis/v2/sports/football/nfl/standings", season=prev)
    pf = {}
    for grp in stand.get('children', []):
        for e in grp.get('standings', {}).get('entries', []):
            ab = e['team']['abbreviation']; d = {s['name']: f(s.get('value')) for s in e['stats']}
            gp = d.get('gamesPlayed') or (d.get('wins', 0) + d.get('losses', 0) + d.get('ties', 0)) or 17
            pf[ab] = ((d.get('pointsFor', 0) - d.get('pointsAgainst', 0)) / gp) if gp else 0
    prior = {ab: (m * 17) / (17 + 8) for ab, m in pf.items()}                       # 2025 point diff/game, regressed
    # 2026 results so far: every completed regular-season game this season
    cur = {ab: [0.0, 0] for ab in prior}
    for wk in range(1, sb['week']['number'] + 1):
        try: wsb = get("https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard", week=wk, seasontype=2, dates=sb['season']['year'])
        except Exception: continue
        for e in wsb.get('events', []):
            c = e['competitions'][0]
            if not c['status']['type'].get('completed'): continue
            hm = next(x for x in c['competitors'] if x['homeAway'] == 'home'); aw = next(x for x in c['competitors'] if x['homeAway'] == 'away')
            d = f(hm.get('score')) - f(aw.get('score')) - 2.0                         # strip home field
            for ab, sign in ((hm['team']['abbreviation'], 1), (aw['team']['abbreviation'], -1)):
                if ab in cur: cur[ab][0] += sign * d; cur[ab][1] += 1
    # rating = 2026 point diff with the 2025 rating as a 6-game prior; ratings weight in the blend grows with 2026 games played
    rating = {ab: (cur[ab][0] + prior.get(ab, 0) * 6) / (cur[ab][1] + 6) for ab in prior}
    games_played = sum(v[1] for v in cur.values()) / max(1, len(cur))
    W_RATING = min(0.5, 0.05 + 0.06 * games_played)                                   # week 1: 5% ratings / 95% Pinnacle; ~week 8: 50/50
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
        anchor = sharp_h
        if anchor is None and vegas:                                                 # no Pinnacle yet: anchor to the posted spread instead of raw ratings
            m_ = re.match(r'([A-Z]+)\s*([-+]?\d+(?:\.\d+)?)', vegas)
            if m_:
                sp = f(m_.group(2)); sp = sp if m_.group(1) == hab else -sp             # home spread, negative = home favored
                anchor = 0.5 * (1 + math.erf(-sp / (13.5 * math.sqrt(2))))
        if anchor is not None: p_home = W_RATING * p_rating + (1 - W_RATING) * anchor   # ratings earn weight as 2026 games accumulate
        vol = (kh['vol'] if kh else 0) + (ka['vol'] if ka else 0)
        rows.append({'sport': 'NFL', 'kalshiAsk': kh['ask'] if kh else None, 'kalshiAwayAsk': ka['ask'] if ka else None, 'eventId': e['id'], 'date': wk, 'time': e['date'], 'state': c['status']['type']['name'], 'venue': '',
            'home': hab, 'away': aab, 'homeName': home['team']['displayName'], 'awayName': away['team']['displayName'], 'homeSP': '', 'awaySP': '', 'homeRec': '', 'awayRec': '',
            'model': round(p_home, 4), 'kalshi': kh['yes'] if kh else None, 'kalshiAway': ka['yes'] if ka else None, 'kvol': vol, 'kvolHome': kh['vol'] if kh else 0, 'kvolAway': ka['vol'] if ka else 0, 'koiHome': kh['oi'] if kh else 0, 'koiAway': ka['oi'] if ka else 0,
            'pubHome': round(kh['vol'] / vol, 3) if vol and kh else None, 'fliffHome': fl_h, 'fliffAway': fl_a, 'sharpHome': round(sharp_h, 4) if sharp_h else None, 'sharpSrc': 'pinnacle' if 'pinnacle' in bk['books'] else ('sharp avg' if sharp_h else None), 'skewHome': skew_h,
            'books': bk['books'], 'notes': [f"ratings (2026 results + 2025 prior): {hab} {rating.get(hab, 0):+.1f}, {aab} {rating.get(aab, 0):+.1f}, +2.0 home -> rating spread {hab} {-spread_model:+.1f}", f"Vegas: {vegas}" if vegas else '', f"ratings alone said {p_rating * 100:.0f}% home; weight {W_RATING:.0%} ratings / {1 - W_RATING:.0%} {'Pinnacle' if sharp_h is not None else 'Vegas spread'} ({games_played:.1f} games of 2026 data per team)" if anchor is not None else 'no market anchor yet - ratings only']})
    return rows

# ---------------- lock + grade ----------------
PRE = ('Scheduled', 'Pre-Game', 'Warmup', 'STATUS_SCHEDULED')
VOL_FIELDS = ('kvol', 'kvolHome', 'kvolAway', 'koiHome', 'koiAway', 'takerHome$', 'takerAway$', 'takerTrades')   # koi = open interest: contracts still held = dollars actually riding on the game, no churn
CARRY_FIELDS = ('takerPubHome', 'takerAt', 'crowdAt', 'kalshiAsk', 'kalshiAwayAsk', 'sharpHome', 'sharpSrc', 'skewHome', 'fliffHome', 'fliffAway', 'books')
def merge_row(old, new):
    """Refresh a pre-game row without ever losing data: volumes never go down, fields the new pull lacks are carried
    forward from the old row, and prices come from whichever pull saw more money (the later one)."""
    if not old: return new
    out = dict(new)
    for k in VOL_FIELDS:
        if (old.get(k) or 0) > (new.get(k) or 0): out[k] = old[k]
    for k in CARRY_FIELDS:
        if out.get(k) in (None, {}, 0) and old.get(k) not in (None, {}): out[k] = old[k]
    if (old.get('kvol') or 0) > (new.get('kvol') or 0):
        for k in ('kalshi', 'kalshiAway', 'kalshiAsk', 'kalshiAwayAsk'):
            if old.get(k) is not None: out[k] = old[k]
    th, ta = out.get('takerHome$') or 0, out.get('takerAway$') or 0
    if th + ta: out['takerPubHome'] = round(th / (th + ta), 3)
    kh, ka = out.get('kvolHome') or 0, out.get('kvolAway') or 0
    if kh + ka: out['pubHome'] = round(kh / (kh + ka), 3)
    return out
def lock(path, new, key):
    old = J(path) if os.path.exists(path) else []
    now = datetime.datetime.now(datetime.timezone.utc)
    def has_started(r):                                                              # by clock as well as by feed state: a stale schedule file must never let in-game prices into the lock
        try: return r['state'] not in PRE or datetime.datetime.fromisoformat(r['time'].replace('Z', '+00:00')) <= now
        except Exception: return r['state'] not in PRE
    started = {r[key] for r in new if has_started(r)}
    keep = [r for r in old if r[key] in started]; frozen = {r[key] for r in keep}
    prev = {r[key]: r for r in old}
    out = keep + [merge_row(prev.get(r[key], {}), r) for r in new if r[key] not in frozen and not has_started(r)] + [dict(r, lateLock=True) for r in new if r[key] in started and r[key] not in frozen]
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
                sm = get("https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/summary", event=r['eventId'])
                comp = sm.get('header', {}).get('competitions', [{}])[0]
                if comp.get('status', {}).get('type', {}).get('completed'):
                    hm = next(x for x in comp['competitors'] if x['homeAway'] == 'home'); aw = next(x for x in comp['competitors'] if x['homeAway'] == 'away')
                    res[k] = {'homeWin': 1 if hm.get('winner') else 0, 'score': f"{aw.get('score')}-{hm.get('score')}"}
        json.dump(res, open(rp, 'w', encoding='utf-8')); print(f"  ML {tag}: {len(res)}/{len(rows)} graded")

def crowd_refresh():
    """--crowd-only: no Odds API credits. Re-pull Kalshi (Robinhood) prices + money for every locked game that hasn't started, update the lock rows in place, append a snapshot."""
    kal = {'MLB': kalshi_games('KXMLBGAME'), 'NFL': kalshi_games('KXNFLGAME')}
    snap_rows = []; touched = 0
    for lockf in sorted(glob.glob(os.path.join(BT, 'ml_*.json'))):
        rows = J(lockf); changed = False
        for r in rows:
            if r['state'] not in PRE: continue
            try:
                if datetime.datetime.fromisoformat(r['time'].replace('Z', '+00:00')) <= datetime.datetime.now(datetime.timezone.utc): continue   # game started: never overwrite with in-game prices
            except Exception: continue
            kev = next((v for v in kal[r['sport']].values() if canon(r['home']) in v['sides'] and canon(r['away']) in v['sides'] and (r['sport'] == 'NFL' or v['date'] == r['date'])), None)
            if not kev: continue
            kh, ka = kev['sides'].get(canon(r['home'])), kev['sides'].get(canon(r['away']))
            vol = (kh['vol'] if kh else 0) + (ka['vol'] if ka else 0)
            fresh = dict(r); fresh.update({'kalshi': kh['yes'] if kh else None, 'kalshiAsk': kh['ask'] if kh else None, 'kalshiAway': ka['yes'] if ka else None, 'kalshiAwayAsk': ka['ask'] if ka else None,
                      'kvol': vol, 'kvolHome': kh['vol'] if kh else 0, 'kvolAway': ka['vol'] if ka else 0, 'koiHome': kh['oi'] if kh else 0, 'koiAway': ka['oi'] if ka else 0, 'pubHome': round(kh['vol'] / vol, 3) if vol and kh else None, 'crowdAt': datetime.datetime.now().isoformat(timespec='minutes')})
            r.update(merge_row(r, fresh))
            changed = True; touched += 1; snap_rows.append({k2: r.get(k2) for k2 in ('sport', 'gamePk', 'eventId', 'home', 'away', 'kalshi', 'kalshiAway', 'kvolHome', 'kvolAway', 'state', 'time')})
        if changed: json.dump(rows, open(lockf, 'w', encoding='utf-8'))
    snapf = os.path.join(BT, f'mlsnap_{today}.json'); snaps = J(snapf) if os.path.exists(snapf) else []
    snaps.append({'at': datetime.datetime.now().isoformat(timespec='minutes'), 'crowdOnly': True, 'rows': snap_rows}); json.dump(snaps, open(snapf, 'w', encoding='utf-8'))
    print(f"  crowd refresh: {touched} pre-game games updated from Kalshi, 0 credits")

if __name__ == '__main__':
    import sys
    if '--crowd-only' in sys.argv:
        crowd_refresh(); grade(); raise SystemExit
    m = mlb_rows()
    try:
        n = nfl_rows()
    except FileNotFoundError:
        print("  NFL data missing, skipping NFL rows")
        n = []
    print(f"  ML rows: MLB {len(m)} ({sum(1 for r in m if r['kalshi'] is not None)} on Kalshi, {sum(1 for r in m if r['fliffHome'])} on Fliff) | NFL {len(n)} ({sum(1 for r in n if r['kalshi'] is not None)} on Kalshi)")
    if m: k, fr = lock(os.path.join(BT, f'ml_{today}.json'), m, 'gamePk'); print(f"  ML lock {today}: kept {k}, refreshed {fr}")
    if n: k, fr = lock(os.path.join(BT, f"ml_{n[0]['date']}.json"), n, 'eventId'); print(f"  ML lock {n[0]['date']}: kept {k}, refreshed {fr}")
    # snapshot for movement / analysis
    snapf = os.path.join(BT, f'mlsnap_{today}.json'); snaps = J(snapf) if os.path.exists(snapf) else []
    snaps.append({'at': datetime.datetime.now().isoformat(timespec='minutes'), 'rows': [{k2: r.get(k2) for k2 in ('sport', 'gamePk', 'eventId', 'home', 'away', 'kalshi', 'kalshiAway', 'kvolHome', 'kvolAway', 'fliffHome', 'fliffAway', 'sharpHome', 'skewHome', 'state', 'time')} for r in m + n]})
    json.dump(snaps, open(snapf, 'w', encoding='utf-8'))
    try: crowd_refresh()                                                         # tomorrow's (and any other unstarted) locked games keep filling in: Kalshi only, no Odds credits
    except Exception as e: print(f"  crowd refresh failed: {e}")
    try:
        grade()
    except Exception as e:
        print(f"  grading failed (ESPN unreachable): {e}")
