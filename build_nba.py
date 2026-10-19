"""Render docs/nba.html from backtest/nba_<date>.json (written by nba.py): moneyline, spread and total for each NBA game, Robinhood's ask vs Pinnacle's
fair price, the crowd's money on each side (Kalshi trade tape), results, and a scorecard that starts at zero. Nothing here is proven yet: the
NFL finding (the side with less of the crowd's spread money covers) is shown as an untested LEAN so the scorecard can test it on NBA games."""
import json, os, re, glob, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs')
J = lambda p: json.load(open(p, encoding='utf-8'))
jd = lambda o: json.dumps(o, separators=(',', ':')).replace('</', '<' + chr(92) + '/')
src = open(os.path.join(HERE, 'build_site.py'), encoding='utf-8').read()
CSS = re.search(r'CSS = r"""(.*?)"""', src, re.S).group(1); FONTS = re.search(r"FONTS = '(.*?)'", src).group(1)

days = {os.path.basename(p)[4:-5]: J(p) for p in sorted(glob.glob(os.path.join(BT, 'nba_*.json')))}
days = {d: rows for d, rows in days.items() if rows}
order = sorted(days, reverse=True)
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
      out.push({ r, kind: 'ml', side: team + ' ML', ask, fair, own: own || 0, tape: tot, crowd: tot ? (own || 0) / tot : null, hit: r.final ? ((r.homeWin === 1) === (k === 'home') ? 1 : 0) : null, fav: fair != null ? fair >= .5 : (ask || 0) >= .5 }); }
  if (s && s.fav) { const tot = (s['tapeFav$'] || 0) + (s['tapeDog$'] || 0);
    out.push({ r, kind: 'spread', side: s.fav + ' −' + s.line, ask: s.favAsk, fair: s.pinFavFair, own: s['tapeFav$'] || 0, tape: tot, crowd: tot ? (s['tapeFav$'] || 0) / tot : null, hit: s.favCovered ?? null, fav: true });
    out.push({ r, kind: 'spread', side: s.dog + ' +' + s.line, ask: s.dogAsk, fair: s.pinDogFair, own: s['tapeDog$'] || 0, tape: tot, crowd: tot ? (s['tapeDog$'] || 0) / tot : null, hit: s.favCovered == null ? null : 1 - s.favCovered, fav: false }); }
  if (t && t.line != null) { const tot = (t['tapeOver$'] || 0) + (t['tapeUnder$'] || 0);
    out.push({ r, kind: 'total', side: 'Over ' + t.line, ask: t.overAsk, fair: t.pinOverFair, own: t['tapeOver$'] || 0, tape: tot, crowd: tot ? (t['tapeOver$'] || 0) / tot : null, hit: t.over ?? null });
    out.push({ r, kind: 'total', side: 'Under ' + t.line, ask: t.underAsk, fair: t.pinUnderFair, own: t['tapeUnder$'] || 0, tape: tot, crowd: tot ? (t['tapeUnder$'] || 0) / tot : null, hit: t.over == null ? null : 1 - t.over }); }
  for (const x of out) { x.edge = (x.ask != null && x.fair != null) ? (x.fair - x.ask) * 100 : null;
    // UNTESTED in the NBA. Spread LEAN = the NFL rule (less of the crowd's money, once $25k+ is in). Moneyline VALUE = Robinhood 3+ points under Pinnacle.
    x.v = 'PASS';
    if (x.kind === 'spread' && x.crowd != null && x.tape >= 25000 && x.crowd < 0.5) x.v = 'LEAN';
    if (x.kind === 'ml' && x.edge != null && x.edge >= 3) x.v = 'VALUE'; }
  return out;
}
const COLS = '<tr><th>Game</th><th>Side</th><th class="num">Robinhood ask</th><th class="num">Pinnacle fair</th><th class="num">Edge</th><th class="num">Crowd share</th><th class="num">$ on side</th><th class="num">Tape $</th><th>Verdict</th><th>Result</th></tr>';
function rowHtml(x){ const r = x.r;
  const res = x.hit == null ? (r.final ? '<span class="res d">push</span>' : '<span class="res n">—</span>') : x.v === 'PASS' ? `<span class="res d">${x.hit ? 'won' : 'lost'} (no bet)</span>` : x.hit ? '<span class="res y">✓</span>' : '<span class="res n">✗</span>';
  return `<tr><td><span class="nm">${r.away} @ ${r.home}</span><br><span class="tm">${when(r.time)}${r.final ? ' · ' + r.finalAway + '-' + r.finalHome : ''}</span></td><td class="nm">${x.side}</td>
  <td class="num">${cents(x.ask)} <span class="tm">${amer(x.ask)}</span></td><td class="num">${pct(x.fair)}</td><td class="num ${x.edge == null ? '' : x.edge >= 2 ? 'pos' : x.edge <= -2 ? 'neg' : ''}">${x.edge == null ? '—' : (x.edge >= 0 ? '+' : '') + x.edge.toFixed(1)}</td>
  <td class="num"><span class="bar"><i style="width:${x.crowd == null ? 0 : x.crowd * 100}%"></i></span> ${pct(x.crowd)}</td><td class="num">${x.tape ? money(x.own) : '—'}</td><td class="num">${money(x.tape)}</td>
  <td><span class="v ${x.v === 'LEAN' ? 'LEAN' : x.v === 'VALUE' ? 'BET' : 'PASS'}" title="${x.v === 'PASS' ? '' : 'untested in the NBA: tracked on the scorecard below'}">${x.v}${x.v !== 'PASS' ? ' · untested' : ''}</span></td><td>${res}</td></tr>`; }
function render(){
  const rows = (DAYS[day] || []).slice().sort((a, b) => a.time < b.time ? -1 : 1).flatMap(sides);
  const hide = $('#hidepass').checked, list = rows.filter(x => !hide || x.v !== 'PASS');
  for (const [k, id] of [['ml', '#tM'], ['spread', '#tS'], ['total', '#tT']]) { const xs = list.filter(x => x.kind === k);
    $(id).innerHTML = COLS + (xs.map(rowHtml).join('') || '<tr><td colspan="10" class="tm" style="text-align:center;padding:14px">nothing yet: Robinhood and Pinnacle post NBA lines the day before</td></tr>'); }
  const g = DAYS[day] || []; $('#kpi').innerHTML = `<div>games<b>${g.length}</b></div><div>final<b>${g.filter(r => r.final).length}</b></div><div>spread LEANs<b>${rows.filter(x => x.v === 'LEAN').length}</b></div><div>moneyline VALUE<b>${rows.filter(x => x.v === 'VALUE').length}</b></div>`;
}
$('#hidepass').addEventListener('input', render);
// ---- scorecard: every graded side across every day ----
const G = Object.values(DAYS).flat().flatMap(sides).filter(x => x.hit != null && x.ask);
const strat = {
  'Spread LEAN (untested): less of the crowd $, $25k+': G.filter(x => x.kind === 'spread' && x.v === 'LEAN'),
  'Spread: side with MORE of the crowd $': G.filter(x => x.kind === 'spread' && x.crowd != null && x.tape >= 25000 && x.crowd >= 0.5),
  'Spread: every favorite': G.filter(x => x.kind === 'spread' && x.fav), 'Spread: every underdog': G.filter(x => x.kind === 'spread' && !x.fav),
  'Moneyline VALUE (untested): Robinhood 3+ pts under Pinnacle': G.filter(x => x.kind === 'ml' && x.v === 'VALUE'),
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
<div class="ctl"><label><input type="checkbox" id="hidepass"> show only LEAN / VALUE</label></div>
<h2 class="mk">Moneyline</h2><div class="wrap"><table class="lt" id="tM"></table></div>
<h2 class="mk">Spread</h2><div class="wrap"><table class="lt" id="tS"></table></div>
<h2 class="mk">Total</h2><div class="wrap"><table class="lt" id="tT"></table></div>
<div class="legend"><b>New board, nothing proven yet.</b> Each row is one side of a market. <b>Robinhood ask</b> = what a $1 contract on that side costs (Robinhood's NBA contracts are Kalshi's), with the American odds. <b>Pinnacle fair</b> = the sharpest book's de-vigged chance at the same line. <b>Edge</b> = fair minus ask, in points. <b>Crowd share</b> = the share of the crowd's taker dollars on that side (each pre-game trade credited to the side the bettor actually backed), frozen at tip-off.
<b>LEAN · untested</b> on a spread = the side with <i>less</i> of the crowd's money once $25k+ is in: the rule that has worked on NFL spreads (29 of 42 covered), tried here on basketball. <b>VALUE · untested</b> on a moneyline = Robinhood selling a team 3+ points under Pinnacle's fair price. Neither has an NBA record yet: the scorecard below grades them from the first game, next to every-favorite and every-underdog baselines, and real rules get set once there are a few weeks of games. Small stakes until then.</div>
<h2 style="margin-top:18px">Scorecard <small>every graded game</small></h2><div id="score"></div>
</div>
<script>const DAYS = {jd(days)}; const CUR = {jd(cur)};{JS}</script>"""

open(os.path.join(SITE, 'nba.html'), 'w', encoding='utf-8', newline='\n').write(page())   # written even before the first game, so the nav link never 404s
print(f"nba.html: {len(order)} days, showing {cur}: {len(days.get(cur, []))} games")
