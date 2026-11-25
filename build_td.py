"""Render docs/firsttd.html: first-touchdown and 2+ touchdown chances for every NFL player, worked out from Kalshi's anytime-TD prices,
next to Kalshi's own first-TD / 2+ prices, each player's 2026 history and (for finished games) what happened.

How the chances are worked out (the same for every game):
  * anytime-TD price p  ->  expected touchdowns  lam = -ln(1 - p)          (Poisson: P(no TD) = e^-lam)
  * first TD            =  lam / (sum of lam over everyone in the game)   (each player's share of the game's expected TDs)
  * 2+ TDs              =  1 - e^-lam * (1 + lam)
  * team scores first   =  the sum of its players' first-TD shares
Finished games use the price at kickoff and the settlement (research/nflprops_<week>.json); this week's use the live ask / bid
(backtest/nflprops_<week>.json, refreshed hourly by nflprops.py). First scorers come from research/first_td_2026.json (ESPN scoring plays).
The calibration and bet tables at the bottom are computed from every finished game each build."""
import json, os, re, glob, math, datetime, unicodedata, collections
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs'); RS = os.path.join(HERE, 'research')
J = lambda p: json.load(open(p, encoding='utf-8'))
jd = lambda o: json.dumps(o, separators=(',', ':')).replace('</', '<' + chr(92) + '/')
src = open(os.path.join(HERE, 'build_site.py'), encoding='utf-8').read()
CSS = re.search(r'CSS = r"""(.*?)"""', src, re.S).group(1); FONTS = re.search(r"FONTS = '(.*?)'", src).group(1)
norm = lambda x: re.sub(r'[^a-z]', '', unicodedata.normalize('NFD', x or '').encode('ascii', 'ignore').decode().lower().replace(' jr', '').replace(' sr', '').replace(' iii', '').replace(' ii', ''))
wn = lambda t: int(t.split('wk')[1])
kfee = lambda p: 0.07 * p * (1 - p)

weeks = sorted({os.path.basename(f)[4:-5] for f in glob.glob(os.path.join(BT, 'nfl_2026_wk*.json'))}, key=wn)
locks = {t: J(os.path.join(BT, f'nfl_{t}.json')) for t in weeks}
fpath = os.path.join(RS, 'first_td_2026.json'); FIRST = J(fpath) if os.path.exists(fpath) else {}

# ---- each player's TDs by week (ESPN box scores via grade.py) and first TDs, for the history columns ----
tds = collections.defaultdict(dict)                       # norm name -> week number -> TDs that game
for t in weeks:
    rp = os.path.join(BT, f'nflres_{t}.json')
    if not os.path.exists(rp): continue
    res = J(rp)
    for r in locks[t]:
        g = res.get(str(r['id']))
        if isinstance(g, dict) and g.get('played') is not False: tds[norm(r['name'])][wn(t)] = g.get('td', 0)
firsts = collections.defaultdict(list)
for v in FIRST.values():
    if v.get('scorer'): firsts[norm(v['scorer'])].append(wn(v['week']))
def hist(n, w):
    h = {k: v for k, v in tds.get(n, {}).items() if k < w}; ks = sorted(h)
    return {'gp': len(h), 'tdg': sum(v > 0 for v in h.values()), 'tds': sum(h.values()), 'multi': sum(v >= 2 for v in h.values()),
            'first': sum(k < w for k in firsts.get(n, [])), 'last': h[ks[-1]] if ks else None}

def week_rows(t):
    """one row per player per game: anytime / first / 2+ prices, our chances, history, result"""
    hp, lp = os.path.join(RS, f'nflprops_{t}.json'), os.path.join(BT, f'nflprops_{t}.json')
    srcs = {ev: (g, False) for ev, g in (J(lp) if os.path.exists(lp) else {}).items()}
    srcs.update({ev: (g, True) for ev, g in (J(hp) if os.path.exists(hp) else {}).items()})
    who = {norm(r['name']): r for r in locks.get(t, [])}
    games = {str(r['eventId']): r for r in locks.get(t, [])}
    rp = os.path.join(BT, f'nflres_{t}.json'); res = J(rp) if os.path.exists(rp) else {}
    out, gms = [], []
    for ev, (g, hist_) in srcs.items():
        any_, first, two = {}, {}, {}
        for m in g['markets']:
            title = m.get('title') or ''
            if 'Protected' in title: continue
            nm = (m.get('name') or title.split(':')[0]).strip()
            if hist_:
                px = m.get('pxKick'); buy = None if px is None else px
            else:
                a, b = m.get('ask'), m.get('bid'); px = (a + b) / 2 if a and b else (a or b); buy = a
            if px is None: continue
            k = (m['series'], m.get('strike'))
            if k == ('KXNFLTD', 0.5): any_[nm] = (px, buy, m)
            elif k == ('KXNFLTD', 1.5): two[nm] = (px, buy, m)
            elif m['series'] == 'KXNFLFIRSTTD': first[nm] = (px, buy, m)
        if len(any_) < 6: continue
        lam = {n: -math.log(1 - min(0.97, max(0.005, v[0]))) for n, v in any_.items()}; L = sum(lam.values())
        lk = games.get(str(ev)) or next(iter([r for r in locks.get(t, []) if str(r['eventId']) == str(ev)]), None)
        game, when = (lk['game'], lk['time']) if lk else (g.get('code'), g.get('time'))
        fs = FIRST.get(str(ev)) or {}
        done = bool(fs.get('scorer') or fs.get('none')) or (hist_ and any(v[2].get('result') in ('yes', 'no') for v in any_.values()))
        team_sh = collections.defaultdict(float)
        for n in sorted(set(any_) | set(first)):
            r = who.get(norm(n)); w = wn(t)
            l = lam.get(n); qf = l / L if l else None; q2 = 1 - math.exp(-l) * (1 + l) if l else None
            if r and qf: team_sh[r['team']] += qf
            fp, f2 = first.get(n), two.get(n)
            if hist_:
                scored_first = None if fp is None else fp[2].get('result') == 'yes'
                td_n = None
                if r and isinstance(res.get(str(r['id'])), dict) and res[str(r['id'])].get('played') is not False: td_n = res[str(r['id'])].get('td', 0)
            else:
                scored_first = (norm(fs.get('scorer')) == norm(n)) if fs.get('scorer') else (False if fs.get('none') else None)
                td_n = res.get(str(r['id']), {}).get('td') if r and isinstance(res.get(str(r['id'])), dict) and res[str(r['id'])].get('played') is not False else None
            out.append({'ev': str(ev), 'game': game, 'time': when, 'name': n, 'team': r['team'] if r else '', 'pos': (r.get('pos') or '') if r else ('D/ST' if 'D/ST' in n else ''),
                        'any': round(any_[n][0], 3) if n in any_ else None, 'qf': None if qf is None else round(qf, 4), 'q2': None if q2 is None else round(q2, 4),
                        'kf': None if not fp else round(fp[1] or fp[0], 3), 'k2': None if not f2 else round(f2[1] or f2[0], 3),
                        'h': hist(norm(n), w), 'sf': scored_first, 'td': td_n, 'done': done, 'hist': hist_})
        teams = sorted(team_sh.items(), key=lambda x: -x[1]); tot = sum(v for _, v in teams) or 1
        gms.append({'ev': str(ev), 'game': game, 'time': when, 'teams': [(k, round(v / tot, 3)) for k, v in teams],
                    'first': fs.get('scorer'), 'firstTeam': fs.get('team'), 'firstText': fs.get('text'), 'done': done})
    return out, sorted(gms, key=lambda x: x['time'] or '')

DATA = {}
for t in weeks:
    rows, gms = week_rows(t)
    if rows: DATA[t] = {'rows': rows, 'games': gms}

# ---- calibration and the bets that were tested, from every finished game (price at kickoff, +1c, Kalshi fee) ----
BUCKETS = [(0, .03), (.03, .06), (.06, .10), (.10, .15), (.15, .25), (.25, 1.01)]
def study(kind):
    rows = [x for d in DATA.values() for x in d['rows'] if x['hist'] and x['k' + kind] is not None and x['q' + kind] is not None
            and (x['sf'] is not None if kind == 'f' else x['td'] is not None)]
    hit = (lambda x: x['sf']) if kind == 'f' else (lambda x: x['td'] >= 2)
    def roi(xs):
        u = 0
        for x in xs:
            c = x['k' + kind] + 0.01; c += kfee(c); u += (1 - c) / c if hit(x) else -1
        return u / len(xs) if xs else None
    cal = []
    for lo, hi in BUCKETS:
        xs = [x for x in rows if lo <= x['k' + kind] < hi]
        if xs: cal.append({'lo': lo, 'hi': hi, 'n': len(xs), 'price': sum(x['k' + kind] for x in xs) / len(xs), 'ours': sum(x['q' + kind] for x in xs) / len(xs),
                           'act': sum(1 for x in xs if hit(x)) / len(xs), 'roi': roi(xs)})
    tests = []
    for name, sel in [('every YES', lambda x: True), ('YES priced 10¢+ (the top few players)', lambda x: x['k' + kind] >= .10),
                      ('YES priced under 6¢ (longshots)', lambda x: x['k' + kind] < .06), ('YES when our chance is 25%+ above the price', lambda x: x['q' + kind] >= 1.25 * x['k' + kind])]:
        xs = [x for x in rows if sel(x)]
        if not xs: continue
        tests.append({'name': name, 'n': len(xs), 'w': sum(1 for x in xs if hit(x)), 'roi': roi(xs)})
    return {'n': len(rows), 'cal': cal, 'tests': tests}
STUDY = {'f': study('f'), '2': study('2')}
# team to score first: our share vs what happened
tf = []
for d in DATA.values():
    for g in d['games']:
        if g['first'] and g['firstTeam'] and len(g['teams']) == 2: tf.append((g['teams'][0][1], g['teams'][0][0] == g['firstTeam']))
TEAM = {'n': len(tf), 'buckets': [{'lo': lo, 'hi': hi, 'n': len(xs), 'ours': sum(a for a, _ in xs) / len(xs), 'act': sum(b for _, b in xs) / len(xs)}
                                  for lo, hi in ((.5, .55), (.55, .6), (.6, .65), (.65, 1.0)) for xs in [[x for x in tf if lo <= x[0] < hi]] if xs]}

cur = max(DATA, key=wn) if DATA else None

def page():
    from navbar import navbar, week_label
    ws = sorted(DATA, key=wn, reverse=True)
    nav = navbar('ftd', '', {'mlb': [], 'nfl': [(w, week_label(w), '') for w in ws]}, {'nfl': cur}, fixed='nfl')
    return (f"""<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>First TD</title>{FONTS}{CSS}<header><h1><a href="index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">NFL first touchdown &amp; 2+ touchdowns · worked out from Kalshi's anytime prices · built {datetime.datetime.now().isoformat(timespec="minutes")}</div></header>{nav}"""
    + """<style>
#ft th[data-k]{cursor:pointer;user-select:none;white-space:nowrap}#ft th[data-k]:hover{color:var(--ink)}#ft tbody tr:hover{background:rgba(255,255,255,.03)}
.gcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px;margin:10px 0 14px}.gc{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;cursor:pointer}
.gc:hover,.gc.on{border-color:var(--acc)}.gc .t{font-weight:800}.gc .s{color:var(--mute);font-size:12px;margin-top:2px}.bar{display:flex;height:8px;border-radius:4px;overflow:hidden;margin:8px 0 4px;background:#20262e}
.bar i{display:block;height:100%}.bar i:first-child{background:var(--acc)}.bar i+i{background:#5b6b80}.gc .r{font-size:12px;margin-top:6px}.cnt{color:var(--mute);font-size:12px}
.lt td.ls{color:var(--mute)}.tag{display:inline-block;font-size:10px;font-weight:800;border-radius:4px;padding:1px 5px;margin-left:4px;background:#20262e;color:var(--mute)}.tag.ok{background:#123d26;color:var(--good)}
.ctl button.rs{background:none;border:1px solid var(--line);color:var(--mute);border-radius:6px;padding:5px 10px;cursor:pointer;font:inherit}.hl{color:var(--good);font-weight:800}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:800px){.two{grid-template-columns:1fr}}.two>div{min-width:0;overflow-x:auto}
</style>
<div class="panel top">
<div class="kpi" id="tkpi"></div>
<h2 style="margin:6px 0 2px">Games <small>click one to show only its players · bar = chance each team scores the first TD</small></h2>
<div class="gcards" id="gcards"></div>
<div class="ctl">
 <label>search <input type="text" id="tq" placeholder="player or team" style="width:140px"></label>
 <label>position <select id="tpos"><option value="">all</option><option>QB</option><option>RB</option><option>WR</option><option>TE</option><option value="D/ST">D/ST</option></select></label>
 <label>min first-TD chance <select id="tmin"><option value="0">any</option><option value="0.03">3%+</option><option value="0.05" selected>5%+</option><option value="0.08">8%+</option><option value="0.1">10%+</option></select></label>
 <button class="rs" id="treset">reset</button> <span class="cnt" id="tcnt"></span>
</div>
<div class="wrap"><table class="lt" id="ft"><thead><tr></tr></thead><tbody></tbody></table></div>
<p class="tm" style="font-size:12px">Click a column to sort (again to flip) · <b>Kalshi</b> = the price to buy YES now (finished games: the price at kickoff) · <span class="tag ok">fair</span> = Kalshi's price is at or under our chance · <span class="tag">longshot</span> = under 6¢, the prices that lost ~40% · filters are remembered on this device.</p>
<h2 style="margin:18px 0 6px">How it's worked out</h2>
<div class="legend">Everything comes from one number per player: Kalshi's <b>anytime TD</b> price, the most traded and most accurate TD market. A 30¢ anytime price means a 30% chance of at least one TD, which works out to <b>0.36 expected TDs</b> (expected TDs = −ln(1 − price)). Then:<br>
• <b>First TD</b> = his expected TDs ÷ everyone in the game's expected TDs. If he has 0.36 and the game totals 4.5, he has 8% of the game's touchdowns, so an 8% chance to score the first one (fair odds +1150).<br>
• <b>2+ TDs</b> = 1 − e<sup>−λ</sup>(1 + λ), the chance of two or more when TDs land at random at his rate. At 0.36 expected TDs that's 5%.<br>
• <b>Team scores first</b> = the sum of its players' first-TD chances.<br>
<b>Season</b> columns are his 2026 games before this week: games with a TD / games played, total TDs, games with 2+ TDs, how many times he scored his game's first TD, and TDs last game. They're for context: in weeks 1-11, players who had scored first before, had a 2+ game, or scored in half their games did no better than their price said once the price was known. <b>The price already has the history in it.</b></div>
<div class="two" style="margin-top:12px"><div><h3 style="margin:4px 0">First TD: price vs what happened</h3><table class="lt" id="calf"></table></div><div><h3 style="margin:4px 0">2+ TDs: price vs what happened</h3><table class="lt" id="cal2"></table></div></div>
<div class="two" style="margin-top:12px"><div><h3 style="margin:4px 0">Bets tested (1u at kickoff price + 1¢ + fee)</h3><table class="lt" id="bets"></table></div><div><h3 style="margin:4px 0">Team to score first</h3><table class="lt" id="teamcal"></table></div></div>
<div class="legend" style="margin-top:10px"><b>What the numbers say.</b> Our chances line up with Kalshi's own first-TD and 2+ prices, and both line up with what happened, except at the bottom: <b>longshots are overpriced</b>. Players priced 3-6¢ to score first actually did it about 2.4% of the time, so buying every first-TD or 2+ YES lost about 40%. The few players priced 10¢+ came out close to fair (some weeks up, some down), and no rule from price, money or history beat the price in both halves of the season. <b>Use this page to price a bet, not to find one:</b> if your book offers a first-TD or 2+ price better than the fair odds here, that's value; at Kalshi's own price it usually isn't. For anytime TDs, the BET / AVOID calls on the Touchdowns page are the tested rule.</div>
</div>
""" + f"<script>const D = {jd(DATA)}; const CUR = {jd(cur)}; const ST = {jd(STUDY)}; const TEAM = {jd(TEAM)};" + JS + "</script>")

JS = r"""
const $ = s => document.querySelector(s); let week = CUR;
window.onNavSport = s => { if (s === 'mlb') { location.href = 'index.html#mlb'; return true; } return true; };
window.onNavSlate = (sp, v) => { week = v; G = ''; render(); };
const store = { get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} } };
let F = Object.assign({ q: '', pos: '', min: '0.05' }, store.get('ftc_td_f', {})), S = store.get('ftc_td_s', { k: 'qf', d: -1 }), G = '';
const save = () => { store.set('ftc_td_f', F); store.set('ftc_td_s', S); };
const when = t => t ? new Date(t).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : '';
const pct = (p, d = 0) => p == null ? '—' : (p * 100).toFixed(d) + '%';
const odds = p => !p ? '—' : p >= .5 ? '−' + Math.round(100 * p / (1 - p)) : '+' + Math.round(100 * (1 - p) / p);
const ck = p => p == null ? '<span class="tm">—</span>' : Math.round(p * 100) + '¢';
const tag = (k, q) => k == null || q == null ? '' : k < .06 ? '<span class="tag">longshot</span>' : k + .01 <= q ? '<span class="tag ok">fair</span>' : '';
const COLS = [
  { k: 'name', l: 'Player', v: x => x.name },
  { k: 'game', l: 'Game', v: x => (x.time || '') + x.game },
  { k: 'any', l: 'Anytime', v: x => x.any ?? -1, n: 1 },
  { k: 'qf', l: 'First TD (ours)', v: x => x.qf ?? -1, n: 1 },
  { k: 'kf', l: 'Kalshi 1st', v: x => x.kf ?? -1, n: 1 },
  { k: 'q2', l: '2+ TDs (ours)', v: x => x.q2 ?? -1, n: 1 },
  { k: 'k2', l: 'Kalshi 2+', v: x => x.k2 ?? -1, n: 1 },
  { k: 'tdg', l: 'TD games', v: x => x.h.gp ? x.h.tdg / x.h.gp : -1, n: 1 },
  { k: 'tds', l: 'TDs', v: x => x.h.tds, n: 1 },
  { k: 'multi', l: '2+ games', v: x => x.h.multi, n: 1 },
  { k: 'first', l: '1st TDs', v: x => x.h.first, n: 1 },
  { k: 'res', l: 'Result', v: x => (x.sf ? 100 : 0) + (x.td ?? -1), n: 1 } ];
function render() {
  const d = D[week] || { rows: [], games: [] }, now = Date.now();
  if (G && !d.games.some(g => g.ev === G)) G = '';
  $('#gcards').innerHTML = d.games.map(g => { const [a, b] = g.teams, sa = a ? Math.round(a[1] * 100) : 50;
    return `<div class="gc ${g.ev === G ? 'on' : ''}" data-ev="${g.ev}"><div class="t">${g.game}</div><div class="s">${when(g.time)}${g.done ? ' · final' : ''}</div>
      ${a && b ? `<div class="bar"><i style="width:${sa}%"></i><i style="width:${100 - sa}%"></i></div><div class="s"><b style="color:var(--ink)">${a[0]} ${sa}%</b> · ${b[0]} ${100 - sa}% to score first</div>` : ''}
      ${g.first ? `<div class="r">1st TD: <b>${g.first}</b> <span class="tm">${g.firstTeam || ''}</span></div>` : g.done ? '<div class="r tm">first scorer not in yet</div>' : ''}</div>`; }).join('') || '<div class="tm">no Kalshi TD prices for this week yet</div>';
  document.querySelectorAll('.gc').forEach(c => c.onclick = () => { G = G === c.dataset.ev ? '' : c.dataset.ev; render(); });
  $('#tq').value = F.q; $('#tpos').value = F.pos; $('#tmin').value = F.min;
  const q = F.q.trim().toLowerCase(), min = +F.min;
  const c = COLS.find(c => c.k === S.k) || COLS[3];
  const list = d.rows.filter(x => (!G || x.ev === G) && (!F.pos || x.pos === F.pos) && (x.qf ?? 0) >= min && (!q || (x.name + ' ' + x.team + ' ' + x.game).toLowerCase().includes(q)))
    .sort((a, b) => { const A = c.v(a), B = c.v(b); return (A > B ? 1 : A < B ? -1 : 0) * S.d; });
  $('#ft thead tr').innerHTML = COLS.map(x => `<th data-k="${x.k}"${x.n ? ' class="num"' : ''}>${x.l}${x.k === S.k ? (S.d > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('');
  document.querySelectorAll('#ft th[data-k]').forEach(th => th.onclick = () => { const k = th.dataset.k; if (S.k === k) S.d = -S.d; else { S.k = k; S.d = COLS.find(x => x.k === k).n ? -1 : 1; } save(); render(); });
  $('#ft tbody').innerHTML = list.map(x => `<tr><td><span class="nm">${x.name}</span> <span class="tm">${x.pos}${x.team ? ' · ' + x.team : ''}</span></td>
    <td class="tm">${x.game}<br>${when(x.time)}</td><td class="num">${ck(x.any)}</td>
    <td class="num"><b>${pct(x.qf, 1)}</b><br><span class="tm">${odds(x.qf)}</span></td><td class="num">${ck(x.kf)}${tag(x.kf, x.qf)}</td>
    <td class="num"><b>${pct(x.q2, 1)}</b><br><span class="tm">${odds(x.q2)}</span></td><td class="num">${ck(x.k2)}${tag(x.k2, x.q2)}</td>
    <td class="num ls">${x.h.gp ? x.h.tdg + '/' + x.h.gp : '—'}${x.h.last != null ? '<br><span class="tm">last: ' + x.h.last + '</span>' : ''}</td><td class="num ls">${x.h.gp ? x.h.tds : '—'}</td><td class="num ls">${x.h.gp ? x.h.multi : '—'}</td><td class="num ls">${x.h.first || (x.h.gp ? 0 : '—')}</td>
    <td class="num">${x.sf ? '<span class="hl">1st TD ✓</span><br>' : ''}${x.td == null ? (x.done ? '<span class="tm">—</span>' : '') : x.td + ' TD' + (x.td === 1 ? '' : 's') + (x.td >= 2 ? ' <span class="res y">2+</span>' : '')}</td></tr>`).join('')
    || `<tr><td colspan="${COLS.length}" class="tm" style="text-align:center;padding:16px">${d.rows.length ? 'nothing matches these filters' : 'no Kalshi TD prices yet: they post a few days before each game'}</td></tr>`;
  $('#tcnt').textContent = `showing ${list.length} of ${d.rows.length}`;
  const open = d.games.filter(g => !g.done && new Date(g.time).getTime() > now).length;
  $('#tkpi').innerHTML = `<div>week<b>${week ? week.split('wk')[1] : '—'}</b></div><div>games<b>${d.games.length}</b></div><div>not kicked off<b>${open}</b></div><div>games studied<b>${TEAM.n}</b></div>`;
}
const calT = (s, lab) => '<thead><tr><th>Kalshi price</th><th class="num">n</th><th class="num">price</th><th class="num">ours</th><th class="num">happened</th><th class="num">buy every YES</th></tr></thead><tbody>' +
  s.cal.map(b => `<tr><td>${Math.round(b.lo * 100)}–${b.hi > 1 ? '100' : Math.round(b.hi * 100)}¢</td><td class="num">${b.n}</td><td class="num">${pct(b.price, 1)}</td><td class="num">${pct(b.ours, 1)}</td><td class="num"><b>${pct(b.act, 1)}</b></td><td class="num ${b.roi >= 0 ? 'pos' : 'neg'}">${b.roi >= 0 ? '+' : ''}${Math.round(b.roi * 100)}%</td></tr>`).join('') + '</tbody>';
$('#calf').innerHTML = calT(ST.f); $('#cal2').innerHTML = calT(ST['2']);
$('#bets').innerHTML = '<thead><tr><th>Bet</th><th class="num">Record</th><th class="num">ROI</th></tr></thead><tbody>' +
  [['First TD', ST.f], ['2+ TDs', ST['2']]].flatMap(([n, s]) => s.tests.map(t => `<tr><td>${n}: ${t.name}</td><td class="num">${t.w}-${t.n - t.w}</td><td class="num ${t.roi >= 0 ? 'pos' : 'neg'}">${t.roi >= 0 ? '+' : ''}${(t.roi * 100).toFixed(1)}%</td></tr>`)).join('') + '</tbody>';
$('#teamcal').innerHTML = '<thead><tr><th>Our chance for the likelier team</th><th class="num">games</th><th class="num">ours</th><th class="num">it scored first</th></tr></thead><tbody>' +
  TEAM.buckets.map(b => `<tr><td>${Math.round(b.lo * 100)}–${b.hi >= 1 ? '100' : Math.round(b.hi * 100)}%</td><td class="num">${b.n}</td><td class="num">${pct(b.ours)}</td><td class="num"><b>${pct(b.act)}</b></td></tr>`).join('') + '</tbody>';
$('#tq').oninput = e => { F.q = e.target.value; save(); render(); $('#tq').focus(); };
$('#tpos').onchange = e => { F.pos = e.target.value; save(); render(); };
$('#tmin').onchange = e => { F.min = e.target.value; save(); render(); };
$('#treset').onclick = () => { F = { q: '', pos: '', min: '0.05' }; S = { k: 'qf', d: -1 }; G = ''; save(); render(); };
render();
"""

if cur:
    open(os.path.join(SITE, 'firsttd.html'), 'w', encoding='utf-8', newline='\n').write(page())
    print(f"firsttd.html: weeks {', '.join(sorted(DATA, key=wn))}; studied {STUDY['f']['n']} first-TD and {STUDY['2']['n']} 2+ markets, {TEAM['n']} games for team-first")
