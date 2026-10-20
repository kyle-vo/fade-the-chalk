"""Render docs/nba.html from backtest/nba_<date>.json (written by nba.py): moneyline, spread and total for each NBA game, Robinhood's ask vs Pinnacle's
fair price, the crowd's money on each side (Kalshi trade tape), results, and a scorecard.
Rules come from last season (research/nba_hist_2025.json: 1,086 regular-season games at Kalshi's tip-off price):
  spread BET   = the team that won its last game by 20+ (58% covered, +14%; +10% Oct-Jan, +18% Feb-Apr). STRONG when its opponent also won its last game.
  ML LEAN      = the same team on the moneyline (+8%: +12% / +4%). The spread is the better bet.
  total LEAN   = under when the total is below 220 (+18% on 74 games: small).
The NFL crowd-fade rule (less of the spread money) was break-even on NBA spreads (+0.6% on 1,128), so it is tracked on the scorecard only."""
import json, os, re, glob, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs')
J = lambda p: json.load(open(p, encoding='utf-8'))
jd = lambda o: json.dumps(o, separators=(',', ':')).replace('</', '<' + chr(92) + '/')
src = open(os.path.join(HERE, 'build_site.py'), encoding='utf-8').read()
CSS = re.search(r'CSS = r"""(.*?)"""', src, re.S).group(1); FONTS = re.search(r"FONTS = '(.*?)'", src).group(1)

days = {os.path.basename(p)[4:-5]: J(p) for p in sorted(glob.glob(os.path.join(BT, 'nba_20*.json')))}   # dated files only (not nba_pinnacle_cache.json)
days = {d: rows for d, rows in days.items() if rows}
order = sorted(days, reverse=True)
# each team's previous final (margin, from our own graded days): the blowout rule needs it at board time
_log = {}
for d in sorted(days):
    for r in days[d]:
        if r.get('final'):
            for t, m in ((r['home'], r['finalHome'] - r['finalAway']), (r['away'], r['finalAway'] - r['finalHome'])): _log.setdefault(t, []).append((r['time'], m))
for d in days:
    for r in days[d]:
        for side in ('home', 'away'):
            prev = [m for t, m in _log.get(r[side], []) if t < r['time']]
            r[side + 'Last'] = prev[-1] if prev else None
            r[side + 'Margin'] = round(sum(prev) / len(prev), 1) if prev else None; r[side + 'Gp'] = len(prev)   # season point differential per game so far
_pt = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=-7)).date().isoformat()
cur = _pt if _pt in days else (min([d for d in order if d >= _pt], default=None) or (order[0] if order else None))

JS = r"""
const $ = s => document.querySelector(s); let day = CUR;
window.onNavSlate = (sp, v) => { day = v; render(); };
const cents = p => p == null ? '—' : Math.round(p * 100) + '¢';
const amer = p => { if (!p || p <= 0 || p >= 1) return ''; return p >= .5 ? '−' + Math.round(100 * p / (1 - p)) : '+' + Math.round(100 * (1 - p) / p); };
const pct = p => p == null ? '—' : Math.round(p * 100) + '%';
const money = v => v == null ? '—' : '$' + (v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1000 ? Math.round(v / 1000) + 'k' : Math.round(v));
const when = t => new Date(t).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
// one row per market side. crowd = share of the taker $ on this side; edge = Pinnacle fair minus Robinhood ask, in points
function sides(r){
  const out = [], m = r.ml, s = r.spread, t = r.total;
  if (m && (m.homeAsk || m.pinHome != null)) { const tot = (m['tapeHome$'] || 0) + (m['tapeAway$'] || 0);
    for (const [k, team, ask, fair, own] of [['home', r.home, m.homeAsk, m.pinHome, m['tapeHome$']], ['away', r.away, m.awayAsk, m.pinAway, m['tapeAway$']]])
      out.push({ r, kind: 'ml', team, side: team + ' ML', ask, fair, own: own || 0, tape: tot, crowd: tot ? (own || 0) / tot : null, hit: r.final ? ((r.homeWin === 1) === (k === 'home') ? 1 : 0) : null, fav: fair != null ? fair >= .5 : (ask || 0) >= .5 }); }
  if (s && s.fav) { const tot = (s['tapeFav$'] || 0) + (s['tapeDog$'] || 0);
    out.push({ r, kind: 'spread', team: s.fav, side: s.fav + ' −' + s.line, ask: s.favAsk, fair: s.pinFavFair, own: s['tapeFav$'] || 0, tape: tot, crowd: tot ? (s['tapeFav$'] || 0) / tot : null, hit: s.favCovered ?? null, fav: true });
    out.push({ r, kind: 'spread', team: s.dog, side: s.dog + ' +' + s.line, ask: s.dogAsk, fair: s.pinDogFair, own: s['tapeDog$'] || 0, tape: tot, crowd: tot ? (s['tapeDog$'] || 0) / tot : null, hit: s.favCovered == null ? null : 1 - s.favCovered, fav: false }); }
  if (t && t.line != null) { const tot = (t['tapeOver$'] || 0) + (t['tapeUnder$'] || 0);
    out.push({ r, kind: 'total', side: 'Over ' + t.line, ask: t.overAsk, fair: t.pinOverFair, own: t['tapeOver$'] || 0, tape: tot, crowd: tot ? (t['tapeOver$'] || 0) / tot : null, hit: t.over ?? null });
    out.push({ r, kind: 'total', side: 'Under ' + t.line, ask: t.underAsk, fair: t.pinUnderFair, own: t['tapeUnder$'] || 0, tape: tot, crowd: tot ? (t['tapeUnder$'] || 0) / tot : null, hit: t.over == null ? null : 1 - t.over }); }
  for (const x of out) { x.edge = (x.ask != null && x.fair != null) ? (x.fair - x.ask) * 100 : null;
    // last season (1,086 games at Kalshi's tip-off price): the team coming off a 20+ point win covered 58% (+14%), both halves of the season.
    // The market expects a letdown that doesn't come. STRONG when its opponent also won its last game (+23%, smaller sample).
    const home = x.team === r.home, last = x.team ? (home ? r.homeLast : r.awayLast) : null, oppLast = x.team ? (home ? r.awayLast : r.homeLast) : null;
    x.last = last; x.blow = last != null && last >= 20;
    x.v = 'PASS';
    if (x.kind === 'spread' && x.blow) x.v = oppLast != null && oppLast > 0 ? 'STRONG BET' : 'BET';
    if (x.kind === 'ml' && x.blow) x.v = 'LEAN';
    // the better team (season point differential 4+ per game above its opponent's, 5+ games each) priced as the UNDERDOG: last season
    // +39% on the moneyline and +22% on the spread, both halves of the season, stronger as the gap grows, but only ~57 games a season
    const myM = home ? r.homeMargin : r.awayMargin, opM = home ? r.awayMargin : r.homeMargin, gpOk = Math.min(r.homeGp || 0, r.awayGp || 0) >= 5;
    x.under = x.team && gpOk && myM != null && opM != null && myM - opM >= 4 && !x.fav && (x.kind === 'ml' || x.kind === 'spread');
    if (x.under && x.v === 'PASS') x.v = 'LEAN';
    if (x.kind === 'total' && x.side.startsWith('Under') && r.total && r.total.line < 220) x.v = 'LEAN';
    x.why = [x.blow ? `${x.team} won its last game by ${last}` + (x.v === 'STRONG BET' ? ', and its opponent won its last too' : '') : '',
             x.under ? `the better team (${myM >= 0 ? '+' : ''}${myM} vs ${opM >= 0 ? '+' : ''}${opM} per game) priced as the underdog` : '',
             x.v === 'LEAN' && x.kind === 'total' ? 'total under 220' : ''].filter(Boolean).join(' · '); }
  return out;
}
// click a header to sort every table by it; click again to flip ascending / descending
let sortKey = 'game', sortDir = 1;
const HEAD = [['game', 'Game', ''], ['side', 'Side', ''], ['ask', 'Robinhood ask', 'num'], ['fair', 'Pinnacle fair', 'num'], ['edge', 'Edge', 'num'], ['crowd', 'Crowd share', 'num'], ['own', '$ on side', 'num'], ['tape', 'Tape $', 'num'], ['v', 'Verdict', ''], ['hit', 'Result', '']];
const VRANK = { 'STRONG BET': 4, 'BET': 3, 'LEAN': 2, 'PASS': 0 };
const sval = x => ({ game: x.r.time + x.r.away, side: x.side, ask: x.ask, fair: x.fair, edge: x.edge, crowd: x.crowd, own: x.tape ? x.own : null, tape: x.tape || null, v: VRANK[x.v] ?? 0, hit: x.hit })[sortKey];
const cmp = (a, b) => { const A = sval(a), B = sval(b); if (A == null && B == null) return 0; if (A == null) return 1; if (B == null) return -1; return (A > B ? 1 : A < B ? -1 : 0) * sortDir; };
const COLS = () => '<tr>' + HEAD.map(([k, l, c]) => `<th class="${c}" data-k="${k}" style="cursor:pointer">${l}${k === sortKey ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>';
document.addEventListener('click', e => { const th = e.target.closest('th[data-k]'); if (!th || !th.closest('#tM,#tS,#tT')) return;
  const k = th.dataset.k; if (k === sortKey) sortDir = -sortDir; else { sortKey = k; sortDir = (k === 'game' || k === 'side') ? 1 : -1; } render(); });
function rowHtml(x){ const r = x.r;
  const res = x.hit == null ? (r.final ? '<span class="res d">push</span>' : '<span class="res n">—</span>') : x.v === 'PASS' ? `<span class="res d">${x.hit ? 'won' : 'lost'} (no bet)</span>` : x.hit ? '<span class="res y">✓</span>' : '<span class="res n">✗</span>';
  return `<tr><td><span class="nm">${r.away} @ ${r.home}</span><br><span class="tm">${when(r.time)}${r.final ? ' · ' + r.finalAway + '-' + r.finalHome : ''}</span></td><td class="nm">${x.side}</td>
  <td class="num">${cents(x.ask)} <span class="tm">${amer(x.ask)}</span></td><td class="num">${pct(x.fair)}</td><td class="num ${x.edge == null ? '' : x.edge >= 2 ? 'pos' : x.edge <= -2 ? 'neg' : ''}">${x.edge == null ? '—' : (x.edge >= 0 ? '+' : '') + x.edge.toFixed(1)}</td>
  <td class="num"><span class="bar"><i style="width:${x.crowd == null ? 0 : x.crowd * 100}%"></i></span> ${pct(x.crowd)}</td><td class="num">${x.tape ? money(x.own) : '—'}</td><td class="num">${money(x.tape)}</td>
  <td><span class="v ${x.v.replace(' ', '')}" title="${x.why}">${x.v}</span>${x.why ? '<br><span class="tm">' + x.why + '</span>' : ''}</td><td>${res}</td></tr>`; }
function render(){
  const rows = (DAYS[day] || []).slice().sort((a, b) => a.time < b.time ? -1 : 1).flatMap(sides);
  const hide = $('#hidepass').checked, list = rows.filter(x => !hide || x.v !== 'PASS');
  for (const [k, id] of [['ml', '#tM'], ['spread', '#tS'], ['total', '#tT']]) { const xs = list.filter(x => x.kind === k).sort(cmp);
    $(id).innerHTML = COLS() + (xs.map(rowHtml).join('') || '<tr><td colspan="10" class="tm" style="text-align:center;padding:14px">nothing yet: Robinhood and Pinnacle post NBA lines the day before</td></tr>'); }
  const g = DAYS[day] || []; $('#kpi').innerHTML = `<div>games<b>${g.length}</b></div><div>final<b>${g.filter(r => r.final).length}</b></div><div>spread bets<b>${rows.filter(x => x.kind === 'spread' && x.v.endsWith('BET')).length}</b></div><div>leans<b>${rows.filter(x => x.v === 'LEAN').length}</b></div>`;
}
$('#hidepass').addEventListener('input', render);
// ---- scorecard: every graded side across every day ----
const G = Object.values(DAYS).flat().flatMap(sides).filter(x => x.hit != null && x.ask);
const strat = {
  'Spread BET: team that won its last game by 20+': G.filter(x => x.kind === 'spread' && x.blow),
  '   of which STRONG (opponent also won its last)': G.filter(x => x.kind === 'spread' && x.v === 'STRONG BET'),
  'Moneyline LEAN: same blowout team': G.filter(x => x.kind === 'ml' && x.blow),
  'LEAN: better team (season margin +4/game) priced as underdog, moneyline': G.filter(x => x.kind === 'ml' && x.under),
  'LEAN: same, spread': G.filter(x => x.kind === 'spread' && x.under),
  'Total LEAN: under when the total is below 220': G.filter(x => x.kind === 'total' && x.v === 'LEAN'),
  'Spread: side with LESS of the crowd $ (NFL rule, break-even last season)': G.filter(x => x.kind === 'spread' && x.crowd != null && x.tape >= 25000 && x.crowd < 0.5),
  'Spread: side with MORE of the crowd $': G.filter(x => x.kind === 'spread' && x.crowd != null && x.tape >= 25000 && x.crowd >= 0.5),
  'Spread: every favorite': G.filter(x => x.kind === 'spread' && x.fav), 'Spread: every underdog': G.filter(x => x.kind === 'spread' && !x.fav),
  'Moneyline: Robinhood 3+ pts under Pinnacle (untested)': G.filter(x => x.kind === 'ml' && x.edge != null && x.edge >= 3),
  'Moneyline: team with less of the crowd $': G.filter(x => x.kind === 'ml' && x.crowd != null && x.tape >= 25000 && x.crowd < 0.5),
  'Moneyline: every favorite': G.filter(x => x.kind === 'ml' && x.fav), 'Moneyline: every underdog': G.filter(x => x.kind === 'ml' && !x.fav),
  'Total: the crowd side': G.filter(x => x.kind === 'total' && x.crowd != null && x.tape >= 10000 && x.crowd > 0.5), 'Total: every over': G.filter(x => x.kind === 'total' && x.side.startsWith('Over')),
};
$('#score').innerHTML = '<div class="wrap"><table class="lt"><thead><tr><th>Strategy (1u each at the Robinhood ask)</th><th class="num">Bets</th><th class="num">Record</th><th class="num">Units</th><th class="num">ROI</th></tr></thead><tbody>' +
  Object.entries(strat).map(([n, b]) => { const w = b.filter(x => x.hit).length, u = b.reduce((s, x) => s + (x.hit ? 1 / x.ask - 1 : -1), 0);
    return `<tr><td class="nm">${n}</td><td class="num">${b.length}</td><td class="num">${w}-${b.length - w}</td><td class="num ${u >= 0 ? 'pos' : 'neg'}">${b.length ? (u >= 0 ? '+' : '') + u.toFixed(1) + 'u' : '—'}</td><td class="num">${b.length ? Math.round(u / b.length * 100) + '%' : '—'}</td></tr>`; }).join('') + '</tbody></table></div>';
render();
"""

def page():
    from navbar import navbar, day_label
    nav = navbar('nba', '', {'mlb': [], 'nfl': [], 'nba': [(d, day_label(d), '') for d in order]}, {'nba': cur}, fixed='nba')
    return f"""<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fade The Chalk</title>{FONTS}{CSS}<header><h1><a href="index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">NBA · moneyline, spread, total · Robinhood vs Pinnacle · crowd money by side · built {datetime.datetime.now().isoformat(timespec="minutes")}</div></header>{nav}
<style>h2.mk{{margin:16px 0 8px}}</style><div class="panel top">
<div class="kpi" id="kpi"></div>
<div class="ctl"><label><input type="checkbox" id="hidepass"> show only bets and leans</label></div>
<h2 class="mk">Moneyline</h2><div class="wrap"><table class="lt" id="tM"></table></div>
<h2 class="mk">Spread</h2><div class="wrap"><table class="lt" id="tS"></table></div>
<h2 class="mk">Total</h2><div class="wrap"><table class="lt" id="tT"></table></div>
<div class="legend">Each row is one side of a market. <b>Robinhood ask</b> = what a $1 contract on that side costs (Robinhood's NBA contracts are Kalshi's), with the American odds. <b>Pinnacle fair</b> = the sharpest book's de-vigged chance at the same line. <b>Crowd share</b> = the share of the crowd's taker dollars on that side, frozen at tip-off.
<b>Rules, tested on all of last season</b> (1,086 regular-season games, Kalshi's price at tip plus the fee):
<b>BET</b> on a spread = the team that <i>won its last game by 20+</i>. It covered 58% (+14%), and held in both halves of the season (+10% Oct-Jan, +18% Feb-Apr) and across favorites, underdogs, home and road. The market prices in a letdown after a blowout that doesn't come.
<b>STRONG BET</b> = the same, when its opponent also won its last game (+23%, about 125 games).
<b>LEAN</b> on a moneyline = the same team (+8%; the spread pays better). <b>LEAN</b> on a moneyline or spread also = <i>the better team priced as the underdog</i>: its season point differential is 4+ points a game better than its opponent's (5+ games each), yet it's the underdog. Last season: +39% on the moneyline, +22% on the spread, both halves of the season, and stronger as the gap grew, but only about 57 games all season, so it's a LEAN. <b>LEAN</b> on a total = the under when the total is below 220 (+18%, only 74 games).
What did <i>not</i> work last season: fading the crowd's spread money (the NFL rule, +0.6% on 1,128 games), the crowd's moneyline money, back-to-backs, win streaks, home/road. The rule needs each team's previous game, so it starts with each team's second game. Regular season only: in the playoffs it was flat.</div>
<h2 style="margin-top:18px">Scorecard <small>every graded game</small></h2><div id="score"></div>
</div>
<script>const DAYS = {jd(days)}; const CUR = {jd(cur)};{JS}</script>"""

open(os.path.join(SITE, 'nba.html'), 'w', encoding='utf-8', newline='\n').write(page())   # written even before the first game, so the nav link never 404s
print(f"nba.html: {len(order)} days, showing {cur}: {len(days.get(cur, []))} games")
