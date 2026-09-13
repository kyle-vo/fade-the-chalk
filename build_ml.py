"""Render docs/ml.html: moneyline board (MLB today + NFL week) with model vs Kalshi/Robinhood vs Fliff vs Pinnacle, public money split, results, and a scorecard."""
import json, os, re, glob, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs')
J = lambda p: json.load(open(p, encoding='utf-8'))
jd = lambda o: json.dumps(o).replace('</', '<' + chr(92) + '/')
src = open(os.path.join(HERE, 'build_site.py'), encoding='utf-8').read()
CSS = re.search(r'CSS = r"""(.*?)"""', src, re.S).group(1); FONTS = re.search(r"FONTS = '(.*?)'", src).group(1)
def implied(o): return (-o) / (-o + 100) if o < 0 else 100 / (o + 100)

# ---- assemble every locked moneyline day/week with results ----
boards = {}
for lockf in sorted(glob.glob(os.path.join(BT, 'ml_*.json'))):
    tag = os.path.basename(lockf)[3:-5]; rows = J(lockf); rp = os.path.join(BT, f'mlres_{tag}.json'); res = J(rp) if os.path.exists(rp) else {}
    for r in rows:
        k = str(r.get('gamePk') or r.get('eventId')); g = res.get(k)
        r['homeWin'] = g['homeWin'] if g else None; r['score'] = g['score'] if g else None
        # pick side = larger model edge vs Fliff (needs a Fliff price); fall back to model favorite
        eh = r['model'] - implied(r['fliffHome']) if r.get('fliffHome') else None; ea = (1 - r['model']) - implied(r['fliffAway']) if r.get('fliffAway') else None
        if eh is None and ea is None: r['pick'] = 'home' if r['model'] >= .5 else 'away'; r['edge'] = None
        else: r['pick'] = 'home' if (eh or -9) >= (ea or -9) else 'away'; r['edge'] = round(max(eh or -9, ea or -9) * 100, 1)
        r['pickOdds'] = r.get('fliffHome') if r['pick'] == 'home' else r.get('fliffAway')
        r['pickProb'] = r['model'] if r['pick'] == 'home' else 1 - r['model']
        r['pickHit'] = None if r['homeWin'] is None else (1 if (r['homeWin'] == 1) == (r['pick'] == 'home') else 0)
    boards[tag] = rows
mlb_days = sorted([t for t in boards if not t.endswith(('wk1', 'wk2', 'wk3', 'wk4', 'wk5', 'wk6', 'wk7', 'wk8', 'wk9')) and '_wk' not in t], reverse=True)
nfl_weeks = sorted([t for t in boards if '_wk' in t], reverse=True)
today = mlb_days[0] if mlb_days else None; week = nfl_weeks[0] if nfl_weeks else None
graded = [r for rows in boards.values() for r in rows if r['homeWin'] is not None]

def head(title, sub):
    nav = '<nav><a href="index.html">Today</a><a href="ml.html" class="on">Moneyline</a><a href="track.html">Track</a><span class="lbl">ML days</span>' + ''.join(f'<a href="#" data-day="{d}" class="dayl">{d[5:]}</a>' for d in mlb_days[:14]) + '</nav>'
    return f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>{FONTS}<style>{CSS}</style><header><h1><a href="index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">{sub}</div></header>{nav}'

JS = r"""
const $ = s => document.querySelector(s); let tab = 'mlb'; let day = TODAY; let sortKey = 'edge', sortDir = -1;
let store = {}; try { store = JSON.parse(localStorage.getItem('ftc_ml_bets') || '{}'); } catch (e) {}
function save(){ try { localStorage.setItem('ftc_ml_bets', JSON.stringify(store)); } catch (e) {} }
const implied = o => { o = +o; if (!o || isNaN(o)) return null; return o < 0 ? (-o) / (-o + 100) : 100 / (o + 100); };
const fmt = o => o == null ? '—' : o > 0 ? '+' + o : '' + o; const pct = p => p == null ? '—' : Math.round(p * 100) + '%';
const key = r => r.date + '|' + (r.gamePk || r.eventId);
function verdict(r){
  const pub = r.pubHome == null ? null : (r.pick === 'home' ? r.pubHome : 1 - r.pubHome);   // share of Kalshi money on the pick side
  const kal = r.kalshi == null ? null : (r.pick === 'home' ? r.kalshi : r.kalshiAway ?? 1 - r.kalshi);
  let v = 'PASS';
  if (r.edge != null && r.edge >= 3 && (pub == null || pub < .6)) v = 'SLEEPER';
  else if (r.edge != null && r.edge >= 3) v = 'VALUE';
  else if (pub != null && pub >= .65 && r.edge != null && r.edge < 0) v = 'FADE';
  else if (r.edge != null && r.edge < -3) v = 'TRAP';
  return { pub, kal, v };
}
function render(){
  const rows = (tab === 'mlb' ? (BOARDS[day] || []) : (BOARDS[WEEK] || [])).map(r => ({ r, ...verdict(r) }));
  const only = $('#onlyplays').checked, hide = $('#hidedone').checked;
  let list = rows.filter(x => (!only || ['SLEEPER', 'VALUE', 'FADE'].includes(x.v)) && (!hide || x.r.homeWin == null || tab === 'mlb'));
  const get = x => ({ edge: x.r.edge ?? -99, model: x.r.pickProb, kvol: x.r.kvol || 0, pub: x.pub ?? -1, time: x.r.time, skew: x.r.skewHome ?? -99, v: x.v })[sortKey];
  list.sort((a, b) => { const A = get(a), B = get(b); return (A > B ? 1 : A < B ? -1 : 0) * sortDir; });
  const cols = [['Game', 'time'], ['Pick', 'model'], ['Model', 'model'], ['Fliff', 'edge'], ['Edge', 'edge'], ['Kalshi / Robinhood', 'kvol'], ['Public $ on pick', 'pub'], ['Pinnacle', 'skew'], ['Skew', 'skew'], ['Verdict', 'v'], ['Bet', 'v'], ['Result', 'v']];
  $('#tbl thead').innerHTML = '<tr>' + cols.map(([l, k]) => `<th data-k="${k}" class="${k === sortKey ? 'on' : ''}">${l}</th>`).join('') + '</tr>';
  const tb = $('#tbl tbody'); tb.innerHTML = ''; let n = { s: 0, f: 0, g: 0, hit: 0, exp: 0 };
  for (const x of list) { const r = x.r, e = store[key(r)] || {};
    if (x.v === 'SLEEPER' || x.v === 'VALUE') n.s++; if (x.v === 'FADE') n.f++; if (r.pickHit != null) { n.g++; n.hit += r.pickHit; n.exp += r.pickProb; }
    const when = new Date(r.time).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
    const pickTeam = r.pick === 'home' ? r.home : r.away, other = r.pick === 'home' ? r.away : r.home;
    const sharp = r.sharpHome == null ? null : (r.pick === 'home' ? r.sharpHome : 1 - r.sharpHome);
    const skew = r.skewHome == null ? null : (r.pick === 'home' ? r.skewHome : -r.skewHome);
    const tr = document.createElement('tr'); tr.className = 'row';
    tr.innerHTML = `<td><span class="nm">${r.away} @ ${r.home}</span><br><span class="tm">${when}${r.homeSP ? ' · ' + r.awaySP + ' / ' + r.homeSP : ''}${r.homeRec ? ' · ' + r.awayRec + ' / ' + r.homeRec : ''}</span></td>
      <td><span class="nm">${pickTeam}</span> <span class="tm">over ${other}</span></td>
      <td class="num">${pct(r.pickProb)}</td>
      <td class="num">${fmt(r.pickOdds)}${r.pickOdds == null ? '' : ' <span class="tm">(' + pct(implied(r.pickOdds)) + ')</span>'}</td>
      <td class="num ${r.edge == null ? '' : r.edge >= 0 ? 'pos' : 'neg'}">${r.edge == null ? '—' : (r.edge >= 0 ? '+' : '') + r.edge.toFixed(1)}</td>
      <td><span class="crowd">${pct(x.kal)} <b>$${r.kvol >= 1000 ? Math.round(r.kvol / 1000) + 'k' : r.kvol}</b></span></td>
      <td><span class="bar" style="width:70px"><i style="width:${x.pub == null ? 0 : x.pub * 100}%"></i></span> <span class="tm">${pct(x.pub)}</span></td>
      <td class="num">${pct(sharp)}</td>
      <td class="num ${skew == null ? '' : skew > 0 ? 'neg' : 'pos'}">${skew == null ? '—' : (skew > 0 ? '+' : '') + skew.toFixed(1)}</td>
      <td><span class="v ${x.v}">${x.v}</span></td>
      <td><input type="checkbox" class="bet" data-k="${key(r)}" ${e.on ? 'checked' : ''}> <input class="stk" data-k="${key(r)}" data-f="stake" value="${e.stake || ''}" placeholder="1u"></td>
      <td>${r.pickHit == null ? '<span class="res n">—</span>' : r.pickHit ? '<span class="res y">✓ ' + pickTeam + '</span>' : '<span class="res n">✗ ' + other + '</span>'}${r.score ? ' <span class="tm">' + r.score + '</span>' : ''}</td>`;
    const det = document.createElement('tr'); det.className = 'det'; det.hidden = true;
    const bk = r.books ? Object.entries(r.books).map(([k, v]) => `<span class="f">${k} ${fmt(v.away)}/${fmt(v.home)}</span>`).join('') : '';
    det.innerHTML = `<td colspan="12">${(r.notes || []).filter(Boolean).join(' &nbsp;|&nbsp; ')}<br>Kalshi: ${r.home} ${pct(r.kalshi)} ($${(r.kvolHome || 0).toLocaleString()}) · ${r.away} ${pct(r.kalshiAway)} ($${(r.kvolAway || 0).toLocaleString()})<br>${bk}</td>`;
    tr.addEventListener('click', ev => { if (ev.target.tagName !== 'INPUT') det.hidden = !det.hidden; });
    tb.appendChild(tr); tb.appendChild(det); }
  $('#kpi').innerHTML = `<div>games<b>${list.length}</b></div><div>plays<b>${n.s}</b></div><div>fades<b>${n.f}</b></div>` + (n.g ? `<div>graded<b>${n.g}</b></div><div>model picks<b>${n.hit}-${n.g - n.hit}</b></div><div>expected<b>${n.exp.toFixed(1)}</b></div>` : '');
  tb.querySelectorAll('input').forEach(i => i.addEventListener('change', () => { const k = i.dataset.k; store[k] = store[k] || {}; if (i.type === 'checkbox') store[k].on = i.checked; else store[k][i.dataset.f] = i.value.trim(); save(); render(); }));
  $('#tbl thead').querySelectorAll('th').forEach(th => th.addEventListener('click', () => { const k = th.dataset.k; if (sortKey === k) sortDir = -sortDir; else { sortKey = k; sortDir = -1; } render(); }));
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => { document.querySelectorAll('.tab').forEach(x => x.classList.remove('on')); t.classList.add('on'); tab = t.dataset.t; render(); }));
document.querySelectorAll('nav a.dayl').forEach(a => a.addEventListener('click', ev => { ev.preventDefault(); day = a.dataset.day; tab = 'mlb'; document.querySelectorAll('nav a.dayl').forEach(x => x.classList.remove('on')); a.classList.add('on'); render(); }));
['#onlyplays', '#hidedone'].forEach(s => $(s).addEventListener('input', render));
// ---- scorecard over every graded game ----
const G = GRADED; const brier = (ps) => ps.length ? ps.reduce((s, [p, y]) => s + (p - y) ** 2, 0) / ps.length : null;
const bm = brier(G.map(r => [r.model, r.homeWin])), bk = brier(G.filter(r => r.kalshi != null).map(r => [r.kalshi, r.homeWin])), bs = brier(G.filter(r => r.sharpHome != null).map(r => [r.sharpHome, r.homeWin]));
const pay = (o, y) => y ? (o > 0 ? o / 100 : 100 / -o) : -1;
const strat = {
  'Model pick, edge ≥ 3 at Fliff': G.filter(r => r.edge != null && r.edge >= 3),
  'Model pick, every game with a Fliff price': G.filter(r => r.pickOdds != null),
  'Fade the public (65%+ of Kalshi $ on the other side)': G.filter(r => r.pubHome != null && r.pickOdds != null && ((r.pick === 'home' ? 1 - r.pubHome : r.pubHome) >= .65)),
  'Ride the public (65%+ of Kalshi $ on the pick)': G.filter(r => r.pubHome != null && r.pickOdds != null && ((r.pick === 'home' ? r.pubHome : 1 - r.pubHome) >= .65)),
};
let sh = '';
for (const [name, b] of Object.entries(strat)) { const w = b.filter(r => r.pickHit).length, pnl = b.reduce((s, r) => s + pay(r.pickOdds, r.pickHit), 0); sh += `<tr><td class="nm">${name}</td><td class="num">${b.length}</td><td class="num">${w}-${b.length - w}</td><td class="num ${pnl >= 0 ? 'pos' : 'neg'}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(1)}u</td></tr>`; }
$('#score').innerHTML = `<div class="kpi"><div>graded games<b>${G.length}</b></div><div>model Brier<b>${bm == null ? '—' : bm.toFixed(4)}</b></div><div>Kalshi Brier<b>${bk == null ? '—' : bk.toFixed(4)}</b></div><div>Pinnacle Brier<b>${bs == null ? '—' : bs.toFixed(4)}</b></div></div>
  <div class="wrap"><table><thead><tr><th>Strategy (flat 1u at Fliff)</th><th>Bets</th><th>Record</th><th>Units</th></tr></thead><tbody>${sh}</tbody></table></div>
  <p class="note">Brier: lower is better, 0.25 is a coin flip. Who's closest to the truth, the model, the Kalshi crowd, or the sharpest book? Public $ = share of Kalshi/Robinhood dollars on that side before kickoff.</p>`;
render();
"""

def page():
    sub = f"moneyline · model win% vs Kalshi/Robinhood vs Fliff vs Pinnacle · public money split · built {datetime.datetime.now().isoformat(timespec='minutes')}"
    return f"""{head('Fade The Chalk', sub)}
<div class="tabs"><div class="tab on" data-t="mlb">MLB {today or ''}</div><div class="tab" data-t="nfl">NFL {week.replace('_', ' ') if week else ''}</div></div>
<div class="panel">
<div class="kpi" id="kpi"></div>
<div class="ctl"><label><input type="checkbox" id="onlyplays"> only SLEEPER / VALUE / FADE</label><label><input type="checkbox" id="hidedone"> hide finished</label><span class="tm">click a column to sort · click a row for the reasoning and every book's price</span></div>
<div class="wrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
<div class="legend"><b>Pick</b> = the side the model likes against Fliff's price. <b>Model</b> = win chance for that side. <b>Edge</b> = model minus Fliff's implied chance, in points; Fliff's cut on a moneyline is ~2-3 points.
<b>Kalshi / Robinhood</b> = the prediction-market price for that side and total dollars traded on the game (Robinhood's contracts are Kalshi's). <b>Public $ on pick</b> = share of that money on the pick side: over 65% is a crowded side.
<b>Pinnacle</b> = the sharpest book's de-vigged chance. <b>Skew</b> = retail books vs Pinnacle for the pick side: positive = retail shading toward it = public money.<br>
<b>SLEEPER</b> = edge ≥ 3 and under 60% of the money on it. <b>VALUE</b> = edge ≥ 3, crowded. <b>FADE</b> = 65%+ of the money on the other side and the model disagrees. <b>TRAP</b> = model says the price is 3+ points too short.
MLB model: regressed run-differential strength, starting-pitcher runs-allowed adjustment, home field. NFL model: last season's point differential (regressed) plus 2 points for home; weak until 2026 games exist, so lean on Pinnacle vs Kalshi there.</div>
<h2>Scorecard <small>every locked, finished game</small></h2><div id="score"></div>
</div>
<script>const BOARDS = {jd(boards)}; const TODAY = {jd(today)}; const WEEK = {jd(week)}; const GRADED = {jd([{k: r.get(k) for k in ('model', 'kalshi', 'sharpHome', 'homeWin', 'edge', 'pickOdds', 'pickHit', 'pick', 'pubHome')} for r in graded])};{JS}</script>"""

open(os.path.join(SITE, 'ml.html'), 'w', encoding='utf-8', newline='\n').write(page())
print(f"ml.html: {len(mlb_days)} MLB days, {len(nfl_weeks)} NFL weeks, {len(graded)} graded games")
