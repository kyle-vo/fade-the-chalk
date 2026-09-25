"""Render docs/lines.html: spreads and totals, Pinnacle's fair price vs Robinhood's ask at the same line, the crowd's money on each side (trade tape),
results, and a scorecard that asks the question the board exists for: does the side with more crowd money cover less often than its price says?"""
import json, os, re, glob, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs')
J = lambda p: json.load(open(p, encoding='utf-8'))
jd = lambda o: json.dumps(o).replace('</', '<' + chr(92) + '/')
src = open(os.path.join(HERE, 'build_site.py'), encoding='utf-8').read()
CSS = re.search(r'CSS = r"""(.*?)"""', src, re.S).group(1); FONTS = re.search(r"FONTS = '(.*?)'", src).group(1)

boards = {}
for lf in sorted(glob.glob(os.path.join(BT, 'lines_*.json'))):
    tag = os.path.basename(lf)[6:-5]; boards[tag] = J(lf)
mlb_days = sorted([t for t in boards if '_wk' not in t], reverse=True); nfl_weeks = sorted([t for t in boards if '_wk' in t], reverse=True)
today = mlb_days[0] if mlb_days else None; week = nfl_weeks[0] if nfl_weeks else None

def head():
    nav = ('<nav><div class="row site"><a href="index.html">Today</a><a href="ml.html">Moneyline</a><a href="lines.html" class="on">Spreads &amp; Totals</a><a href="track.html">Track</a><a href="archive.html">Archive</a></div>'
           '<div class="row mlb"><span class="lbl">MLB</span><a href="index.html#mlb">Home runs today</a><a href="ml.html#mlb">Moneyline</a><a href="#mlb" class="sportl on" data-t="mlb">Spreads &amp; Totals</a>' + ''.join(f'<a href="#" data-day="{d}" class="dayl">{d[5:]}</a>' for d in mlb_days[:8]) + '</div>'
           '<div class="row nfl"><span class="lbl">NFL</span><a href="index.html#nfl">Touchdowns this week</a><a href="ml.html#nfl">Moneyline</a><a href="#nfl" class="sportl" data-t="nfl">Spreads &amp; Totals</a>' + ''.join(f'<a href="#" data-week="{w}" class="weekl">week {w.split("wk")[1]}</a>' for w in nfl_weeks[:8]) + '</div></nav>')
    return f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fade The Chalk</title>{FONTS}{CSS}<header><h1><a href="index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">spreads &amp; totals · Pinnacle fair vs Robinhood ask at the same line · crowd money by side · built {datetime.datetime.now().isoformat(timespec="minutes")}</div></header>{nav}'

JS = r"""
const $ = s => document.querySelector(s); let tab = location.hash === '#nfl' ? 'nfl' : 'mlb'; let day = TODAY; let week = WEEK;
let sortKey = 'edge', sortDir = -1;
const pct = p => p == null ? '—' : Math.round(p * 100) + '%'; const cents = p => p == null ? '—' : Math.round(p * 100) + '¢';
const money = v => v == null ? '—' : '$' + (v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1000 ? Math.round(v / 1000) + 'k' : v);
const when = t => new Date(t).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
// one "side row" per market side: edge = Pinnacle fair minus Robinhood ask (points); crowd = share of taker $ on this side
function sides(r){
  const out = [];
  if (r.spread && r.spread.ticker) { const s = r.spread, tot = (s['tapeFav$'] || 0) + (s['tapeDog$'] || 0);
    out.push({ r, kind: 'spread', side: s.fav + ' -' + s.line, ask: s.favAsk, fair: s.pinFavFair, crowd: tot ? s['tapeFav$'] / tot : null, tape: tot, vol: s.ladderVol, hit: s.favCovered, shift: s.shift, pinLine: s.pinLine });
    out.push({ r, kind: 'spread', side: s.dog + ' +' + s.line, ask: s.dogAsk, fair: s.pinDogFair, crowd: tot ? s['tapeDog$'] / tot : null, tape: tot, vol: s.ladderVol, hit: s.favCovered == null ? null : 1 - s.favCovered, shift: s.shift, pinLine: s.pinLine }); }
  if (r.total && r.total.ticker) { const t = r.total, tot = (t['tapeOver$'] || 0) + (t['tapeUnder$'] || 0);
    out.push({ r, kind: 'total', side: 'Over ' + t.line, ask: t.overAsk, fair: t.pinOverFair, crowd: tot ? t['tapeOver$'] / tot : null, tape: tot, vol: t.ladderVol, hit: t.over, shift: t.shift, pinLine: t.pinLine });
    out.push({ r, kind: 'total', side: 'Under ' + t.line, ask: t.underAsk, fair: t.pinUnderFair, crowd: tot ? t['tapeUnder$'] / tot : null, tape: tot, vol: t.ladderVol, hit: t.over == null ? null : 1 - t.over, shift: t.shift, pinLine: t.pinLine }); }
  for (const x of out) { x.edge = (x.ask != null && x.fair != null) ? (x.fair - x.ask) * 100 : null; x.v = x.edge == null ? '—' : x.edge >= 5 ? 'STRONG BET' : x.edge >= 2 ? 'BET' : 'PASS'; }
  return out;
}
function render(){
  const rows = (tab === 'mlb' ? (BOARDS[day] || []) : (BOARDS[week] || [])).flatMap(sides);
  document.querySelector('.tab[data-t=mlb]').textContent = 'MLB ' + (day || ''); document.querySelector('.tab[data-t=nfl]').textContent = 'NFL ' + (week || '').replace('_', ' ');
  const hide = $('#onlyplays').checked, kind = $('#kind').value;
  const get = x => ({ time: x.r.time, kind: x.kind, side: x.side, ask: x.ask ?? -1, fair: x.fair ?? -1, edge: x.edge ?? -99, crowd: x.crowd ?? -1, tape: x.tape || 0, vol: x.vol || 0, v: x.v, hit: x.hit ?? -1 })[sortKey];
  const list = rows.filter(x => (!hide || x.v === 'BET' || x.v === 'STRONG BET') && (kind === 'all' || x.kind === kind)).sort((a, b) => { const A = get(a), B = get(b); return (A > B ? 1 : A < B ? -1 : 0) * sortDir; });
  document.querySelectorAll('#tbl thead th').forEach(th => th.textContent = th.dataset.l + (th.dataset.k === sortKey ? (sortDir < 0 ? ' ▼' : ' ▲') : ''));
  const tb = $('#tbl tbody'); tb.innerHTML = '';
  let g = 0, w = 0, u = 0;
  for (const x of list) { const r = x.r; if (x.hit != null && x.ask) { g++; w += x.hit; u += x.hit ? (1 / x.ask - 1) : -1; }
    const tr = document.createElement('tr'); tr.className = 'row';
    tr.innerHTML = `<td><span class="nm">${r.away} @ ${r.home}</span><br><span class="tm">${when(r.time)}</span></td><td>${x.kind}</td><td><span class="nm">${x.side}</span>${x.shift ? `<br><span class="tm" title="Pinnacle's line is ${x.pinLine}; Robinhood only lists half points, so this is the nearest strike and Pinnacle's fair price is nudged for the half point">Pinnacle ${x.pinLine}~</span>` : ''}</td>
      <td class="num">${cents(x.ask)}</td><td class="num">${pct(x.fair)}</td><td class="num ${x.edge == null ? '' : x.edge >= 2 ? 'pos' : x.edge <= -2 ? 'neg' : ''}">${x.edge == null ? '—' : (x.edge >= 0 ? '+' : '') + x.edge.toFixed(1)}</td>
      <td class="num" title="share of the crowd's taker dollars on this side (trade tape)"><span class="bar"><i style="width:${x.crowd == null ? 0 : x.crowd * 100}%"></i></span> ${pct(x.crowd)}</td><td class="num">${money(x.tape)}</td><td class="num">${money(x.vol)}</td>
      <td><span class="v ${x.v.replace(/[^A-Za-z]/g, '')}">${x.v}</span></td><td>${x.hit == null ? '<span class="res n">—</span>' : x.hit ? '<span class="res y">✓ covered</span>' : '<span class="res n">✗</span>'}${r.finalHome != null ? ' <span class="tm">' + r.finalAway + '-' + r.finalHome + '</span>' : ''}</td>`;
    tb.appendChild(tr); }
  const games = new Set(list.map(x => x.r.date + (x.r.gamePk || x.r.eventId))).size;
  $('#kpi').innerHTML = `<div>games<b>${games}</b></div><div>sides shown<b>${list.length}</b></div>` + (g ? `<div>graded<b>${g}</b></div><div>record<b>${w}-${g - w}</b></div><div>units, 1u each side<b class="${u >= 0 ? 'pos' : 'neg'}">${u >= 0 ? '+' : ''}${u.toFixed(2)}</b></div>` : '');
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => setTab(t.dataset.t)));
function setTab(t){ tab = t; document.querySelectorAll('.tab').forEach(x => x.classList.toggle('on', x.dataset.t === t)); document.querySelectorAll('nav a.sportl').forEach(x => x.classList.toggle('on', x.dataset.t === t)); history.replaceState(null, '', '#' + t); render(); }
document.querySelectorAll('nav a.sportl').forEach(a => a.addEventListener('click', ev => { ev.preventDefault(); setTab(a.dataset.t); }));
document.querySelectorAll('nav a.dayl').forEach(a => a.addEventListener('click', ev => { ev.preventDefault(); day = a.dataset.day; setTab('mlb'); }));
document.querySelectorAll('nav a.weekl').forEach(a => a.addEventListener('click', ev => { ev.preventDefault(); week = a.dataset.week; setTab('nfl'); }));
['#onlyplays', '#kind'].forEach(s => $(s).addEventListener('input', render));
document.querySelectorAll('#tbl thead th').forEach(th => { th.dataset.l = th.textContent; th.addEventListener('click', () => { const k = th.dataset.k; if (sortKey === k) sortDir = -sortDir; else { sortKey = k; sortDir = k === 'time' || k === 'side' || k === 'kind' ? 1 : -1; } render(); }); });
setTab(tab);
// ---- scorecard over every graded side ----
const G = Object.values(BOARDS).flat().flatMap(sides).filter(x => x.hit != null && x.ask);
const pay = x => x.hit ? (1 / x.ask - 1) : -1;
const strat = {
  'Every side, 1u each (should be about -vig)': G,
  'CROWD side (more taker $ on it)': G.filter(x => x.crowd != null && x.crowd > 0.5),
  'FADE the crowd (less taker $ on it)': G.filter(x => x.crowd != null && x.crowd < 0.5),
  'Heavy crowd: 70%+ of the $ on it': G.filter(x => x.crowd != null && x.crowd >= 0.7),
  'Fade heavy crowd: under 30% of the $ on it': G.filter(x => x.crowd != null && x.crowd < 0.3),
  'Robinhood cheaper than Pinnacle fair by 2+ (BET)': G.filter(x => x.edge != null && x.edge >= 2),
  'Robinhood dearer than Pinnacle fair by 2+': G.filter(x => x.edge != null && x.edge <= -2),
  'Favorite covers': G.filter(x => x.kind === 'spread' && x.side.includes(' -')),
  'Underdog covers': G.filter(x => x.kind === 'spread' && x.side.includes(' +')),
  'Over': G.filter(x => x.kind === 'total' && x.side.startsWith('Over')),
  'Under': G.filter(x => x.kind === 'total' && x.side.startsWith('Under')),
  'MLB only: crowd side': G.filter(x => x.r.sport === 'MLB' && x.crowd != null && x.crowd > 0.5),
  'NFL only: crowd side': G.filter(x => x.r.sport === 'NFL' && x.crowd != null && x.crowd > 0.5),
};
const SROWS = Object.entries(strat).map(([name, b]) => { const w = b.filter(x => x.hit).length, pnl = b.reduce((s, x) => s + pay(x), 0); return { name, bets: b.length, w, l: b.length - w, pct: b.length ? w / b.length : -1, pnl, roi: b.length ? pnl / b.length : -99 }; });
let sSort = null, sDir = -1;
function scoreRows(){ const rows = sSort ? [...SROWS].sort((a, b) => ((a[sSort] > b[sSort] ? 1 : a[sSort] < b[sSort] ? -1 : 0) * sDir)) : SROWS;
  return rows.map(x => `<tr><td class="nm">${x.name}</td><td class="num">${x.bets}</td><td class="num">${x.w}-${x.l}</td><td class="num">${x.bets ? (x.pct * 100).toFixed(0) + '%' : '—'}</td><td class="num ${x.pnl >= 0 ? 'pos' : 'neg'}">${x.pnl >= 0 ? '+' : ''}${x.pnl.toFixed(1)}u</td><td class="num ${x.pnl >= 0 ? 'pos' : 'neg'}">${x.bets ? (x.roi * 100).toFixed(0) + '%' : '—'}</td></tr>`).join(''); }
$('#score').innerHTML = `<div class="kpi"><div>graded sides<b>${G.length}</b></div><div>games<b>${new Set(G.map(x => x.r.date + (x.r.gamePk || x.r.eventId))).size}</b></div></div>
  <div class="wrap"><table id="stbl"><thead><tr><th data-s="name">Strategy (flat 1u at Robinhood)</th><th class="num" data-s="bets">Bets</th><th class="num" data-s="pct">Record</th><th class="num" data-s="pct">Win %</th><th class="num" data-s="pnl">Units</th><th class="num" data-s="roi">ROI</th></tr></thead><tbody>${scoreRows()}</tbody></table></div>
  <p class="note">Click a header to sort. Every side of every graded market is counted once, so "every side" is what a coin flip returns minus the spread. The crowd rows are the test: if the side with more money covers less than its price, the fade rows go green.</p>`;
$('#stbl thead').querySelectorAll('th').forEach(th => th.addEventListener('click', () => { const k = th.dataset.s; if (sSort === k) sDir = -sDir; else { sSort = k; sDir = k === 'name' ? 1 : -1; } $('#stbl tbody').innerHTML = scoreRows(); }));
"""

def page():
    return f"""{head()}
<div class="tabs"><div class="tab on" data-t="mlb">MLB {today or ''}</div><div class="tab" data-t="nfl">NFL {week.replace('_', ' ') if week else ''}</div></div>
<div class="panel">
<div class="kpi" id="kpi"></div>
<div class="ctl"><label><input type="checkbox" id="onlyplays"> hide PASS</label><label>show <select id="kind"><option value="all">spreads and totals</option><option value="spread">spreads only</option><option value="total">totals only</option></select></label></div>
<div class="wrap"><table id="tbl"><thead><tr><th data-k="time">Game</th><th data-k="kind">Market</th><th data-k="side">Side</th><th class="num" data-k="ask">Robinhood ask</th><th class="num" data-k="fair">Pinnacle fair</th><th class="num" data-k="edge">Edge</th><th class="num" data-k="crowd">Crowd $ on this side</th><th class="num" data-k="tape">Tape $</th><th class="num" data-k="vol">$ traded</th><th data-k="v">Verdict</th><th data-k="hit">Result</th></tr></thead><tbody></tbody></table></div>
<div class="legend"><b>No model here.</b> Each row is one side of a spread or total, so a 12-game slate is 48 rows (24 with spreads or totals only). Click any column header to sort; click again to flip. <b>Robinhood ask</b> = what a $1 contract on that side costs. <b>Pinnacle fair</b> = the sharpest book's de-vigged chance at the same line (a ~ means Pinnacle's line was a whole number, Robinhood only lists half points, so the nearest strike is shown and the fair price is nudged for the half point).
<b>Edge</b> = fair minus ask, in points; <b>BET</b> at 2+, <b>STRONG BET</b> at 5+: you are simply being paid more than the sharpest book says the side is worth. <b>Crowd $ on this side</b> = share of the taker dollars on this exact market from the trade tape (each trade credited to the side the bettor backed); <b>Tape $</b> = both sides together; <b>$ traded</b> = the whole ladder of lines for this game.
Rows lock at first pitch / kickoff (volumes only ever go up before that) and grade from the final score. The scorecard at the bottom is the point: does the side with more of the crowd's money cover less than its price says?</div>
<h2 style="margin-top:18px">Scorecard</h2><div id="score"></div>
</div>
<script>const BOARDS = {jd(boards)}; const TODAY = {jd(today)}; const WEEK = {jd(week)};{JS}</script>"""

open(os.path.join(SITE, 'lines.html'), 'w', encoding='utf-8', newline='\n').write(page())
print(f"lines.html: {len(mlb_days)} MLB days, {len(nfl_weeks)} NFL weeks, {sum(len(v) for v in boards.values())} games")
