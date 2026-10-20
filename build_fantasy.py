"""Render docs/fantasy.html: NFL fantasy start/sit, waiver risers and yardage projections (receptions, receiving / rushing / passing yards),
graded every week from ESPN box scores (backtest/nflstats_<week>.json, written by grade.py).

Projection = the player's own 2026 average, pulled toward the middle (one good game is mostly noise), then nudged by what held week after
week in weeks 3-6 (562 player-games with 2+ prior games, each week predicted only from the weeks before it):
  * crowd money: players on the team with LESS of the crowd's spread money beat their average by ~2 fantasy points more than the crowd's team
    (red for the crowd's team in all 4 weeks); for running backs that is ~12 rushing yards.
  * the totals crowd: when the crowd's money is on the UNDER, players fell ~2 points / ~8 receiving yards short (every week).
  * matchup: what the opponent has allowed to the position in earlier weeks (receivers vs tough pass defenses: ~8 yards short, every week).
  * team implied points (small).
Yards are noisy: the typical miss is ~25 yards for receiving and rushing, ~55 for passing. The page turns that into an over/under chance
for any line you type in, and only calls a lean when the projection clears the line by a real margin."""
import json, os, re, glob, math, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs')
J = lambda p: json.load(open(p, encoding='utf-8'))
jd = lambda o: json.dumps(o, separators=(',', ':')).replace('</', '<' + chr(92) + '/')
src = open(os.path.join(HERE, 'build_site.py'), encoding='utf-8').read()
CSS = re.search(r'CSS = r"""(.*?)"""', src, re.S).group(1); FONTS = re.search(r"FONTS = '(.*?)'", src).group(1)

# fitted on weeks 3-6 (ridge, half-PPR); residual sd = the typical spread of outcomes around the projection
M = {
    'fp':      dict(c=2.94, base=0.594, spLess=1.104, under=-1.927, opp=0.721, impl=0.145, sd=6.7),
    'rec':     dict(c=1.04, base=0.705, under=-0.312, sd=2.3),
    'recYds':  dict(c=13.48, base=0.606, under=-8.463, opp=3.442, sd=32.3),
    'rushYds': dict(c=8.91, base=0.761, spLess=12.165, fav=4.951, sd=31.4),   # opponent rush defense came out backwards (noise), so it is left out
    'passYds': dict(c=138.21, base=0.417, sd=71.0),
    'qbRush':  dict(c=4.70, base=0.700, sd=20.9),
}
num = lambda v: v if isinstance(v, (int, float)) else 0.0

def line(p):
    s = {k: num(p.get(k, 0)) for k in ('passing.passingYards', 'passing.passingTouchdowns', 'passing.interceptions', 'rushing.rushingAttempts', 'rushing.rushingYards',
                                       'rushing.rushingTouchdowns', 'receiving.receptions', 'receiving.receivingYards', 'receiving.receivingTouchdowns', 'receiving.receivingTargets')}
    o = {'passYds': s['passing.passingYards'], 'passTD': s['passing.passingTouchdowns'], 'ints': s['passing.interceptions'], 'att': s['rushing.rushingAttempts'],
         'rushYds': s['rushing.rushingYards'], 'rushTD': s['rushing.rushingTouchdowns'], 'rec': s['receiving.receptions'], 'recYds': s['receiving.receivingYards'],
         'recTD': s['receiving.receivingTouchdowns'], 'tgt': s['receiving.receivingTargets']}
    o['fp'] = round(0.04 * o['passYds'] + 4 * o['passTD'] - 2 * o['ints'] + 0.1 * o['rushYds'] + 6 * o['rushTD'] + 0.5 * o['rec'] + 0.1 * o['recYds'] + 6 * o['recTD'], 1)
    return o

weeks = sorted({os.path.basename(f)[4:-5] for f in glob.glob(os.path.join(BT, 'nfl_2026_wk*.json'))}, key=lambda t: int(t.split('wk')[1]))
wn = lambda t: int(t.split('wk')[1])
stats = {t: J(os.path.join(BT, f'nflstats_{t}.json')) for t in weeks if os.path.exists(os.path.join(BT, f'nflstats_{t}.json'))}
locks = {t: J(os.path.join(BT, f'nfl_{t}.json')) for t in weeks}
POS = {}
for t in weeks:
    for r in locks[t]: POS[str(r['id'])] = (r.get('pos') or '')[:2]
games = {}                                                  # (week, pid) -> stat line, plus the opponent for defense-allowed numbers
for t, st in stats.items():
    for ev, g in st.items():
        teams = sorted({p.get('team') for p in g.values() if p.get('team')})
        for pid, p in g.items():
            opp = next((x for x in teams if x != p.get('team')), None)
            games[(t, pid)] = dict(line(p), team=p.get('team'), opp=opp, ev=ev, name=p.get('name'))

def project(t):
    """projections for every skill player on week t's lock, using only weeks before t"""
    prior = [w for w in weeks if wn(w) < wn(t) and w in stats]
    hist = {}
    for (w, pid), g in games.items():
        if w in prior: hist.setdefault(pid, []).append((wn(w), g))
    # what each defense allowed to each position, per game, vs the league
    allow, lg = {}, {}
    for (w, pid), g in games.items():
        if w not in prior: continue
        pos = POS.get(pid)
        if pos not in ('QB', 'RB', 'WR', 'TE'): continue
        a = allow.setdefault((g['opp'], pos), {}).setdefault(w, {'fp': 0, 'recYds': 0, 'rushYds': 0, 'passYds': 0}); L = lg.setdefault(pos, {}).setdefault((w, g['opp']), {'fp': 0, 'recYds': 0, 'rushYds': 0, 'passYds': 0})
        for k in a: a[k] += g[k]; L[k] += g[k]
    def opp_factor(opp, pos, k):
        a = allow.get((opp, pos), {}); L = lg.get(pos, {})
        if len(a) < 2 or not L: return 1.0
        mine = sum(v[k] for v in a.values()) / len(a); avg = sum(v[k] for v in L.values()) / len(L)
        return max(0.6, min(1.5, mine / avg)) if avg else 1.0
    lf = os.path.join(BT, f'lines_{t}.json'); LN = {str(x.get('eventId')): x for x in J(lf)} if os.path.exists(lf) else {}
    posmean = {}
    for pid, h in hist.items():
        pos = POS.get(pid)
        if pos and len(h) >= 2: posmean.setdefault(pos, []).append(sum(g['fp'] for _, g in h) / len(h))
    posmean = {k: sorted(v)[len(v) // 2] for k, v in posmean.items()}
    out = []
    for r in locks[t]:
        pid = str(r['id']); pos = (r.get('pos') or '')[:2]
        if pos not in ('QB', 'RB', 'WR', 'TE'): continue
        h = sorted(hist.get(pid, []))
        if not h: continue
        n = len(h); avg = lambda k: sum(g[k] for _, g in h) / n
        base = {k: avg(k) for k in ('fp', 'rec', 'recYds', 'rushYds', 'passYds', 'tgt', 'att')}
        if n == 1:                                          # one game is mostly noise: lean on the position's typical starter
            for k in base: base[k] = base[k] * 0.5 + (posmean.get(pos, base['fp']) if k == 'fp' else base[k]) * 0.5
        last2 = h[-2:]; opps2 = sum(g['tgt'] + g['att'] for _, g in last2) / len(last2); oppsAll = sum(g['tgt'] + g['att'] for _, g in h) / n
        sp = (LN.get(str(r['eventId'])) or {}).get('spread') or {}; tot = (LN.get(str(r['eventId'])) or {}).get('total') or {}
        fv, dg = sp.get('tapeFav$') or 0, sp.get('tapeDog$') or 0; spT = fv + dg
        spTeam = None if not (sp.get('fav') and spT) else (fv if r['team'] == sp['fav'] else dg) / spT
        spLess = 0.5 if spTeam is None or spT < 100000 else (1.0 if spTeam < .5 else 0.0)
        ov, un = tot.get('tapeOver$') or 0, tot.get('tapeUnder$') or 0
        overShare = ov / (ov + un) if ov + un else None
        under = 1.0 if (overShare is not None and ov + un >= 25000 and overShare < .45) else 0.0
        fav = 0.5 if not sp.get('fav') else (1.0 if sp['fav'] == r['team'] else 0.0)
        impl = (r.get('implied') or 22.5) - 22.5
        oF, oR, oP = opp_factor(r['opp'], pos, 'fp'), opp_factor(r['opp'], pos, 'recYds'), opp_factor(r['opp'], pos, 'passYds')
        m = M['fp']; fp = m['c'] + m['base'] * base['fp'] + m['spLess'] * spLess + m['under'] * under + m['opp'] * oF + m['impl'] * impl
        adj = fp - (m['c'] + m['base'] * base['fp'] + m['spLess'] * 0.5 + m['opp'] * 1.0)   # this week's situation vs a neutral week for the same player
        m = M['rec']; rec = max(0, m['c'] + m['base'] * base['rec'] + m['under'] * under) if base['rec'] >= 0.5 else base['rec']
        m = M['recYds']; recY = max(0, m['c'] + m['base'] * base['recYds'] + m['under'] * under + m['opp'] * oR) if base['recYds'] >= 10 else base['recYds']
        if pos == 'QB':
            m = M['passYds']; passY = m['c'] + m['base'] * base['passYds'] if base['passYds'] >= 100 else base['passYds']
            m = M['qbRush']; rushY = m['c'] + m['base'] * base['rushYds'] if base['rushYds'] >= 5 else base['rushYds']
        else:
            passY = 0.0
            m = M['rushYds']; rushY = max(0, m['c'] + m['base'] * base['rushYds'] + m['spLess'] * spLess + m['fav'] * fav) if base['rushYds'] >= 15 else base['rushYds']
        act = games.get((t, pid))
        out.append({'id': pid, 'name': r['name'], 'team': r['team'], 'opp': r['opp'], 'pos': pos, 'depth': r.get('depth'), 'game': r['game'], 'time': r['time'],
                    'n': n, 'fp': round(fp, 1), 'adj': round(adj, 2), 'rec': round(rec, 1), 'recYds': round(recY), 'rushYds': round(rushY), 'passYds': round(passY),
                    'avg': {k: round(v, 1) for k, v in base.items()}, 'opps2': round(opps2, 1), 'oppsAll': round(oppsAll, 1),
                    'oppF': round(oF, 2), 'oppRec': round(oR, 2), 'oppPass': round(oP, 2), 'spTeam': None if spTeam is None else round(spTeam, 3), 'spTape': round(spT),
                    'spLess': spLess, 'under': under, 'overShare': None if overShare is None else round(overShare, 3), 'implied': r.get('implied'), 'spread': r.get('spread'),
                    'tdProb': r.get('prob'), 'act': None if not act else {k: act[k] for k in ('fp', 'rec', 'recYds', 'rushYds', 'passYds', 'tgt', 'att')}})
    # rank within position: START / FLEX / SIT, plus BOOM / BUST / RISING tags
    cut = {'QB': (12, 12), 'RB': (24, 36), 'WR': (30, 42), 'TE': (12, 18)}
    for pos, (s, f) in cut.items():
        ps = sorted([x for x in out if x['pos'] == pos], key=lambda x: -x['fp'])
        for i, x in enumerate(ps):
            x['rank'] = i + 1; x['v'] = 'START' if i < s else 'FLEX' if i < f and pos != 'QB' else 'SIT'
    for x in out:
        tags = []
        # Tags read THIS WEEK's situation only (money, totals crowd, matchup, team total), measured against his normal projection (same
        # player, neutral week). Comparing to his raw average instead tagged every star a BUST, which is just regression to the mean.
        # Weeks 3-6: situation 1+ pt below normal -> fell 2.2 short of his normal (-2.3/-1.9/-2.2/-2.3, every week);
        #            0.5+ above -> +1.3 (+0.0/+2.4/+3.1/-0.4: a lean).
        if x['avg']['fp'] >= 4 and x['adj'] >= 0.5: tags.append('BOOM')
        if x['avg']['fp'] >= 4 and x['adj'] <= -1.0: tags.append('BUST')
        if x['n'] >= 3 and x['oppsAll'] >= 4 and x['opps2'] >= 1.3 * x['oppsAll'] and x['avg']['fp'] < 12: tags.append('RISING')
        x['tags'] = tags
    return out

proj = {t: project(t) for t in weeks if wn(t) >= 3}
cur = max(proj, key=wn) if proj else None
# self-check on finished weeks: how far off were the projections, and how did the tags do (each week projected only from earlier weeks)
check = []
for t in sorted(proj, key=wn):
    done = [x for x in proj[t] if x['act']]
    if len(done) < 30: continue
    mae = lambda k, xs: sum(abs(x[k] - x['act'][k]) for x in xs) / len(xs) if xs else None
    sk = [x for x in done if x['avg']['fp'] >= 5]
    tag = lambda nm: [x for x in sk if nm in x['tags']]
    norm = lambda x: x['fp'] - x['adj']                                       # his projection in a neutral week
    beat = lambda xs: (round(sum(x['act']['fp'] - norm(x) for x in xs) / len(xs), 1) if xs else None, len(xs))   # avg points vs his normal projection, and how many
    check.append({'week': t, 'n': len(done), 'maeFp': round(mae('fp', sk), 1), 'maeAvgOnly': round(sum(abs(x['avg']['fp'] - x['act']['fp']) for x in sk) / len(sk), 1) if sk else None,
                  'maeRec': round(mae('recYds', [x for x in done if x['avg']['recYds'] >= 15]) or 0, 1), 'maeRush': round(mae('rushYds', [x for x in done if x['pos'] == 'RB' and x['avg']['rushYds'] >= 20]) or 0, 1),
                  'boom': beat(tag('BOOM')), 'bust': beat(tag('BUST')), 'rest': beat([x for x in sk if not ({'BOOM', 'BUST'} & set(x['tags']))])})

# ---- prop bets: Kalshi's main yardage lines vs the one prop rule that held (props_rules.py), graded from the box scores ----
import props_rules as PR
norm = lambda n: re.sub(r'[^a-z]', '', (n or '').lower().replace(' jr.', '').replace(' jr', '').replace(' sr.', '').replace(' iii', '').replace(' ii', ''))
kfee = lambda p: 0.07 * p * (1 - p)
def props_week(t):
    """weeks with history use the price at kickoff (research/, +1c slippage); this week uses the live ask (backtest/nflprops_<week>.json)"""
    hp, lp = os.path.join(HERE, 'research', f'nflprops_{t}.json'), os.path.join(BT, f'nflprops_{t}.json')
    hist = os.path.exists(hp); src = J(hp) if hist else (J(lp) if os.path.exists(lp) else {})
    if not src: return []
    who = {norm(r['name']): r for r in locks.get(t, [])}
    mf = os.path.join(BT, f'ml_{t}.json'); ml = {str(g['eventId']): g for g in J(mf)} if os.path.exists(mf) else {}
    act = {norm(g['name']): g for (w, pid), g in games.items() if w == t}
    out = []
    for ev, g in src.items():
        if hist:
            ms = [dict(m, name=(m.get('title') or '').split(':')[0].strip()) for m in g['markets'] if m.get('pxKick') is not None and 'Protected' not in (m.get('title') or '')]
            mid = lambda m: m['pxKick']
        else:
            ms = g['markets']; mid = lambda m: (m['ask'] + m['bid']) / 2 if m.get('ask') and m.get('bid') else None
        for m in PR.main_lines(ms, mid):
            r = who.get(norm(m['name']))
            if not r: continue
            pos = (r.get('pos') or '')[:2]; gm = ml.get(str(r['eventId'])) or {}; k = gm.get('kalshi')
            winP = None if k is None else (k if gm.get('home') == r['team'] else 1 - k)
            v, side = PR.verdict(pos, m['series'], winP)
            if not side: continue
            px = mid(m)
            if hist: cost = (px if side == 'OVER' else 1 - px) + 0.01
            else: cost = m['ask'] if side == 'OVER' else (1 - m['bid'] if m.get('bid') else None)
            if not cost: continue
            a = act.get(norm(m['name'])); val = a[PR.STAT[m['series']]] if a else None
            out.append({'name': m['name'], 'team': r['team'], 'opp': r['opp'], 'pos': pos, 'game': r['game'], 'time': r['time'], 'stat': PR.LABEL[m['series']],
                        'line': float(m['strike']), 'side': side, 'price': round(cost, 3), 'cost': round(min(0.99, cost + kfee(cost)), 3), 'winP': None if winP is None else round(winP, 3),
                        'v': v or 'PASS', 'actual': val, 'hit': None if val is None else int((val > float(m['strike'])) == (side == 'OVER')), 'hist': hist})
    return sorted(out, key=lambda x: (x['v'] != 'BET', x['time'], x['name']))
props = {t: props_week(t) for t in weeks}
props = {t: v for t, v in props.items() if v}

def page():
    from navbar import navbar, week_label
    ws = sorted(proj, key=wn, reverse=True)
    nav = navbar('fantasy', '', {'mlb': [], 'nfl': [(w, week_label(w), '') for w in ws]}, {'nfl': cur}, fixed='nfl')
    return f"""<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fade The Chalk</title>{FONTS}{CSS}<header><h1><a href="index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">fantasy start / sit · waiver risers · yardage projections · built {datetime.datetime.now().isoformat(timespec="minutes")}</div></header>{nav}
<style>.tg{{display:inline-block;font-size:11px;font-weight:700;border-radius:4px;padding:1px 6px;margin-left:4px}}.tg.BOOM{{background:#123d26;color:var(--good)}}.tg.BUST{{background:#4a1218;color:var(--bad)}}.tg.RISING{{background:#12304a;color:var(--blue)}}
.lin{{width:62px;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:5px;padding:3px 5px;font:13px var(--mono)}}.lean{{font-size:12px;font-weight:700}}.lean.o{{color:var(--good)}}.lean.u{{color:var(--warn)}}
.pt{{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}}.pt button{{background:var(--panel);color:var(--mute);border:1px solid var(--line);border-radius:999px;padding:6px 14px;font:700 12px var(--font);cursor:pointer}}.pt button.on{{color:var(--ink);border-color:var(--acc)}}
td.act{{color:var(--mute)}}</style>
<div class="panel top">
<div class="kpi" id="kpi"></div>
<h2 style="margin:10px 0 6px">Prop bets <small>Kalshi / Robinhood main lines</small></h2>
<div class="wrap"><table class="lt" id="props"></table></div>
<div class="legend"><b>The prop rule.</b> Main line = the strike priced nearest 50¢. <b>BET</b> = a player on the <b>underdog</b> (his team under 45% to win on Kalshi), with one of: <b>RB rushing yards UNDER</b>, <b>QB rushing yards UNDER</b>, <b>TE receiving yards UNDER</b>, <b>QB passing yards OVER</b>. That made <b>+11.8% on 358 bets</b> at the price at kickoff plus the fee, and it was positive in all 6 weeks (+3, +17, +21, +12, +4, +13%). It was found on weeks 1-4 and held on weeks 5-6, which weren't used to find it. The same four props on favorites were break-even, so they show as PASS. Edges are single digits per bet: it pays over many bets, not on one. <b>Not a bet:</b> first-TD and 2+ TD props (they lost 35-47% every week), overs in general (−9%), and our own projections vs the line (they lost at every threshold). For anytime TDs, use the BET / AVOID calls on the main board.</div>
<div id="propScore"></div>
<h2 style="margin:16px 0 6px">Start / sit</h2>
<div class="pt" id="posTabs"><button data-p="ALL">All</button><button data-p="QB">QB</button><button data-p="RB">RB</button><button data-p="WR">WR</button><button data-p="TE">TE</button><button data-p="RISING">Waiver risers</button></div>
<div class="ctl"><label>scoring <select id="scoring"><option value="half">half-PPR</option><option value="ppr">PPR</option><option value="std">standard</option></select></label><label>search <input id="q" placeholder="player or team"></label><label><input type="checkbox" id="hidestart"> hide started games</label></div>
<div class="wrap"><table id="tbl" class="lt"><thead><tr><th data-k="rank">#</th><th data-k="name">Player</th><th data-k="game">Game</th><th class="num" data-k="pts">Proj pts</th><th class="num" data-k="avgPts">2026 avg</th><th data-k="v">Start / sit</th><th class="num" data-k="rec">Rec</th><th class="num" data-k="recYds">Rec yds</th><th class="num" data-k="rushYds">Rush yds</th><th class="num" data-k="passYds">Pass yds</th><th class="num" data-k="oppF">Matchup</th><th class="num" data-k="spTeam">Spread $ on team</th><th class="num" data-k="opps2">Touches+tgts L2</th><th>Your line</th><th class="num" data-k="actPts">Actual</th></tr></thead><tbody></tbody></table></div>
<div class="legend"><b>How to read it.</b> <b>Proj pts</b> = projected fantasy points. It starts from his 2026 average, pulled toward the middle (early-season games are noisy), then nudged by what has held every week so far: players on the team with <i>less</i> of the crowd's spread money have beaten their average by about 2 points more than players on the crowd's team (running backs: about 12 more rushing yards); when the crowd's totals money is on the <b>under</b>, players have come in about 2 points and 8 receiving yards short; and the <b>Matchup</b> number is what the opponent has allowed to his position per game against the league (1.20 = 20% more, a soft matchup; 0.80 = a tough one). <b>START / FLEX / SIT</b> = his projected rank at the position (QB top 12, RB top 24 start / 36 flex, WR 30 / 42, TE 12 / 18). <b>BOOM</b> / <b>BUST</b> read only this week's situation (the money, the totals crowd, the matchup, the team total) against a normal week for the same player, so stars aren't tagged just for being stars. <b>BUST</b> = the situation puts him 1+ point below his normal: those players fell about 2.2 points short of it in every week so far (the most reliable tag here; usually the crowd's money is on his team and on the under). <b>BOOM</b> = 0.5+ above his normal: +1.3 on average, but only 2 of 4 weeks clearly positive, so a lean. <b>RISING</b> = his targets + carries over the last 2 games are 30%+ above his season rate: a waiver flag, not proven yet (only 37 players so far, about break-even). <b>Your line</b>: type the yardage line from your book (receiving yards for WR/TE, rushing for RB, passing for QB) and the page shows the chance of the over from the projection and how far real outcomes spread around it (about ±25 yards receiving/rushing, ±55 passing). It calls a lean only at 60%+. These are for fantasy, <b>not betting</b>: checked against Kalshi's real lines for weeks 3-4, betting wherever the projection disagreed with the price lost money. For yardage bets, use the Prop bets table above. Spread money moves until kickoff, so recheck close to the game. Finished weeks show the actual line and the scorecard below shows how each week's projections did (every week projected only from the weeks before it).</div>
<h2 style="margin-top:18px">How the projections did</h2><div class="wrap"><table class="lt"><thead><tr><th>Week</th><th class="num">Players</th><th class="num">Avg miss, pts</th><th class="num">…using his plain average</th><th class="num">Rec yds miss</th><th class="num">Rush yds miss</th><th class="num">BOOM vs his normal</th><th class="num">BUST vs his normal</th><th class="num">Others vs his normal</th></tr></thead><tbody id="chk"></tbody></table></div>
</div>
<script>const PROJ = {jd(proj)}; const CUR = {jd(cur)}; const CHECK = {jd(check)}; const PROPS = {jd(props)};{JS}</script>"""

JS = r"""
const $ = s => document.querySelector(s); let week = CUR, pos = 'ALL', sortKey = 'pts', sortDir = -1;
window.onNavSport = s => { if (s === 'mlb') { location.href = 'index.html#mlb'; return true; } return true; };
window.onNavSlate = (sp, v) => { week = v; render(); };
let lines = {}; try { lines = JSON.parse(localStorage.getItem('ftc_ff_lines') || '{}'); } catch (e) {}
const saveLines = () => { try { localStorage.setItem('ftc_ff_lines', JSON.stringify(lines)); } catch (e) {} };
const sc = () => $('#scoring').value;
const pts = (x, a) => { const base = a ? x.act.fp : x.fp, rec = a ? x.act.rec : x.rec; return sc() === 'ppr' ? base + 0.5 * rec : sc() === 'std' ? base - 0.5 * rec : base; };
const avgPts = x => sc() === 'ppr' ? x.avg.fp + 0.5 * x.avg.rec : sc() === 'std' ? x.avg.fp - 0.5 * x.avg.rec : x.avg.fp;
const when = t => new Date(t).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
const statFor = x => x.pos === 'QB' ? ['passYds', 'pass', 71] : x.pos === 'RB' ? ['rushYds', 'rush', 31.4] : ['recYds', 'rec', 32.3];
const Phi = z => { const t = 1 / (1 + 0.2316419 * Math.abs(z)), d = 0.3989423 * Math.exp(-z * z / 2), p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return z > 0 ? 1 - p : p; };
function leanCell(x){ const [k, lab, sd] = statFor(x), key = week + '|' + x.id, L = lines[key];
  let out = `<input class="lin" data-k="${key}" placeholder="${lab}" value="${L ?? ''}">`;
  if (L !== undefined && L !== '' && !isNaN(+L)) { const pOver = 1 - Phi((+L + 0.5 - x[k]) / sd);
    out += pOver >= 0.6 ? ` <span class="lean o">OVER ${Math.round(pOver * 100)}%</span>` : pOver <= 0.4 ? ` <span class="lean u">UNDER ${Math.round((1 - pOver) * 100)}%</span>` : ` <span class="tm">${Math.round(pOver * 100)}% over</span>`;
    if (x.act) out += ` <span class="tm">${x.act[k] > +L ? '✓ over' : '✓ under'}</span>`; }
  return out; }
function renderProps(){
  const xs = PROPS[week] || [], hide = $('#hidestart').checked;
  const list = xs.filter(x => x.v === 'BET' || !hide).filter(x => !hide || x.hist || new Date(x.time).getTime() > Date.now());
  const head = '<tr><th>Player</th><th>Game</th><th>Prop</th><th class="num">Price</th><th class="num">Team win %</th><th>Verdict</th><th class="num">Actual</th></tr>';
  $('#props').innerHTML = head + (list.map(x => `<tr><td><span class="nm">${x.name}</span> <span class="tm">${x.pos} · ${x.team}</span></td><td class="tm">${x.game}<br>${when(x.time)}</td>
    <td class="nm">${x.side} ${x.line} ${x.stat}</td><td class="num">${Math.round(x.price * 100)}¢</td><td class="num ${x.winP != null && x.winP < .45 ? 'pos' : ''}">${x.winP == null ? '—' : Math.round(x.winP * 100) + '%'}</td>
    <td><span class="v ${x.v === 'BET' ? 'BET' : 'PASS'}">${x.v}</span>${x.v === 'PASS' ? ' <span class="tm">team not the underdog</span>' : ''}</td>
    <td class="num">${x.actual == null ? '—' : x.actual + (x.v === 'BET' ? (x.hit ? ' <span class="res y">✓</span>' : ' <span class="res n">✗</span>') : ' <span class="tm">' + (x.hit ? 'won' : 'lost') + ' (no bet)</span>')}</td></tr>`).join('') ||
    '<tr><td colspan="7" class="tm" style="text-align:center;padding:14px">no Kalshi prop lines yet for this week: they post a few days before each game</td></tr>');
  // scorecard: every graded BET, by week
  const wks = Object.keys(PROPS).sort((a, b) => +a.split('wk')[1] - +b.split('wk')[1]);
  const rec = b => { const w = b.filter(x => x.hit).length, u = b.reduce((s, x) => s + (x.hit ? 1 / x.cost - 1 : -1), 0); return b.length ? `${w}-${b.length - w} · <span class="${u >= 0 ? 'pos' : 'neg'}">${u >= 0 ? '+' : ''}${u.toFixed(1)}u (${Math.round(u / b.length * 100)}%)</span>` : '—'; };
  const g = k => wks.flatMap(w => PROPS[w]).filter(x => x.hit != null && k(x));
  $('#propScore').innerHTML = '<div class="wrap"><table class="lt"><thead><tr><th>Prop scorecard (1u per bet at the price + fee)</th>' + wks.map(w => `<th class="num">Wk ${w.split('wk')[1]}</th>`).join('') + '<th class="num">All</th></tr></thead><tbody>' +
    [['BET (underdog)', x => x.v === 'BET'], ['same props, team not the underdog (no bet)', x => x.v !== 'BET']].map(([n, k]) =>
      `<tr><td class="nm">${n}</td>` + wks.map(w => `<td class="num">${rec(PROPS[w].filter(x => x.hit != null && k(x)))}</td>`).join('') + `<td class="num">${rec(g(k))}</td></tr>`).join('') + '</tbody></table></div>';
}
function render(){
  renderProps();
  const rows = (PROJ[week] || []).filter(x => (pos === 'ALL' || (pos === 'RISING' ? x.tags.includes('RISING') : x.pos === pos)) && (!$('#hidestart').checked || new Date(x.time).getTime() > Date.now()));
  const q = ($('#q').value || '').toLowerCase(); const list = rows.filter(x => !q || (x.name + ' ' + x.team + ' ' + x.opp).toLowerCase().includes(q));
  const val = x => ({ rank: x.rank, name: x.name, game: x.time, pts: pts(x), avgPts: avgPts(x), v: x.v, rec: x.rec, recYds: x.recYds, rushYds: x.rushYds, passYds: x.passYds, oppF: x.oppF, spTeam: x.spTeam ?? -1, opps2: x.opps2, actPts: x.act ? pts(x, true) : -99 })[sortKey];
  list.sort((a, b) => { const A = val(a), B = val(b); return (A > B ? 1 : A < B ? -1 : 0) * sortDir; });
  document.querySelectorAll('#tbl thead th[data-k]').forEach(th => { th.textContent = th.dataset.l + (th.dataset.k === sortKey ? (sortDir < 0 ? ' ▼' : ' ▲') : ''); });
  $('#tbl tbody').innerHTML = list.slice(0, 400).map(x => `<tr><td class="num">${x.pos}${x.rank}</td><td><span class="nm">${x.name}</span> <span class="tm">${x.team}</span>${x.tags.map(t => `<span class="tg ${t}">${t}</span>`).join('')}${x.n < 2 ? ' <span class="tm" title="only one 2026 game in the data">1g</span>' : ''}</td>
    <td class="tm">${x.team === x.game.split(' ')[0] ? '@ ' : 'vs '}${x.opp}<br>${when(x.time)}</td><td class="num"><b>${pts(x).toFixed(1)}</b></td><td class="num tm">${avgPts(x).toFixed(1)}</td>
    <td><span class="v ${x.v === 'START' ? 'BET' : x.v === 'FLEX' ? 'LEAN' : 'PASS'}">${x.v}</span></td><td class="num">${x.rec ? x.rec.toFixed(1) : '—'}</td><td class="num">${x.recYds || '—'}</td><td class="num">${x.rushYds || '—'}</td><td class="num">${x.passYds || '—'}</td>
    <td class="num ${x.oppF >= 1.15 ? 'pos' : x.oppF <= 0.85 ? 'neg' : ''}" title="what ${x.opp} has allowed to ${x.pos}s per game vs the league">${x.oppF.toFixed(2)}</td>
    <td class="num" title="${x.spTape ? 'share of the $' + x.spTape.toLocaleString() + ' crowd spread money on ' + x.team + (x.spTape < 100000 ? ' (under $100k: not readable yet)' : '') : 'no spread money yet'}">${x.spTeam == null ? '—' : Math.round(x.spTeam * 100) + '%' + (x.spLess === 1 ? ' ✓' : '')}</td>
    <td class="num" title="targets + carries per game, last 2 vs the season">${x.opps2} <span class="tm">/ ${x.oppsAll}</span></td><td>${leanCell(x)}</td>
    <td class="num act">${x.act ? pts(x, true).toFixed(1) + (x.act.recYds || x.act.rushYds || x.act.passYds ? `<br><span class="tm">${x.pos === 'QB' ? x.act.passYds + ' pass' : x.pos === 'RB' ? x.act.rushYds + ' rush' : x.act.recYds + ' rec'}</span>` : '') : '—'}</td></tr>`).join('') || '<tr><td colspan="15" class="tm" style="text-align:center;padding:16px">nothing matches</td></tr>';
  document.querySelectorAll('.lin').forEach(i => i.addEventListener('change', () => { lines[i.dataset.k] = i.value.trim(); saveLines(); render(); }));
  const all = PROJ[week] || [], done = all.filter(x => x.act);
  $('#kpi').innerHTML = `<div>week<b>${week ? week.split('wk')[1] : '—'}</b></div><div>players<b>${all.length}</b></div><div>BOOM tags<b>${all.filter(x => x.tags.includes('BOOM')).length}</b></div><div>BUST tags<b>${all.filter(x => x.tags.includes('BUST')).length}</b></div><div>waiver risers<b>${all.filter(x => x.tags.includes('RISING')).length}</b></div>` + (done.length ? `<div>graded<b>${done.length}</b></div>` : '');
}
document.querySelectorAll('#tbl thead th[data-k]').forEach(th => { th.dataset.l = th.textContent; th.addEventListener('click', () => { const k = th.dataset.k; if (sortKey === k) sortDir = -sortDir; else { sortKey = k; sortDir = (k === 'name' || k === 'rank' || k === 'game') ? 1 : -1; } render(); }); });
document.querySelectorAll('#posTabs button').forEach(b => b.addEventListener('click', () => { pos = b.dataset.p; document.querySelectorAll('#posTabs button').forEach(x => x.classList.toggle('on', x === b)); if (pos !== 'ALL' && pos !== 'RISING') { sortKey = 'rank'; sortDir = 1; } render(); }));
document.querySelector('#posTabs button').classList.add('on');
['#scoring', '#q', '#hidestart'].forEach(s => $(s).addEventListener('input', render));
const f = ([d, n]) => n ? `<span class="${d >= 0 ? 'pos' : 'neg'}">${d >= 0 ? '+' : ''}${d}</span> <span class="tm">(${n})</span>` : '—';
$('#chk').innerHTML = CHECK.length ? CHECK.map(c => `<tr><td>${c.week.split('wk')[1]}</td><td class="num">${c.n}</td><td class="num">${c.maeFp}</td><td class="num tm">${c.maeAvgOnly}</td><td class="num">${c.maeRec}</td><td class="num">${c.maeRush}</td><td class="num">${f(c.boom)}</td><td class="num">${f(c.bust)}</td><td class="num">${f(c.rest)}</td></tr>`).join('') : '<tr><td colspan="9" class="tm">no finished weeks yet</td></tr>';
render();
"""

if cur:
    html = page()
    open(os.path.join(SITE, 'fantasy.html'), 'w', encoding='utf-8', newline='\n').write(html)
    print(f"fantasy.html: weeks {', '.join(sorted(proj, key=wn))}, current {cur}: {len(proj[cur])} players; check rows {len(check)}")
