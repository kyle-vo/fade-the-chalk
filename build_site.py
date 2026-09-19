"""Build the static site into docs/ (GitHub Pages):
  index.html          today's board (MLB + NFL tabs)
  days/<date>.html    a past MLB slate with results graded in
  nfl/<week>.html     an NFL week with results graded in
  track.html          paper-bet ledger (bets live in your browser) + model strategies scored at fair odds
"""
import json, os, glob, datetime, math
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs')
for d in ('', 'days', 'nfl'): os.makedirs(os.path.join(SITE, d), exist_ok=True)
J = lambda p: json.load(open(p, encoding='utf-8'))
jd = lambda o: json.dumps(o).replace('</', '<' + chr(92) + '/')
board = J(os.path.join(HERE, 'output', 'board.json'))
today = (board['mlb'][0].get('date') or board['mlb'][0]['time'][:10]) if board['mlb'] else datetime.date.today().isoformat()

# ---------- assemble history ----------
days = {}
for lock in sorted(glob.glob(os.path.join(BT, 'pred_*.json'))):
    date = os.path.basename(lock)[5:15]; rows = J(lock)
    rp = os.path.join(BT, f'res_{date}.json'); res = J(rp) if os.path.exists(rp) else {}
    graded_games = set(res.get('_games', []))
    for r in rows:
        r['date'] = date
        g = res.get(str(r['id']))
        if r.get('gamePk') in graded_games or (g is not None and not r.get('gamePk')):
            if g and g['pa'] > 0: r['hit'] = 1 if g['hr'] > 0 else 0; r['actual'] = g['hr']; r['actualPA'] = g['pa']
            else: r['hit'] = None; r['dnp'] = True
        else: r['hit'] = None
    days[date] = rows
weeks = {}
for lock in sorted(glob.glob(os.path.join(BT, 'nfl_*.json'))):
    wk = os.path.basename(lock)[4:-5]; rows = J(lock)
    rp = os.path.join(BT, f'nflres_{wk}.json'); res = J(rp) if os.path.exists(rp) else {}
    graded_games = set(res.get('_games', []))
    for r in rows:
        r['date'] = wk
        if r['eventId'] in graded_games:
            g = res.get(str(r['id']))
            if g: r['hit'] = 1 if g['td'] > 0 else 0; r['actual'] = g['td']
            else: r['hit'] = 0; r['actual'] = 0; r['dnp'] = True   # on roster, no touches
        else: r['hit'] = None
    weeks[wk] = rows
import unicodedata, re as _re
_norm = lambda x: _re.sub(r'[^a-z ]', '', unicodedata.normalize('NFD', x or '').encode('ascii', 'ignore').decode().lower()).strip()
def _implied(o): return (-o) / (-o + 100) if o < 0 else 100 / (o + 100)
PUBLIC_BOOKS = ('draftkings', 'fanduel', 'betmgm', 'espnbet', 'fanatics', 'williamhill_us', 'betrivers')
SHARP_BOOKS = ('bovada', 'betonlineag', 'pinnacle', 'lowvig', 'betus', 'mybookieag')
def book_skew(books):
    """retail implied % minus offshore implied %: positive = public books are shorter = the crowd is on him."""
    pub = [_implied(o) for b, o in books.items() if b in PUBLIC_BOOKS]; shp = [_implied(o) for b, o in books.items() if b in SHARP_BOOKS]
    if not pub or not shp: return None
    return round(max(-5.0, min(5.0, (sum(pub) / len(pub) - sum(shp) / len(shp)) * 100)), 1)   # capped: a stale book is not the crowd
_LOCALTZ = datetime.datetime.now().astimezone().tzinfo
def _snap_utc(at): return datetime.datetime.fromisoformat(at).replace(tzinfo=_LOCALTZ).astimezone(datetime.timezone.utc)
def _start_utc(r):
    t = r.get('time') or ''
    try: return datetime.datetime.fromisoformat(t.replace('Z', '+00:00'))
    except ValueError: return None
def _pregame(snaps, r):
    """only snapshots taken before this player's game started (in-game prices are contaminated by the outcome)"""
    st = _start_utc(r)
    return [sn for sn in snaps if st is None or _snap_utc(sn['at']) <= st]   # nothing pre-game = no crowd number (never leak an in-game price)
def attach_odds(rows, date, sport):
    """Book odds from the latest snapshot of that date (closing line), movement vs the first snapshot -> heat bump."""
    if sport == 'NFL':
        # Touchdown props are pulled only three times a week (odds.py NFL_WINDOWS), so read the whole week's snapshots, oldest first, instead of today's file.
        snaps = []
        for back in range(8, -1, -1):
            fp = os.path.join(BT, f"odds_{(datetime.date.today() - datetime.timedelta(days=back)).isoformat()}.json")
            if os.path.exists(fp): snaps += [sn for sn in J(fp) if sn.get('NFL')]
        if not snaps: return
    else:
        sp = os.path.join(BT, f'odds_{date}.json')
        if not os.path.exists(sp): return
        snaps = J(sp)
    def usable(r):
        pre = _pregame(snaps, r)
        if sport != 'NFL': return pre
        # a snapshot prices a player's NEXT game, so only count ones taken after his previous game: within 3.5 days of a Thursday kickoff, 5.5 days otherwise
        st = _start_utc(r)
        if st is None: return pre
        lim = (3.5 if st.weekday() in (3, 4) else 5.5) * 86400
        return [sn for sn in pre if (st - _snap_utc(sn['at'])).total_seconds() <= lim]
    for r in rows:
        nm = _norm(r['name']); first, last, lastbooks = {}, {}, {}; use = usable(r)
        for sn in use:                                 # latest PRE-GAME sighting wins; first sighting = the opener
            for k2, o in sn.get(sport, {}).items():
                first.setdefault(k2, o); last[k2] = o; lastbooks[k2] = sn.get('books', {}).get(sport, {}).get(k2, lastbooks.get(k2, {}))
        o = last.get(nm)
        if o is None: continue
        r['book'] = o
        bks = lastbooks.get(nm, {})
        r['onFliff'] = 'fliff' in bks
        r['bookUsed'] = 'fliff' if 'fliff' in bks else 'underdog' if 'underdog' in bks else 'best'
        if bks: r['bestBook'] = max(bks.values()); r['bestAt'] = max(bks, key=bks.get)
        sk = book_skew(bks)
        if sk is not None:
            r['skew'] = sk
            r['heat'] = round(min(100, max(0, r['heat'] + (12 if sk >= 2.5 else 6 if sk >= 1.2 else -6 if sk <= -1.2 else 0))))
            r.setdefault('notes', []).append(f"book skew {sk:+.1f} pts (retail books vs offshore; + = public money on him)")
        if nm in first and len(use) > 1:
            mv = (_implied(o) - _implied(first[nm])) * 100   # + = price shortened = money came in
            r['move'] = round(mv, 1)
            r['heat'] = round(min(100, max(0, r['heat'] + (15 if mv >= 3 else 8 if mv >= 1.5 else -8 if mv <= -1.5 else 0))))
            r.setdefault('notes', []).append(f"line moved {first[nm]:+d} -> {o:+d} ({mv:+.1f} pts implied)")
def attach_kalshi(rows, date, sport):
    """Kalshi = the public's own price with money behind it. yes price -> crowd %; volume -> how many are on him."""
    kp = os.path.join(BT, f'kalshi_{sport.lower()}_{date}.json')
    if not os.path.exists(kp): return
    snaps = J(kp)
    allv = sorted(v['vol'] for sn in snaps for v in sn['markets'].values()); top = allv[int(len(allv) * 0.75)] if allv else 0
    for r in rows:
        ms, first = {}, {}
        for sn in _pregame(snaps, r):                  # last PRE-GAME price and volume; in-game prices know the outcome
            for nm, m in sn['markets'].items(): first.setdefault(nm, m); ms[nm] = m
        k = ms.get(_norm(r['name']))
        if not k: continue
        r['kalshi'] = k['yes']; r['kvol'] = k['vol']; r['koi'] = k['oi']
        ask = k.get('ask') or (k['yes'] + 0.01)
        if 0 < ask < 1:
            r['sportsbook'] = r.get('book'); r['book'] = round(-100 * ask / (1 - ask)) if ask >= .5 else round(100 * (1 - ask) / ask); r['bookUsed'] = 'robinhood'; r['onFliff'] = False
        gap = (k['yes'] - r['prob']) * 100                      # crowd above the model = they love him more than the numbers do
        bump = (12 if gap >= 6 else 6 if gap >= 3 else -6 if gap <= -3 else 0) + (10 if k['vol'] >= top and k['vol'] > 0 else 0)
        if _norm(r['name']) in first and len(snaps) > 1:
            km = (k['yes'] - first[_norm(r['name'])]['yes']) * 100; r['kmove'] = round(km, 1); bump += 8 if km >= 3 else -5 if km <= -3 else 0
        r['heat'] = round(min(100, max(0, r['heat'] + bump)))
        r.setdefault('notes', []).append(f"Kalshi: crowd says {k['yes'] * 100:.0f}% (model {r['prob'] * 100:.0f}%), ${k['vol']:,} traded" + (f", moved {r['kmove']:+.1f} pts" if 'kmove' in r else ''))
def attach_team_money(rows, date):
    """Inputs for the home-run verdict. The moneyline lock is frozen at first pitch, so nothing in-game leaks in.
    teamPub = share of the Kalshi/Robinhood MONEYLINE dollars on this hitter's team; teamFav = his team is the priced favorite;
    big = top third of that day's priced hitters by Kalshi home-run dollars (recomputed every build, so it works at 9am and at 4pm)."""
    mp = os.path.join(BT, f'ml_{date}.json')
    games = {str(g.get('gamePk')): g for g in J(mp)} if os.path.exists(mp) else {}
    vols = sorted(r['kvol'] for r in rows if r.get('kvol') and r.get('kalshi'))
    cut = vols[2 * len(vols) // 3] if len(vols) >= 9 else None
    for r in rows:
        r['big'] = bool(cut and r.get('kvol') and r.get('kalshi') and r['kvol'] >= cut)
        g = games.get(str(r.get('gamePk')))
        if not g or r.get('team') not in (g.get('home'), g.get('away')): continue
        home = r['team'] == g['home']
        if g.get('pubHome') is not None: r['teamPub'] = round(g['pubHome'] if home else 1 - g['pubHome'], 3)
        kh, ka = g.get('kalshi'), g.get('kalshiAway')
        if kh is not None:
            pr = kh if home else (ka if ka is not None else 1 - kh); r['teamPrice'] = round(pr, 3); r['teamFav'] = pr >= 0.5

def attach_kalshi_nfl(rows):
    """NFL rows span several dates in a week; merge every kalshi_nfl_<date>.json whose date falls in the week, per-player pre-game price."""
    import glob as _g
    files = sorted(_g.glob(os.path.join(BT, 'kalshi_nfl_*.json')))
    if not files or not rows: return
    times = [r['time'][:10] for r in rows if r.get('time')]
    lo, hi = min(times), max(times)
    snaps = []
    for fp in files:
        d = os.path.basename(fp)[11:21]
        if lo[:10] <= d <= hi[:10] or (datetime.date.fromisoformat(lo) - datetime.timedelta(days=1)).isoformat() <= d <= (datetime.date.fromisoformat(hi) + datetime.timedelta(days=1)).isoformat():
            snaps += J(fp)
    if not snaps: return
    snaps.sort(key=lambda sn: sn['at'])
    allv = sorted(v['vol'] for sn in snaps for v in sn['markets'].values()); top = allv[int(len(allv) * 0.75)] if allv else 0
    for r in rows:
        ms, first = {}, {}
        for sn in _pregame(snaps, r):
            for nm, m in sn['markets'].items(): first.setdefault(nm, m); ms[nm] = m
        k = ms.get(_norm(r['name']))
        if not k: continue
        r['kalshi'] = k['yes']; r['kvol'] = k['vol']; r['koi'] = k['oi']
        ask = k.get('ask') or (k['yes'] + 0.01)
        if 0 < ask < 1:
            r['sportsbook'] = r.get('book'); r['book'] = round(-100 * ask / (1 - ask)) if ask >= .5 else round(100 * (1 - ask) / ask); r['bookUsed'] = 'robinhood'; r['onFliff'] = False
        gap = (k['yes'] - r['prob']) * 100
        bump = (12 if gap >= 6 else 6 if gap >= 3 else -6 if gap <= -3 else 0) + (10 if k['vol'] >= top and k['vol'] > 0 else 0)
        if _norm(r['name']) in first and len(snaps) > 1:
            km = (k['yes'] - first[_norm(r['name'])]['yes']) * 100; r['kmove'] = round(km, 1); bump += 8 if km >= 3 else -5 if km <= -3 else 0
        r['heat'] = round(min(100, max(0, r['heat'] + bump)))
        r.setdefault('notes', []).append(f"Kalshi/Robinhood: crowd says {k['yes'] * 100:.0f}% (model {r['prob'] * 100:.0f}%), ${k['vol']:,} traded" + (f", moved {r['kmove']:+.1f} pts" if 'kmove' in r else ''))
for _d, _rows in days.items(): attach_odds(_rows, _d, 'MLB'); attach_kalshi(_rows, _d, 'MLB'); attach_team_money(_rows, _d)
for _w, _rows in weeks.items(): attach_odds(_rows, today, 'NFL'); attach_kalshi_nfl(_rows)
attach_odds(board['nfl'], today, 'NFL'); attach_kalshi_nfl(board['nfl']); attach_odds(board['mlb'], today, 'MLB'); attach_kalshi(board['mlb'], today, 'MLB'); attach_team_money(board['mlb'], today)
slim = lambda r: {k: r.get(k) for k in ('sport', 'id', 'name', 'team', 'game', 'time', 'prob', 'fair', 'heat', 'hit', 'actual', 'dnp', 'date', 'pos', 'slot', 'lineupPosted', 'lateLock', 'book', 'move', 'skew', 'onFliff', 'bookUsed', 'bestBook', 'bestAt', 'kalshi', 'kvol', 'kmove', 'sportsbook', 'big', 'teamPub', 'teamFav', 'probRaw')}
HISTORY = [slim(r) for rows in days.values() for r in rows] + [slim(r) for rows in weeks.values() for r in rows]
_mlb = os.path.join(BT, 'mlboard.json'); MLH = json.load(open(_mlb, encoding='utf-8')) if os.path.exists(_mlb) else []   # written by build_ml.py

# ---------- templates ----------
FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;800&family=IBM+Plex+Sans:wght@400;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap">'
CSS = r"""<style>nav{display:flex;flex-direction:column;gap:6px;padding:12px 26px 0;font-size:13px}nav .row{display:flex;flex-wrap:wrap;gap:4px 6px;align-items:center}nav a{color:var(--mute);text-decoration:none;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--panel)}nav a.on{color:var(--ink);border-color:var(--acc)}nav .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.8px;font-weight:700;padding:5px 10px;border-radius:6px;min-width:52px;text-align:center}nav .row.mlb .lbl{color:#7fb8ff;background:#14202e}nav .row.mlb a.on{border-color:#7fb8ff}nav .row.nfl .lbl{color:#7fe0a5;background:#122a1e}nav .row.nfl a.on{border-color:#7fe0a5}nav .row.site a{border-color:#2f3944}nav .row.site a.on{border-color:var(--acc)}
:root{--bg:#0b0d10;--panel:#14181e;--line:#232a33;--ink:#e6e9ee;--mute:#8a94a3;--acc:#ffb020;--good:#2fd47a;--bad:#ff4d5e;--warn:#ffb020;--blue:#4aa3ff;--font:"IBM Plex Sans",ui-sans-serif,system-ui,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;--disp:"Barlow Condensed","Arial Narrow",Impact,sans-serif;color-scheme:dark}
*{box-sizing:border-box}body{background:var(--bg);color:var(--ink);font-family:var(--font);margin:0;padding:0 0 60px;font-size:14px}
header{padding:18px 26px 12px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px 18px;align-items:baseline}
h1{margin:0;font-family:var(--disp);font-size:34px;font-weight:800;letter-spacing:1.5px;line-height:1}h1 span{color:var(--acc)}h1 a{color:inherit;text-decoration:none}
.sub{color:var(--mute);font-size:13px}

nav a:hover{color:var(--ink);border-color:#3a4552}
.tabs{display:flex;gap:6px;padding:14px 26px 0}
.tab{font-family:var(--disp);font-size:17px;letter-spacing:.6px;text-transform:uppercase;padding:8px 16px;border:1px solid var(--line);border-bottom:none;border-radius:8px 8px 0 0;background:var(--panel);color:var(--mute);cursor:pointer;font-weight:600}
.tab.on{color:var(--ink);background:#1b2129;border-color:#2f3944}
.panel{margin:0 26px;border:1px solid var(--line);background:var(--panel);border-radius:0 10px 10px 10px;padding:14px}
.panel.top{border-radius:10px;margin-top:14px}
.ctl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px;font-size:13px}
.ctl input[type=text],.ctl input[type=number],.ctl select{background:#0e1115;border:1px solid var(--line);color:var(--ink);padding:6px 8px;border-radius:6px;font:inherit}
.ctl label{color:var(--mute)}.ctl select{background:#0e1115;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:4px 6px;font:inherit;max-width:320px}
textarea{width:100%;background:#0e1115;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:8px;font:12px var(--mono);min-height:64px}
details.top5{margin-bottom:14px}.top5 h2{margin:0 0 8px;font-size:15px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px}.card{background:#0e1115;border:1px solid var(--line);border-radius:8px;padding:10px 12px;position:relative}.card .rk{position:absolute;top:8px;right:10px;color:var(--mute);font:600 11px var(--mono)}.card .nm{font-weight:700;font-size:14px}.card .tm{display:block;margin-top:2px}.card .st{display:flex;gap:10px;margin-top:8px;font:12px var(--mono);font-variant-numeric:tabular-nums}.card .st b{display:block;font-size:14px;color:var(--ink)}.card .st span{color:var(--mute)}.card .why{margin-top:8px;font-size:12px;color:var(--mute)}.card.hit{border-color:#2fd47a}.card.miss{border-color:#3a2a2e}.paste{margin-bottom:12px;font-size:13px;color:var(--mute)}details.paste summary{cursor:pointer;color:var(--ink);font-weight:600}
button{background:#1b2129;border:1px solid #2f3944;color:var(--ink);padding:6px 12px;border-radius:6px;cursor:pointer;font:inherit}button:hover{border-color:var(--acc)}
.wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:1000px}
th{font-size:11px;text-transform:uppercase;letter-spacing:.6px;position:sticky;top:0;background:#1b2129;text-align:left;padding:8px 8px;border-bottom:1px solid var(--line);color:var(--mute);font-weight:600;cursor:pointer;white-space:nowrap}
th.on{color:var(--acc)}th.r{text-align:right}
td{padding:7px 8px;border-bottom:1px solid #1a2028;vertical-align:middle;white-space:nowrap}
tr.row:hover td{background:#181e26}
td.num{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}th.num{text-align:right}td.num .bar{margin-right:6px}th{vertical-align:bottom}
.nm{font-weight:700}.tm{color:var(--mute);font-size:12px}
input.odds,input.pub,input.stk{width:60px;background:#0e1115;border:1px solid var(--line);color:var(--ink);padding:4px 6px;border-radius:5px;font:12px var(--mono);text-align:right}input.stk{width:44px}
span.crowd{font-family:var(--mono);font-size:12px;color:var(--ink);margin-right:6px;white-space:nowrap}span.crowd b{color:var(--acc);font-weight:600}input.pub{width:42px}
input.bet{accent-color:var(--acc);width:16px;height:16px;vertical-align:middle}
.bar{display:inline-block;height:8px;border-radius:4px;background:#2b3440;width:60px;vertical-align:middle;position:relative;overflow:hidden}.bar i{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,#4aa3ff,#ff4d5e)}
.v{display:inline-block;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.4px}
.v.BET{background:#123d26;color:var(--good)}.v.LEAN{background:#12304a;color:var(--blue)}.v.AVOID{background:#4a1218;color:var(--bad)}.v.SLEEPER{background:#123d26;color:var(--good)}.v.VALUE{background:#12304a;color:var(--blue)}.v.TRAP,.v.FADE{background:#4a1218;color:var(--bad)}.v.CHALK{background:#463610;color:var(--warn)}.v.PASS,.v.DONE{background:#20262e;color:var(--mute)}.v.STRONGBET{background:#123d26;color:var(--good)}.v.BET{background:#12304a;color:var(--blue)}.v.PASSpricedin{background:#20262e;color:var(--mute)}
.res{font-family:var(--mono);font-weight:600}.res.y{color:var(--good)}.res.n{color:var(--mute)}.res.d{color:#5b6472}
.pos{color:var(--good)}.neg{color:var(--bad)}
tr.det td{background:#0e1115;color:var(--mute);white-space:normal;font-size:12px;padding:8px 14px 10px}
tr.det .f{display:inline-block;margin:2px 10px 2px 0;font-family:var(--mono)}
.legend{font-size:12px;color:var(--mute);margin:10px 0 0;line-height:1.7;max-width:110ch}.legend b{color:var(--ink)}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}.kpi div{background:#0e1115;border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:12px;color:var(--mute);min-width:96px}.kpi b{display:block;font-size:22px;color:var(--ink);font-family:var(--disp);font-weight:800;letter-spacing:.5px}.kpi b.pos{color:var(--good)}.kpi b.neg{color:var(--bad)}
h2{font-family:var(--disp);font-size:22px;letter-spacing:.8px;text-transform:uppercase;margin:22px 0 10px;color:var(--ink)}h2 small{font-family:var(--font);font-size:12px;color:var(--mute);text-transform:none;letter-spacing:0;margin-left:10px;font-weight:400}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}
.mini table{min-width:0}
svg.chart{width:100%;height:220px;display:block;background:#0e1115;border:1px solid var(--line);border-radius:8px}
.note{font-size:12px;color:var(--mute);line-height:1.6;max-width:90ch}
.empty{padding:22px;color:var(--mute);text-align:center;border:1px dashed var(--line);border-radius:8px}
@media(max-width:700px){header,nav,.tabs,.panel{padding-left:10px;padding-right:10px}.panel{margin-left:6px;margin-right:6px}}
</style>"""

def nav(active, root, sport=None):
    """three rows: site pages / MLB (today's HR board, moneyline, day pages) / NFL (today's TD board, moneyline, week pages)"""
    on = lambda h: ' class="on"' if active == h else ''
    site = f'<div class="row site"><a href="{root}index.html"{on("index.html")}>Today</a><a href="{root}ml.html"{on("ml.html")}>Moneyline</a><a href="{root}track.html"{on("track.html")}>Track</a><a href="{root}archive.html"{on("archive.html")}>Archive</a></div>'
    on_mlb = ' class="on"' if active == "index.html" and sport == "mlb" else ''; on_nfl = ' class="on"' if active == "index.html" and sport == "nfl" else ''
    mlb = f'<div class="row mlb"><span class="lbl">MLB</span><a href="{root}index.html#mlb"{on_mlb}>Home runs today</a><a href="{root}ml.html#mlb">Moneyline</a>' + ''.join(f'<a href="{root}days/{d}.html"{on("days/" + d)}>{d[5:]}</a>' for d in sorted(days, reverse=True)[:8]) + '</div>'
    nfl = f'<div class="row nfl"><span class="lbl">NFL</span><a href="{root}index.html#nfl"{on_nfl}>Touchdowns this week</a><a href="{root}ml.html#nfl">Moneyline</a>' + ''.join(f'<a href="{root}nfl/{w}.html"{on("nfl/" + w)}>week {w.split("wk")[1]}</a>' for w in sorted(weeks, reverse=True)[:8]) + '</div>'
    return f'<nav>{site}{mlb}{nfl}</nav>'

def head(title, sub, active, root):
    return f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>{FONTS}{CSS}<header><h1><a href="{root}index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">{sub}</div></header>{nav(active, root)}'

BOARD_JS = r"""
const $ = s => document.querySelector(s);
let tab = PAGE.tab, sortKey = 'prob', sortDir = -1;
if (location.hash === '#nfl' && (PAGE.rows.nfl || []).length) tab = 'nfl'; else if (location.hash === '#mlb' && (PAGE.rows.mlb || []).length) tab = 'mlb';
document.querySelectorAll('.tab').forEach(x => x.classList.toggle('on', x.dataset.t === tab));
function markNav(){ document.querySelectorAll('nav .row.mlb a, nav .row.nfl a').forEach(a => { if (/index\.html#(mlb|nfl)$/.test(a.getAttribute('href'))) a.classList.toggle('on', a.getAttribute('href').endsWith('#' + tab) && PAGE.tab !== 'single'); }); }
let store = {};
try { store = JSON.parse(localStorage.getItem('ftc_bets') || '{}'); } catch (e) { store = {}; }
function save(){ try { localStorage.setItem('ftc_bets', JSON.stringify(store)); } catch (e) {} }
const norm = s => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z ]/g, '').replace(/\s+/g, ' ').trim();
const implied = o => { o = +o; if (!o || isNaN(o)) return null; return o < 0 ? (-o) / (-o + 100) : 100 / (o + 100); };
const fmtOdds = o => o > 0 ? '+' + o : '' + o;
const key = r => r.date + '|' + r.sport + ':' + r.id;
// A projected lineup assumes he plays. Part-timers (catchers, platoon bats, rested veterans) often don't: Hunter Goodman topped the list on days he sat.
// playAdj = model % x how often he has really started in his team's last ~10 games. Only applies while the lineup is unposted; a posted lineup means he IS playing.
// r.prob itself is never changed: it stays 'if he plays', which is how results are graded (a scratch is a void, not a miss).
const restRisk = r => r.sport === 'MLB' && !r.lineupPosted && r.startRate != null && r.startRate < 0.9;      // worth calling out on the row
const playAdj = r => (r.sport === 'MLB' && !r.lineupPosted && r.startRate != null) ? r.prob * r.startRate : r.prob;   // applied to every projected hitter: even everyday players sit ~7%
function verdict(r){
  const e = store[key(r)] || {}; const oddsIn = e.odds || r.book; const imp = implied(oddsIn); const edge = imp == null ? null : r.prob - imp;
  const heat = e.pub != null && e.pub !== '' ? +e.pub : r.heat;
  const live = r.hit != null || r.dnp || !/Scheduled|Pre-Game|Warmup|STATUS_SCHEDULED/i.test(r.state || 'Scheduled') || (r.time && new Date(r.time).getTime() <= Date.now());   // locked rows keep their lock-time state, so the clock decides
  let v = 'PASS', why = '';
  if (r.sport === 'MLB') {
    // Home runs: follow the crowd when it agrees with itself in BOTH markets (money on the hitter AND on his team to win). See _patch notes in attach_team_money.
    const tp = r.teamPub, pubTxt = tp == null ? 'no moneyline money data for his game yet' : 'public has ' + Math.round(tp * 100) + '% of the moneyline money on ' + r.team;
    const bigTxt = r.big ? 'big name (top third of today\'s hitters by Kalshi dollars)' : 'not one of today\'s big-money names';
    if (r.big && tp != null && tp >= .65) v = 'BET';
    else if (r.big && ((tp != null && tp < .5) || r.teamFav === false)) v = 'AVOID';
    else if (!r.big && tp != null && tp >= .65) v = 'LEAN';
    why = bigTxt + ' · ' + pubTxt + (r.teamFav === false ? ' · his team is the priced underdog' : '');
  } else if (edge != null) {
    if (edge >= .04 && heat < 45) v = 'SLEEPER'; else if (edge >= .03) v = 'VALUE';
    else if (e.pub !== undefined && e.pub !== '' && +e.pub >= 60 && edge < 0) v = 'FADE';
    else if (heat >= 60 && edge <= 0.01) v = 'TRAP';
  } else if (heat >= 65) v = 'CHALK'; else if (r.prob >= .3 && heat < 40) v = 'SLEEPER';
  const nasty = r.prob * 100 + (edge == null ? 0 : edge * 150) - heat * 0.2;
  return { edge, heat, v, why, nasty, imp, live };
}
const COLS = {
  mlb: [['Player','name'],['Slot','slot'],['Game','game'],['vs SP','pitcher'],['Season','hr'],['L15','l15hr'],['Model %','prob'],['Fair','fair'],['Robinhood','odds'],['Edge','edge'],['Heat','heat'],['Crowd $ (Kalshi)','kvol'],['Verdict','v'],['Nasty','nasty'],['Bet','bet'],['Result','hit']],
  nfl: [['Player','name'],['Depth','pos'],['Game','game'],['Line','spread'],['Team imp.','implied'],['2025 TD','prevTD'],['2026 use','use26'],['Share','share'],['Model %','prob'],['Fair','fair'],['Robinhood','odds'],['Edge','edge'],['Heat','heat'],['Crowd $ (Kalshi)','kvol'],['Verdict','v'],['Nasty','nasty'],['Bet','bet'],['Result','hit']]
};
function resultCell(r){
  if (r.dnp) return '<span class="res d">DNP</span>';
  if (r.hit == null) return '<span class="res n">—</span>';
  const line = r.sport === 'MLB' && r.actualPA ? ` <span class="tm">${r.actual} HR / ${r.actualPA} PA</span>` : r.sport === 'NFL' && r.hit != null ? ` <span class="tm">${r.actual} TD</span>` : '';
  return r.hit ? `<span class="res y">✓ ${r.sport === 'MLB' ? 'HR' : 'TD'}${r.actual > 1 ? ' x' + r.actual : ''}</span>${line}` : `<span class="res n">✗</span>${line}`;
}
function render(){ top5();
  const rows = (PAGE.rows[tab] || []).map(r => ({ r, ...verdict(r) }));
  const q = norm($('#q').value), minp = +$('#minp').value / 100, maxh = +$('#maxh').value, hide = $('#hidedone').checked, only = $('#onlyplays').checked, onlybets = $('#onlybets').checked;
  const onlyhits = $('#onlyhits').checked;
  const gameSel = $('#game').value;
  let list = rows.filter(x => (!gameSel || x.r.game === gameSel) && (!hide || !x.live) && (!onlyhits || x.r.hit === 1) && x.r.prob >= minp && x.heat <= maxh && (!only || ['SLEEPER','VALUE','TRAP','FADE','BET','LEAN','AVOID'].includes(x.v)) && (!onlybets || (store[key(x.r)] || {}).on) &&
      (!q || norm(x.r.name).includes(q) || norm(x.r.team).includes(q) || norm(x.r.game).includes(q) || norm(x.r.teamName || '').includes(q)));
  const get = x => ({ nasty: x.nasty, prob: playAdj(x.r), edge: x.edge == null ? -9 : x.edge, heat: x.heat, time: x.r.time, name: x.r.name, slot: x.r.slot, hr: x.r.hr, l15hr: x.r.l15hr, fair: x.r.fair, prevTD: x.r.prevTD, use26: x.r.usage26 ? (x.r.usage26.tgt + x.r.usage26.att) : -1, share: x.r.share, implied: x.r.implied, v: x.v, game: x.r.game, pitcher: x.r.pitcher, pos: x.r.pos, spread: x.r.spread, odds: +(store[key(x.r)]||{}).odds || 0, pub: +(store[key(x.r)]||{}).pub || 0, kvol: x.r.kvol || 0, skew: x.r.skew == null ? -99 : x.r.skew, bet: (store[key(x.r)]||{}).on ? 1 : 0, hit: x.r.hit == null ? -1 : x.r.hit })[sortKey];
  list.sort((a, b) => { const A = get(a), B = get(b); return (A > B ? 1 : A < B ? -1 : 0) * sortDir; });
  const R = new Set(['slot', 'hr', 'l15hr', 'prob', 'fair', 'edge', 'nasty', 'implied', 'prevTD', 'use26', 'share']);
  $('#tbl thead').innerHTML = '<tr>' + COLS[tab].map(([l, k]) => `<th data-k="${k}" class="${k === sortKey ? 'on' : ''} ${R.has(k) ? 'r' : ''}">${l}${k === sortKey ? (sortDir < 0 ? ' ▼' : ' ▲') : ''}</th>`).join('') + '</tr>';
  const tb = $('#tbl tbody'); tb.innerHTML = '';
  const n = { s: 0, v: 0, t: 0, bets: 0, hits: 0, graded: 0, exp: 0, act: 0 };
  for (const x of list) {
    const r = x.r, e = store[key(r)] || {}; if (x.v === 'SLEEPER' || x.v === 'BET') n.s++; if (x.v === 'VALUE' || x.v === 'LEAN') n.v++; if (x.v === 'TRAP' || x.v === 'FADE' || x.v === 'AVOID') n.t++;
    if (e.on) n.bets++; if (r.hit != null) { n.graded++; n.exp += r.prob; n.act += r.hit; }
    const when = new Date(r.time).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
    const tr = document.createElement('tr'); tr.className = 'row';
    const common = `<td>${r.hit === 1 ? '<span class="res y">✓</span> ' : ''}<span class="nm">${r.name}</span> <span class="tm">${r.team}${r.inj ? ' · ' + r.inj : ''}${r.lateLock ? ' · late lock' : ''}</span></td>`;
    const tail = `<td class="num" title="${restRisk(r) ? 'Lineup not posted. He has started ' + r.starts + ' of ' + r.team + "'s last " + r.teamGames + ' games, so ' + (r.prob * 100).toFixed(1) + '% if he plays becomes ' + (playAdj(r) * 100).toFixed(1) + '% once the chance he sits is counted. Sorted by the lower number.' : ''}">${(r.prob * 100).toFixed(1)}%${restRisk(r) ? '<br><span class="tm" style="color:var(--warn)">' + (playAdj(r) * 100).toFixed(1) + '% · starts ' + r.starts + '/' + r.teamGames + '</span>' : ''}</td><td class="num">${fmtOdds(r.fair)}</td>
      <td><input class="odds" data-k="${key(r)}" data-f="odds" value="${e.odds || ''}" placeholder="${r.book ? fmtOdds(r.book) : '+000'}" title="${r.book ? (r.bookUsed === 'robinhood' ? 'Robinhood / Kalshi ask, as American odds' + (r.sportsbook ? '; Fliff ' + fmtOdds(r.sportsbook) : '') : r.bookUsed === 'fliff' ? 'Fliff price (no Robinhood market)' : r.bookUsed === 'underdog' ? 'Underdog price (not on Fliff)' : 'best sportsbook price') + (r.bestBook && r.bestBook > r.book ? ', best ' + fmtOdds(r.bestBook) + ' at ' + r.bestAt : '') + (r.move ? ', moved ' + (r.move > 0 ? '+' : '') + r.move + ' pts' : '') : 'type the book odds'}">${r.book && r.bookUsed === 'robinhood' ? '' : r.book && r.bookUsed === 'fliff' ? '<span class="tm">FL</span>' : r.book && r.bookUsed === 'underdog' ? '<span class="tm">UD</span>' : r.book && r.bookUsed === 'best' ? '<span class="tm">*</span>' : ''}${r.move ? `<span class="tm ${r.move > 0 ? 'neg' : 'pos'}">${r.move > 0 ? '▲' : '▼'}</span>` : ''}</td>
      <td class="num ${x.edge == null ? '' : x.edge >= 0 ? 'pos' : 'neg'}">${x.edge == null ? '—' : (x.edge >= 0 ? '+' : '') + (x.edge * 100).toFixed(1)}</td>
      <td><span class="bar"><i style="width:${x.heat}%"></i></span> <span class="tm">${Math.round(x.heat)}</span></td>
      <td>${r.kalshi != null ? `<span class="crowd" title="Kalshi: the crowd prices him at ${Math.round(r.kalshi * 100)}% with $${r.kvol.toLocaleString()} traded${r.kmove ? ', moved ' + (r.kmove > 0 ? '+' : '') + r.kmove + ' pts' : ''}">${Math.round(r.kalshi * 100)}% <b>$${r.kvol >= 1000 ? Math.round(r.kvol / 1000) + 'k' : r.kvol}</b>${r.kmove ? `<span class="${r.kmove > 0 ? 'neg' : 'pos'}"> ${r.kmove > 0 ? '▲' : '▼'}</span>` : ''}</span>` : r.skew != null ? `<span class="crowd" title="retail books minus offshore, in implied %: positive = crowd on him">skew ${r.skew > 0 ? '+' : ''}${r.skew}</span>` : ''}<input class="pub" data-k="${key(r)}" data-f="pub" value="${e.pub || ''}" placeholder="%" title="type a real public bet % to override"></td>
      <td><span class="v ${x.v}" title="${x.why || ''}">${x.v}</span></td><td class="num">${x.nasty.toFixed(1)}</td>
      <td><input type="checkbox" class="bet" data-k="${key(r)}" data-f="on" ${e.on ? 'checked' : ''} title="paper bet"> <input class="stk" data-k="${key(r)}" data-f="stake" value="${e.stake || ''}" placeholder="1u"></td>
      <td>${resultCell(r)}</td>`;
    if (tab === 'mlb') tr.innerHTML = common + `<td class="num">${r.slot}${r.lineupPosted ? '' : '*'}</td><td class="tm">${r.game.replace(/ at /, ' @ ')}<br>${when}</td><td class="tm">${r.pitcher} (${r.pHand})</td><td class="num">${r.hr} HR / ${r.pa} PA</td><td class="num">${r.l15hr}</td>` + tail;
    else tr.innerHTML = common + `<td>${r.depth || r.pos}</td><td class="tm">${r.game}<br>${when}</td><td class="tm">${r.spread || '—'} / ${r.total || '—'}</td><td class="num">${r.implied}</td><td class="num">${r.prevTD} in ${r.prevGP}g${r.prevTeam && r.prevTeam !== r.team ? ' (' + r.prevTeam + ')' : ''}</td><td class="num" title="${r.usage26 ? 'this season: ' + r.usage26.tgt + ' targets, ' + r.usage26.att + ' carries, ' + r.usage26.td + ' TD in ' + r.usage26.gp + ' g. Usage-based TD share ' + Math.round(r.usage26.share * 100) + '%, weighted ' + Math.round(r.usage26.w * 100) + '% against the 2025 share' : 'not blended yet'}">${r.usage26 ? (r.usage26.tgt ? r.usage26.tgt + ' tgt' : '') + (r.usage26.tgt && r.usage26.att ? ' · ' : '') + (r.usage26.att ? r.usage26.att + ' car' : '') + (!r.usage26.tgt && !r.usage26.att ? '0' : '') + (r.usage26.td ? ' · ' + r.usage26.td + ' TD' : '') : '—'}</td><td class="num">${(r.share * 100).toFixed(0)}%</td>` + tail;
    const det = document.createElement('tr'); det.className = 'det'; det.hidden = true;
    const facts = r.factors ? Object.entries(r.factors).map(([k, v]) => `<span class="f">${k} ${v}</span>`).join('') : '';
    det.innerHTML = `<td colspan="${COLS[tab].length}">${(r.notes || []).filter(Boolean).join(' &nbsp;|&nbsp; ')}<br>${facts}</td>`;
    tr.addEventListener('click', ev => { if (ev.target.tagName !== 'INPUT') det.hidden = !det.hidden; });
    tb.appendChild(tr); tb.appendChild(det);
  }
  let k = `<div>rows<b>${list.length}</b></div><div>${tab === 'mlb' ? 'bet' : 'sleepers'}<b>${n.s}</b></div><div>${tab === 'mlb' ? 'lean' : 'value'}<b>${n.v}</b></div><div>${tab === 'mlb' ? 'avoid' : 'traps / fades'}<b>${n.t}</b></div><div>with a price<b>${list.filter(x => x.edge != null).length}</b></div><div>paper bets<b>${n.bets}</b></div>`;
  if (n.graded) k += `<div>graded<b>${n.graded}</b></div><div>model said<b>${n.exp.toFixed(1)}</b></div><div>actually hit<b>${n.act}</b></div>`;
  $('#kpi').innerHTML = k;
  tb.querySelectorAll('input').forEach(i => i.addEventListener('change', () => { const k = i.dataset.k; store[k] = store[k] || {}; store[k][i.dataset.f] = i.type === 'checkbox' ? i.checked : i.value.trim(); if (i.type === 'checkbox' && i.checked) { store[k].sport = tab; } save(); render(); }));
  $('#tbl thead').querySelectorAll('th').forEach(th => th.addEventListener('click', () => { const k = th.dataset.k; if (sortKey === k) sortDir = -sortDir; else { sortKey = k; sortDir = -1; } render(); }));
}
// ---- top 5 to take: model % first, then what the graded history says (see track page) ----
// Signals kept: hitters priced shorter at retail than at
// Pinnacle (skew > 1) hit 9.6% vs 15%; heavy Kalshi money OVER-delivered (22% vs 15%), so the crowd is never faded here. NFL: RBs beat their number.
let gamesFor = null;
function fillGames(){
  if (gamesFor === tab) return; gamesFor = tab;
  const rows = tab === 'mlb' ? (PAGE.rows.mlb || []) : (PAGE.rows.nfl || []); const seen = new Map();
  for (const r of rows) if (r.game && !seen.has(r.game)) seen.set(r.game, r.time || '');
  const games = [...seen.entries()].sort((a, b) => a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0);
  $('#game').innerHTML = '<option value="">all games (' + games.length + ')</option>' + games.map(([g, t]) => `<option value="${g.replace(/"/g, '&quot;')}">${g}${t ? ' · ' + new Date(t).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : ''}</option>`).join('');
}
function top5(){
  fillGames();
  const gsel = $('#game').value; const rows = (tab === 'mlb' ? (PAGE.rows.mlb || []) : (PAGE.rows.nfl || [])).filter(r => !gsel || r.game === gsel);
  const now = Date.now();                                                              // locked rows keep the state they had at lock time, so judge 'started' by the clock
  const pre = r => r.hit == null && !r.dnp && (!r.time || new Date(r.time).getTime() > now) && /Scheduled|Pre-Game|Warmup|STATUS_SCHEDULED/i.test(r.state || 'Scheduled') && (tab === 'nfl' || r.slot);
  const upcoming = PAGE.graded ? [] : rows.filter(pre); const live = upcoming.length > 0;   // Today page mid-slate: only games still to come. Graded day page: the whole slate, with results
  const cand = live ? upcoming : rows.filter(r => !r.dnp && (tab === 'nfl' || r.slot));
  const score = r => { let m = 1, why = [];
    // Lineup slot, corrected 2026-09-18. The earlier 1.15x boost for slots 1-2 came from rows locked before lineups posted, where 'slot' was really
    // plate-appearance rank. On 741 hitters with REAL posted lineups: slots 1-2 16.0% vs 14.5% model, 3-4 16.6% vs 14.1%, 7-9 10.5% vs 8.7% (no clean top-of-order edge);
    // slots 5-6 9.7% vs 11.3%, and that one also held in the other half of the data. So: no boost up top, a mild penalty for 5-6. The model already gives leadoff men more plate appearances.
    if (tab === 'mlb') { if (r.slot >= 5 && r.slot <= 6) { m *= 0.9; why.push('slots 5-6 have run a little cold (9.7% vs 11.3% expected)'); } if (r.slot && !r.lineupPosted) why.push('lineup not posted: slot is projected'); }
    else if ((r.pos || '').startsWith('RB')) { m *= 1.1; why.push('RB (beat their number wk 1)'); }
    if (r.skew != null && r.skew > 1) { m *= 0.8; why.push('retail shorter than Pinnacle: public trap'); }
    if (r.kvol != null && r.kvol >= 3500) why.push('heavy Kalshi money, crowd has been right on these');
    if (r.book && implied(r.book) != null && r.prob - implied(r.book) >= .03) why.push('+' + Math.round((r.prob - implied(r.book)) * 100) + ' pts vs the price');
    if (restRisk(r)) why.unshift('has started only ' + r.starts + ' of ' + r.team + "'s last " + r.teamGames + ': ' + (r.prob * 100).toFixed(1) + '% if he plays, ' + (playAdj(r) * 100).toFixed(1) + '% counting days off');
    return { s: playAdj(r) * m, why }; };
  const ranked = cand.map(r => ({ r, ...score(r) })).sort((a, b) => b.s - a.s).slice(0, 5);
  $('#top5h').textContent = tab === 'mlb' ? (live ? 'Top 5 homers to take' : 'Top 5 homers, how they did') : (live ? 'Top 5 touchdowns to take' : 'Top 5 touchdowns, how they did');
  $('#top5').innerHTML = ranked.length ? ranked.map((x, i) => { const r = x.r; const done = r.hit != null;
    const vd = tab === 'mlb' ? verdict(r) : null;
    return `<div class="card ${done ? (r.hit ? 'hit' : 'miss') : ''}"><span class="rk">#${i + 1}</span><span class="nm">${r.name}</span>${vd && vd.v !== 'PASS' ? ` <span class="v ${vd.v}" title="${vd.why}">${vd.v}</span>` : ''}<span class="tm">${r.team}${tab === 'mlb' && r.slot ? ' · bats ' + r.slot : r.pos ? ' · ' + r.pos : ''} · ${r.game}${r.pitcher ? ' · vs ' + r.pitcher : ''}</span>
      <div class="st"><div><span>model</span><b>${(playAdj(r) * 100).toFixed(1)}%</b></div><div><span>Robinhood</span><b>${r.kalshi != null ? Math.round(r.kalshi * 100) + '¢' : r.book ? fmtOdds(r.book) : '—'}</b></div><div><span>crowd $</span><b>${r.kvol != null ? '$' + (r.kvol >= 1000 ? Math.round(r.kvol / 1000) + 'k' : r.kvol) : '—'}</b></div>${done ? `<div><span>result</span><b class="${r.hit ? 'pos' : 'neg'}">${r.hit ? '✓ ' + (tab === 'mlb' ? 'HR' : 'TD') : '✗'}</b></div>` : ''}</div>
      <div class="why">${x.why.length ? x.why.join(' · ') : 'model % alone'}</div></div>`; }).join('') : '<div class="empty">Nothing left to take: every game on this slate has started.</div>';
  $('#top5n').textContent = ranked.length ? (tab === 'mlb' ? 'Ranked by model %, cut for part-time players while lineups are unposted (model % x how often he has actually started lately), nudged down a little for lineup slots 5-6 and for hitters the public has pushed shorter than Pinnacle. Heavy crowd money is a plus, not a fade. The verdict tag on each card is the separate crowd-agreement read.' : 'Ranked by model %, nudged up for running backs and down for players the public has pushed shorter than Pinnacle.') + (live ? ' Started games drop off.' : '') : '';
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => { document.querySelectorAll('.tab').forEach(x => x.classList.remove('on')); t.classList.add('on'); tab = t.dataset.t; history.replaceState(null, '', '#' + tab); markNav(); render(); }));
markNav();
['#q', '#game', '#minp', '#maxh', '#hidedone', '#onlyplays', '#onlybets', '#onlyhits'].forEach(s => $(s).addEventListener('input', render));
$('#sort').addEventListener('change', () => { sortKey = $('#sort').value; sortDir = sortKey === 'time' ? 1 : -1; render(); });
render();
"""

def board_page(title, sub, active, root, rows_mlb, rows_nfl, graded, tabs=True):
    tab = 'mlb' if rows_mlb else 'nfl'
    tabhtml = ''
    if tabs and rows_mlb and rows_nfl: tabhtml = '<div class="tabs"><div class="tab on" data-t="mlb">MLB Home Runs</div><div class="tab" data-t="nfl">NFL Anytime TD</div></div>'
    date_prefix = (rows_mlb or rows_nfl)[0]['date'] if (rows_mlb or rows_nfl) else ''
    page = {'tab': tab, 'graded': graded, 'rows': {'mlb': rows_mlb, 'nfl': rows_nfl}, 'datePrefix': date_prefix}
    return f"""{head(title, sub, active, root)}{tabhtml}
<div class="panel {'' if tabhtml else 'top'}">
<div class="kpi" id="kpi"></div>
<div class="top5"><h2 id="top5h">Top 5 to take</h2><div class="cards" id="top5"></div><div class="note" id="top5n"></div></div>
<div class="ctl">
<label>search <input type="text" id="q" placeholder="player / team / game"></label>
<label>game <select id="game"><option value="">all games</option></select></label>
<label>min model % <input type="number" id="minp" value="0" min="0" max="100" style="width:56px"></label>
<label>max heat <input type="number" id="maxh" value="100" min="0" max="100" style="width:56px"></label>
<label><input type="checkbox" id="hidedone"> hide started games</label>
<label><input type="checkbox" id="onlyplays"> only flagged (hide PASS)</label>
<label><input type="checkbox" id="onlybets"> only my paper bets</label>
<label><input type="checkbox" id="onlyhits"> ✓ only homered / scored</label>
<label>sort <select id="sort"><option value="prob" selected>model %</option><option value="nasty">nasty score</option><option value="edge">edge</option><option value="heat">public heat</option><option value="hit">result</option><option value="time">game time</option></select></label>
</div>
<div class="wrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
<div class="legend">
<b>Model %</b> = what the numbers say. <b>Fair</b> = the odds that % deserves. <b>Robinhood</b> = the Kalshi/Robinhood ask for his home run market, shown as American odds (a 22¢ contract = +355); hover for Fliff's price. FL = no Robinhood market, Fliff's price shown; UD = Underdog; * = best sportsbook price; hover for the best price and any line move; ▲ = shortened since the morning pull). Type over it if Fliff shows you something different. <b>Edge</b> = model % minus the book's implied %.
<b>Heat</b> = how crowded the bet is: name recognition + hot streak + narrative, then adjusted by two live signals once odds are flowing: <b>line movement</b> (price shortened since the morning pull = money came in) and <b>book skew</b> (DraftKings / FanDuel / MGM pricing him shorter than Bovada / BetOnline = retail crowd is on him). For MLB the Public column shows <b>Kalshi</b>: the prediction-market crowd's own price for him and how many dollars they've put on it; crowd above the model, heavy volume, or a rising price all raise Heat. Typing a real public-bet % overrides all of it.<br>
<b>Model %</b> for home runs is recalibrated from 2026-09-19 (open a row to see the raw number it came from). <b>Home run verdicts</b> follow the crowd when it agrees with itself in both markets. <b>BET</b> = a big-money name (top third of today's hitters by Robinhood/Kalshi dollars) whose team also has 65%+ of the public's moneyline money: those homered 20.9% of the time against a 15.7% price. <b>LEAN</b> = same team situation, smaller name (13.1% against 11.0%). <b>AVOID</b> = a big-money name on the priced underdog or on a team the public is betting against (12.7% against 14.8%). <b>PASS</b> = none of those, or no moneyline money on his game yet. Hover a verdict for the reason. Six days of data so far; the Track page scores each tier going forward. <b>Touchdown verdicts:</b> <b>SLEEPER</b> = edge with low heat. <b>VALUE</b> = edge, some heat. <b>TRAP</b> = crowd on him, no edge. <b>FADE</b> = public 60%+ and negative edge. <b>CHALK</b> = hot name, no price entered.
<b>Result</b> fills in as games go final and stays on the page with the crowd money, so hits can be checked against where the public was. <b>Bet</b> = tick to paper-bet him (stake in units, blank = 1u). It's scored on the Track page once the game is final, at the Book odds you typed, or at Fair if you typed none.
</div>
</div>
<script>const PAGE = {jd(page)};{BOARD_JS}</script>"""

TRACK_CSS = '<style>button.rm{background:#1c2430;border:1px solid #2b3440;color:#8a94a3;border-radius:6px;padding:2px 8px;cursor:pointer;font:inherit}button.rm:hover{color:#ff4d5e;border-color:#ff4d5e}</style>'
TRACK_JS = r"""
const H = HISTORY; let store = {};
try { store = JSON.parse(localStorage.getItem('ftc_bets') || '{}'); } catch (e) {}
const byKey = {}; for (const r of H) byKey[r.date + '|' + r.sport + ':' + r.id] = r;
const pay = (odds, stake, hit) => hit ? stake * (odds > 0 ? odds / 100 : 100 / -odds) : -stake;
const fmt = o => o > 0 ? '+' + o : '' + o;
// ---- your paper bets (props from the day pages + moneylines from ml.html) ----
let mlStore = {}; try { mlStore = JSON.parse(localStorage.getItem('ftc_ml_bets') || '{}'); } catch (e) {}
const mlByKey = {}; for (const r of MLH) mlByKey[r.date + '|' + (r.gamePk || r.eventId)] = r;
const ledgerRows = () => {
  const bets = [];
  for (const [k, e] of Object.entries(store)) { if (!e.on) continue; const r = byKey[k]; if (!r) continue;
    const odds = +e.odds || r.book || r.fair, stake = +e.stake || 1; const settled = r.hit != null && !r.dnp;
    bets.push({ kind: 'prop', k, date: r.date, name: r.name, sub: r.team, game: r.game, prob: r.prob, heat: r.heat, odds, stake, atFair: !e.odds && !r.book, settled, hit: r.hit, pnl: settled ? pay(odds, stake, r.hit) : 0, void: !!r.dnp }); }
  for (const [k, e] of Object.entries(mlStore)) { if (!e.on) continue; const r = mlByKey[k]; if (!r) continue;
    const team = r.pick === 'home' ? r.home : r.away, odds = r.pickOdds, stake = +e.stake || 1; const settled = r.pickHit != null && odds != null;
    bets.push({ kind: 'ml', k, date: r.date, name: team + ' ML', sub: r.sport, game: r.away + ' @ ' + r.home + (r.score ? ' · ' + r.score : ''), prob: r.pickProb, heat: r.pubHome == null ? null : Math.round((r.pick === 'home' ? r.pubHome : 1 - r.pubHome) * 100), odds: odds == null ? 0 : odds, stake, atFair: false, settled, hit: r.pickHit, pnl: settled ? pay(odds, stake, r.pickHit) : 0, void: false, noPrice: odds == null }); }
  bets.sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0); return bets; };
let bets = [], settled = [];
function renderLedger(){
  bets = ledgerRows(); settled = bets.filter(b => b.settled); const units = settled.reduce((s, b) => s + b.pnl, 0); const staked = settled.reduce((s, b) => s + b.stake, 0);
  document.querySelector('#mykpi').innerHTML = `<div>paper bets<b>${bets.length}</b></div><div>settled<b>${settled.length}</b></div><div>record<b>${settled.filter(b => b.hit).length}-${settled.filter(b => !b.hit).length}</b></div><div>units<b class="${units >= 0 ? 'pos' : 'neg'}">${units >= 0 ? '+' : ''}${units.toFixed(2)}</b></div><div>ROI<b class="${units >= 0 ? 'pos' : 'neg'}">${staked ? (units / staked * 100).toFixed(1) : '0.0'}%</b></div><div>pending<b>${bets.filter(b => !b.settled && !b.void).length}</b></div>`;
  const led = document.querySelector('#ledger');
  if (!bets.length) { led.innerHTML = '<div class="empty">No paper bets yet. Tick the Bet box next to a player on a day page, or next to a game on the Moneyline page, and it shows up here.</div>'; return; }
  let run = 0;
  led.innerHTML = '<div class="wrap"><table><thead><tr><th>Date</th><th>Bet</th><th>Game</th><th class="num">Model %</th><th class="num">Public</th><th class="num">Odds</th><th class="num">Stake</th><th>Result</th><th class="num">P/L</th><th class="num">Running</th><th></th></tr></thead><tbody>' +
    bets.map(b => { if (b.settled) run += b.pnl; return `<tr><td class="tm">${b.date.replace('_', ' ')}</td><td><span class="nm">${b.name}</span> <span class="tm">${b.sub}</span></td><td class="tm">${b.game}</td><td class="num">${(b.prob * 100).toFixed(1)}%</td><td class="num">${b.heat == null ? '—' : Math.round(b.heat) + (b.kind === 'ml' ? '%' : '')}</td><td class="num">${b.noPrice ? '—' : fmt(b.odds)}${b.atFair ? ' <span class="tm">fair</span>' : ''}</td><td class="num">${b.stake}u</td><td>${b.void ? '<span class="res d">void</span>' : !b.settled ? '<span class="res n">pending</span>' : b.hit ? '<span class="res y">✓ ' + (b.kind === 'ml' ? 'won' : 'hit') + '</span>' : '<span class="res n">✗ ' + (b.kind === 'ml' ? 'lost' : 'miss') + '</span>'}</td><td class="num ${b.pnl >= 0 ? 'pos' : 'neg'}">${b.settled ? (b.pnl >= 0 ? '+' : '') + b.pnl.toFixed(2) : '—'}</td><td class="num ${run >= 0 ? 'pos' : 'neg'}">${b.settled ? (run >= 0 ? '+' : '') + run.toFixed(2) : ''}</td><td><button class="rm" data-kind="${b.kind}" data-k="${b.k}" title="remove this paper bet">✕</button></td></tr>`; }).join('') +
    '</tbody></table></div><div class="note" style="margin-top:6px"><button class="rm" id="clearall">clear all paper bets</button> &nbsp; bets live in this browser only (localStorage), so tick and track on the same site, not one on the live site and one on a local file</div>';
  led.querySelectorAll('button.rm[data-k]').forEach(btn => btn.addEventListener('click', () => { const st = btn.dataset.kind === 'ml' ? mlStore : store; if (st[btn.dataset.k]) st[btn.dataset.k].on = false; try { localStorage.setItem(btn.dataset.kind === 'ml' ? 'ftc_ml_bets' : 'ftc_bets', JSON.stringify(st)); } catch (e) {} renderLedger(); drawChart(); }));
  const ca = led.querySelector('#clearall'); if (ca) ca.addEventListener('click', () => { if (!confirm('Remove every paper bet from this browser?')) return; for (const e of Object.values(store)) e.on = false; for (const e of Object.values(mlStore)) e.on = false; try { localStorage.setItem('ftc_bets', JSON.stringify(store)); localStorage.setItem('ftc_ml_bets', JSON.stringify(mlStore)); } catch (e) {} renderLedger(); drawChart(); });
}
renderLedger();
// ---- model strategies at fair odds ----
const G = H.filter(r => r.hit != null && !r.dnp && r.sport === 'MLB');
const dates = [...new Set(G.map(r => r.date))].sort();
const strat = {
  'Top 5 by model %': d => G.filter(r => r.date === d).sort((a, b) => b.prob - a.prob).slice(0, 5),
  'Top 10 by model %': d => G.filter(r => r.date === d).sort((a, b) => b.prob - a.prob).slice(0, 10),
  'Sleepers (20%+, heat < 35)': d => G.filter(r => r.date === d && r.prob >= .2 && r.heat < 35),
  'Chalk (20%+, heat 60+)': d => G.filter(r => r.date === d && r.prob >= .2 && r.heat >= 60),
  'Everyone 20%+': d => G.filter(r => r.date === d && r.prob >= .2),
  'HR VERDICT BET: big name, public 65%+ on his team': d => G.filter(r => r.date === d && r.big && r.teamPub != null && r.teamPub >= .65),
  'HR VERDICT LEAN: smaller name, public 65%+ on his team': d => G.filter(r => r.date === d && !r.big && r.teamPub != null && r.teamPub >= .65),
  'HR VERDICT AVOID: big name, underdog or public against his team': d => G.filter(r => r.date === d && r.big && !(r.teamPub != null && r.teamPub >= .65) && ((r.teamPub != null && r.teamPub < .5) || r.teamFav === false)),
};
const curves = {}; const SROWS = [];
for (const [name, fn] of Object.entries(strat)) { let bets = 0, hits = 0, pnl = 0, exp = 0; const curve = [0];
  for (const d of dates) { for (const r of fn(d)) { bets++; hits += r.hit; exp += r.prob; pnl += pay(r.fair, 1, r.hit); } curve.push(pnl); }
  curves[name] = curve; SROWS.push({ name, bets, hits, l: bets - hits, pct: bets ? hits / bets : -1, exp: bets ? exp / bets : -1, pnl, roi: bets ? pnl / bets : -99 }); }
let sSort = null, sDir = -1;
function stratRows(){ const rows = sSort ? [...SROWS].sort((a, b) => ((a[sSort] > b[sSort] ? 1 : a[sSort] < b[sSort] ? -1 : 0) * sDir)) : SROWS;
  return rows.map(x => `<tr><td class="nm">${x.name}</td><td class="num">${x.bets}</td><td class="num">${x.hits}-${x.l}</td><td class="num">${x.bets ? (x.pct * 100).toFixed(1) : 0}%</td><td class="num">${x.bets ? (x.exp * 100).toFixed(1) : 0}%</td><td class="num ${x.pnl >= 0 ? 'pos' : 'neg'}">${x.pnl >= 0 ? '+' : ''}${x.pnl.toFixed(1)}u</td><td class="num ${x.pnl >= 0 ? 'pos' : 'neg'}">${x.bets ? (x.roi * 100).toFixed(1) : 0}%</td></tr>`).join(''); }
document.querySelector('#strat tbody').innerHTML = stratRows();
document.querySelectorAll('#strat thead th').forEach(th => th.addEventListener('click', () => { const k = th.dataset.s; if (!k) return; if (sSort === k) sDir = -sDir; else { sSort = k; sDir = k === 'name' ? 1 : -1; } document.querySelector('#strat tbody').innerHTML = stratRows(); }));
// ---- calibration + heat ----
const bk = [[0, .08], [.08, .12], [.12, .16], [.16, .20], [.20, .25], [.25, 1]];
// two eras, scored apart: rows carrying probRaw were made by the recalibrated model (v3, from 2026-09-19); everything older is the raw number as it was shown then
const calRows = rows => bk.map(([lo, hi]) => { const b = rows.filter(r => r.prob >= lo && r.prob < hi); if (!b.length) return ''; const p = b.reduce((s, r) => s + r.prob, 0) / b.length, a = b.reduce((s, r) => s + r.hit, 0) / b.length; const rw = b.filter(r => r.probRaw != null); const rawp = rw.length ? rw.reduce((s, r) => s + r.probRaw, 0) / rw.length : null;
  return `<tr><td>${(lo * 100).toFixed(0)}–${hi === 1 ? '100' : (hi * 100).toFixed(0)}%</td><td class="num">${b.length}</td><td class="num">${(p * 100).toFixed(1)}%</td><td class="num">${(a * 100).toFixed(1)}%</td><td class="num ${Math.abs(a - p) <= .02 ? 'pos' : 'neg'}">${((a - p) * 100 >= 0 ? '+' : '')}${((a - p) * 100).toFixed(1)}</td><td class="num tm">${rawp == null ? '—' : (rawp * 100).toFixed(1) + '%'}</td></tr>`; }).join('');
const eraOld = G.filter(r => r.probRaw == null), eraNew = G.filter(r => r.probRaw != null);
document.querySelector('#calib tbody').innerHTML = `<tr><td colspan="6" class="tm"><b>Recalibrated model, from 2026-09-19</b> · ${eraNew.length} graded hitters</td></tr>` + (calRows(eraNew) || '<tr><td colspan="6" class="tm">no graded days yet</td></tr>') + `<tr><td colspan="6" class="tm" style="padding-top:12px"><b>Before recalibration</b> · ${eraOld.length} graded hitters</td></tr>` + calRows(eraOld);
const hb = [[0, 35, 'Cold (< 35)'], [35, 60, 'Warm (35–60)'], [60, 101, 'Hot (60+)']];
document.querySelector('#heat tbody').innerHTML = hb.map(([lo, hi, lab]) => { const b = G.filter(r => r.heat >= lo && r.heat < hi); if (!b.length) return ''; const p = b.reduce((s, r) => s + r.prob, 0), a = b.reduce((s, r) => s + r.hit, 0); return `<tr><td>${lab}</td><td class="num">${b.length}</td><td class="num">${(p / b.length * 100).toFixed(1)}%</td><td class="num">${(a / b.length * 100).toFixed(1)}%</td><td class="num ${a / p >= 1 ? 'pos' : 'neg'}">${(a / p).toFixed(2)}</td></tr>`; }).join('');
// ---- kalshi volume terciles ----
const K = G.filter(r => r.kalshi != null && r.kvol != null);
if (K.length) { const vs = K.map(r => r.kvol).sort((a, b) => a - b); const t1 = vs[Math.floor(vs.length / 3)], t2 = vs[Math.floor(vs.length * 2 / 3)];
  const kb = [[0, t1, 'Light money'], [t1, t2, 'Medium'], [t2, 1e12, 'Heavy money']];
  document.querySelector('#kvol tbody').innerHTML = kb.map(([lo, hi, lab]) => { const b = K.filter(r => r.kvol >= lo && r.kvol < hi); if (!b.length) return ''; const p = b.reduce((s, r) => s + r.prob, 0), c = b.reduce((s, r) => s + r.kalshi, 0), a = b.reduce((s, r) => s + r.hit, 0); return `<tr><td>${lab}</td><td class="num">${b.length}</td><td class="num">${(p / b.length * 100).toFixed(1)}%</td><td class="num">${(c / b.length * 100).toFixed(1)}%</td><td class="num">${(a / b.length * 100).toFixed(1)}%</td><td class="num ${a / c >= 1 ? 'pos' : 'neg'}">${(a / c).toFixed(2)}</td></tr>`; }).join(''); }
else document.querySelector('#kvol tbody').innerHTML = '<tr><td colspan="6" class="tm">No graded days with Kalshi data yet. Fills in from tomorrow.</td></tr>';
function drawChart(){
// ---- chart ----
const svg = document.querySelector('#chart'); const W = 800, Hh = 220, pad = 34;
const series = [['Top 5 by model %', '#ffb020'], ['Sleepers (20%+, heat < 35)', '#2fd47a'], ['Chalk (20%+, heat 60+)', '#ff4d5e']];
let myCurve = [0]; { let run = 0; for (const d of dates) { for (const b of settled) if (b.date === d) run += b.pnl; myCurve.push(run); } }
const all = [...series.map(s => curves[s[0]]), myCurve].flat(); const mn = Math.min(0, ...all), mx = Math.max(1, ...all);
const X = i => pad + i * (W - pad * 2) / Math.max(1, dates.length), Y = v => Hh - pad + (v - mn) * -(Hh - pad * 2) / (mx - mn || 1);
let g = `<line x1="${pad}" x2="${W - pad}" y1="${Y(0)}" y2="${Y(0)}" stroke="#2b3440"/>`;
for (const [name, col] of series) g += `<polyline fill="none" stroke="${col}" stroke-width="2" points="${curves[name].map((v, i) => X(i) + ',' + Y(v)).join(' ')}"/>`;
if (settled.length) g += `<polyline fill="none" stroke="#e6e9ee" stroke-width="2.5" stroke-dasharray="5 4" points="${myCurve.map((v, i) => X(i) + ',' + Y(v)).join(' ')}"/>`;
dates.forEach((d, i) => { if (i % Math.ceil(dates.length / 8) === 0) g += `<text x="${X(i + 1)}" y="${Hh - 10}" fill="#8a94a3" font-size="10" text-anchor="middle">${d.slice(5)}</text>`; });
g += `<text x="${pad}" y="${Y(mx) + 4}" fill="#8a94a3" font-size="10">${mx >= 0 ? '+' : ''}${mx.toFixed(0)}u</text><text x="${pad}" y="${Y(mn) - 2}" fill="#8a94a3" font-size="10">${mn.toFixed(0)}u</text>`;
svg.innerHTML = g;
document.querySelector('#chartlegend').innerHTML = series.map(([n, c]) => `<span style="color:${c}">■</span> ${n}`).join(' &nbsp; ') + (settled.length ? ' &nbsp; <span style="color:#e6e9ee">┅</span> your paper bets' : '');
}
drawChart();
"""

def track_page():
    n_days = len([d for d, rows in days.items() if any(r['hit'] is not None for r in rows)])
    return f"""{head('Fade The Chalk', 'paper-bet ledger + how the model is doing at fair odds', 'track.html', '')}
{TRACK_CSS}<div class="panel top">
<h2>Your paper bets <small>ticked on the day pages, kept in this browser, scored when games go final</small></h2>
<div class="kpi" id="mykpi"></div>
<div id="ledger"></div>
<h2>Model strategies at fair odds <small>{n_days} graded MLB days · flat 1u · fair = the odds the model's own % implies, so a real book pays less than this</small></h2>
<svg class="chart" id="chart" viewBox="0 0 800 220" preserveAspectRatio="none"></svg>
<div class="note" id="chartlegend" style="margin:6px 0 12px"></div>
<div class="wrap"><table id="strat"><thead><tr><th data-s="name">Strategy</th><th class="num" data-s="bets">Bets</th><th class="num" data-s="pct">Record</th><th class="num" data-s="pct">Hit %</th><th class="num" data-s="exp">Model said</th><th class="num" data-s="pnl">Units</th><th class="num" data-s="roi">ROI</th></tr></thead><tbody></tbody></table></div>
<div class="grid2" style="margin-top:18px">
<div class="mini"><h2>Calibration <small>does 25% mean 25%?</small></h2><div class="wrap"><table id="calib"><thead><tr><th>Model %</th><th class="num">n</th><th class="num">Predicted</th><th class="num">Actual</th><th class="num">Diff</th><th class="num">Raw said</th></tr></thead><tbody></tbody></table></div></div>
<div class="mini"><h2>The rigged test, Kalshi money <small>hitters with the most public dollars on them: do they underperform?</small></h2><div class="wrap"><table id="kvol"><thead><tr><th>Kalshi volume</th><th>n</th><th>Model said</th><th>Crowd said</th><th>Actual</th><th>Actual ÷ crowd</th></tr></thead><tbody></tbody></table></div></div>
<div class="mini"><h2>The rigged test, heat <small>do the crowd's names underperform their own numbers?</small></h2><div class="wrap"><table id="heat"><thead><tr><th>Heat</th><th>n</th><th>Predicted</th><th>Actual</th><th>Actual ÷ predicted</th></tr></thead><tbody></tbody></table></div></div>
</div>
<p class="note" style="margin-top:14px">Picks are locked before first pitch and graded from box scores afterward; results never change a lock. Days before {min(days) if days else ''} were reconstructed from posted lineups with season stats as of the build, which leaks a little. Model v3 (from 2026-09-19): home-run percentages are recalibrated because v2 was too spread out (hitters shown at 30% homered 22%, hitters shown at 4% homered 7%); tested on held-out days, and the table above scores the two eras separately, with Diff in green when predicted and actual are within 2 points. Model v2 (from 2026-09-12): base rate regressed less toward league, weak hitters dampened, level scaled 0.92 - fitted on those same days, so judge it on days after that.</p>
</div>
<script>const HISTORY = {jd(HISTORY)}; const MLH = {jd(MLH)};{TRACK_JS}</script>"""

W = lambda path, html: open(os.path.join(SITE, path), 'w', encoding='utf-8', newline='\n').write(html)
gen = board['generated']
for r in board['mlb']: r.setdefault('date', today)
for r in board['nfl']: r.setdefault('date', 'now')
# today's page: use the locked rows for today if present (so results show once graded), else the live board
_cal = datetime.date.today().isoformat()   # output/board.json is local and gitignored, so it can be a day behind the locks pulled from git: the calendar day's lock wins
today_rows = days.get(_cal) or days.get(today, board['mlb'])
cur_week = max(weeks) if weeks else None
nfl_today = weeks[cur_week] if cur_week else board['nfl']   # locked + graded rows, same as the week page
W('index.html', board_page('Fade The Chalk', f'MLB HR + NFL anytime TD · model prob vs. the price vs. the crowd · built {gen}', 'index.html', '', today_rows, nfl_today, False))
for d, rows in days.items():
    graded = any(r['hit'] is not None for r in rows)
    W(f'days/{d}.html', board_page('Fade The Chalk', f'MLB home runs · {d} · {"results graded" if graded else "waiting on results"} · picks locked pre-game', 'days/' + d, '../', rows, [], graded, tabs=False))
for w, rows in weeks.items():
    graded = any(r['hit'] is not None for r in rows)
    W(f'nfl/{w}.html', board_page('Fade The Chalk', f'NFL anytime TD · {w.replace("_", " ")} · {"results graded" if graded else "waiting on results"}', 'nfl/' + w, '../', [], rows, graded, tabs=False))
W('track.html', track_page())
open(os.path.join(SITE, '.nojekyll'), 'w').close()
print(f"site: index + {len(days)} day pages + {len(weeks)} nfl pages + track -> {SITE}")
