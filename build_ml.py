"""Render docs/ml.html: moneyline board (MLB today + NFL week) with model vs Kalshi/Robinhood vs Fliff vs Pinnacle, public money split, results, and a scorecard."""
import json, os, re, glob, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); BT = os.path.join(HERE, 'backtest'); SITE = os.path.join(HERE, 'docs')
J = lambda p: json.load(open(p, encoding='utf-8'))
jd = lambda o: json.dumps(o).replace('</', '<' + chr(92) + '/')
src = open(os.path.join(HERE, 'build_site.py'), encoding='utf-8').read()
CSS = re.search(r'CSS = r"""(.*?)"""', src, re.S).group(1); FONTS = re.search(r"FONTS = '(.*?)'", src).group(1)
def implied(o): return (-o) / (-o + 100) if o < 0 else 100 / (o + 100)
def american(p): p = min(max(p, .01), .99); return round(-100 * p / (1 - p)) if p >= .5 else round(100 * (1 - p) / p)

# ---- assemble every locked moneyline day/week with results ----
boards = {}
for lockf in sorted(glob.glob(os.path.join(BT, 'ml_*.json'))):
    tag = os.path.basename(lockf)[3:-5]; rows = J(lockf); rp = os.path.join(BT, f'mlres_{tag}.json'); res = J(rp) if os.path.exists(rp) else {}
    for r in rows:
        k = str(r.get('gamePk') or r.get('eventId')); g = res.get(k)
        r['homeWin'] = g['homeWin'] if g else None; r['score'] = g['score'] if g else None
        # pick side = larger model edge vs Fliff (needs a Fliff price); fall back to model favorite
        # Robinhood = Kalshi. Price you pay = the ask; a contract pays $1. ask 0.40 -> +150.
        ah = r.get('kalshiAsk') or (r['kalshi'] + 0.01 if r.get('kalshi') is not None else None); aa = r.get('kalshiAwayAsk') or (r['kalshiAway'] + 0.01 if r.get('kalshiAway') is not None else None)
        r['rhHome'] = american(ah) if ah and 0 < ah < 1 else None; r['rhAway'] = american(aa) if aa and 0 < aa < 1 else None
        # pick = the model's favorite, always (weekend 1: the model's >50% side was the only 'favorite' that made money).
        # earlier versions picked whichever side had the bigger edge vs the ask, which with a Pinnacle-anchored model degenerates into 'always the cheap underdog'.
        r['pick'] = 'home' if r['model'] >= .5 else 'away'
        ask = ah if r['pick'] == 'home' else aa
        r['edge'] = round(((r['model'] if r['pick'] == 'home' else 1 - r['model']) - ask) * 100, 1) if ask else None
        r['pickOdds'] = r.get('rhHome') if r['pick'] == 'home' else r.get('rhAway'); r['oppOdds'] = r.get('rhAway') if r['pick'] == 'home' else r.get('rhHome')
        r['pickFliff'] = r.get('fliffHome') if r['pick'] == 'home' else r.get('fliffAway')
        r['pickProb'] = r['model'] if r['pick'] == 'home' else 1 - r['model']
        r['pickHit'] = None if r['homeWin'] is None else (1 if (r['homeWin'] == 1) == (r['pick'] == 'home') else 0)
        # book take = the losing side's share of the Kalshi/Robinhood money on the game (what the winners collected from the losers)
        if r['homeWin'] is not None and r.get('pubHome') is not None and r.get('kvol'):
            loser_share = (1 - r['pubHome']) if r['homeWin'] == 1 else r['pubHome']
            r['bookTake'] = round(loser_share * r['kvol']); r['loserShare'] = round(loser_share, 3); r['bookGave'] = round((1 - loser_share) * r['kvol'])
        # units if you took the model pick flat 1u at Robinhood's price
        if r['pickHit'] is not None and r.get('pickOdds') is not None:
            o = r['pickOdds']; r['units'] = round((o / 100 if o > 0 else 100 / -o) if r['pickHit'] else -1.0, 3)
    boards[tag] = rows
mlb_days = sorted([t for t in boards if not t.endswith(('wk1', 'wk2', 'wk3', 'wk4', 'wk5', 'wk6', 'wk7', 'wk8', 'wk9')) and '_wk' not in t], reverse=True)
nfl_weeks = sorted([t for t in boards if '_wk' in t], reverse=True)
today = mlb_days[0] if mlb_days else None; week = nfl_weeks[0] if nfl_weeks else None
graded = [r for rows in boards.values() for r in rows if r['homeWin'] is not None]
# slim copy for track.html (build_site.py embeds it so moneyline paper bets can be scored there)
ML_KEEP = ('sport', 'date', 'gamePk', 'eventId', 'home', 'away', 'time', 'homeSP', 'awaySP', 'pick', 'pickOdds', 'pickProb', 'pickHit', 'score', 'kalshiAsk', 'kalshiAwayAsk', 'pubHome', 'takerPubHome')
json.dump([{k: r.get(k) for k in ML_KEEP} for rows in boards.values() for r in rows], open(os.path.join(BT, 'ml_board.json'), 'w', encoding='utf-8'))

def head(title, sub):
    nav = '<nav><a href="index.html">Today</a><a href="ml.html" class="on">Moneyline</a><a href="track.html">Track</a><a href="archive.html">Archive</a><span class="lbl">MLB days</span>' + ''.join(f'<a href="#" data-day="{d}" class="dayl">{d[5:]}</a>' for d in mlb_days[:7]) + '<span class="lbl">NFL weeks</span>' + ''.join(f'<a href="#" data-week="{w}" class="weekl">wk {w.split("wk")[1]}</a>' for w in nfl_weeks[:8]) + '</nav>'
    return f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>{FONTS}{CSS}<header><h1><a href="index.html">FADE THE <span>CHALK</span></a></h1><div class="sub">{sub}</div></header>{nav}'

JS = r"""
const $ = s => document.querySelector(s); let tab = 'mlb'; let day = TODAY; let week = WEEK; let sortKey = 'edge', sortDir = -1;
let store = {}; try { store = JSON.parse(localStorage.getItem('ftc_ml_bets') || '{}'); } catch (e) {}
function save(){ try { localStorage.setItem('ftc_ml_bets', JSON.stringify(store)); } catch (e) {} }
const implied = o => { o = +o; if (!o || isNaN(o)) return null; return o < 0 ? (-o) / (-o + 100) : 100 / (o + 100); };
const fmt = o => o == null ? '—' : o > 0 ? '+' + o : '' + o; const pct = p => p == null ? '—' : Math.round(p * 100) + '%';
const key = r => r.date + '|' + (r.gamePk || r.eventId);
// Weekend 1 backtest (28 graded moneylines): model-favorite picks went 9-5 (+1.3u), model-underdog picks 4-10 (-1.3u).
// The public backing a favorite was right 65% of the time; the public backing an underdog was right only 25%.
// So: bet the pick only when it IS the favorite, skip every underdog pick, and the strongest bets are favorites the public hasn't piled onto yet.
function verdict(r){
  const pub = r.pubHome == null ? null : (r.pick === 'home' ? r.pubHome : 1 - r.pubHome);   // share of Kalshi money on the pick side
  const kal = r.kalshi == null ? null : (r.pick === 'home' ? r.kalshi : r.kalshiAway ?? 1 - r.kalshi);
  const isFav = true;                                               // the pick is always the model's favorite now
  let v = 'PASS';
  if (r.pickOdds != null) {
    if (r.edge != null && r.edge < -3) v = 'PASS (priced in)';      // Robinhood already charges more than the model's number: no value
    else if (pub != null && pub < 0.5) v = 'STRONG BET';            // model's favorite, and the public's money is on the other team
    else v = 'BET';                                                 // model's favorite, public already on it
  }
  const tpub = r.takerPubHome == null ? null : (r.pick === 'home' ? r.takerPubHome : 1 - r.takerPubHome);   // directional: taker dollars on the pick side, pre-game trade tape
  return { pub, kal, v, isFav, tpub };
}
function render(){
  const rows = (tab === 'mlb' ? (BOARDS[day] || []) : (BOARDS[week] || [])).map(r => ({ r, ...verdict(r) }));
  document.querySelector('.tab[data-t=mlb]').textContent = 'MLB ' + day; document.querySelector('.tab[data-t=nfl]').textContent = 'NFL ' + (week || '').replace('_', ' ');
  const only = $('#onlyplays').checked, hide = $('#hidedone').checked;
  let list = rows.filter(x => (!only || x.v === 'BET' || x.v === 'STRONG BET') && (!hide || x.r.homeWin == null || tab === 'mlb'));
  const get = x => ({ edge: x.r.edge ?? -99, model: x.r.pickProb, kvol: x.r.kvol || 0, pub: x.pub ?? -1, time: x.r.time, sharp: x.r.sharpHome ?? -99, v: x.v, take: x.r.bookTake ?? -1, gave: x.r.bookGave ?? -1, tpub: x.tpub ?? -1, tvol: (x.r['takerHome$'] || 0) + (x.r['takerAway$'] || 0) })[sortKey];
  list.sort((a, b) => { const A = get(a), B = get(b); return (A > B ? 1 : A < B ? -1 : 0) * sortDir; });
  const cols = [['Game', 'time'], ['Pick', 'model'], ['Model', 'model'], ['Robinhood', 'edge'], ['Edge', 'edge'], ['Public $ on pick', 'pub'], ['$ traded', 'kvol'], ['Tape $ on pick', 'tpub'], ['Tape $', 'tvol'], ['Pinnacle', 'sharp'], ['Verdict', 'v'], ['Bet', 'v'], ['Result', 'v'], ['Book take', 'take'], ['Book gave', 'gave']];
  const R = new Set(['Model', 'Robinhood', 'Edge', 'Public $ on pick', '$ traded', 'Tape $ on pick', 'Tape $', 'Pinnacle', 'Book take', 'Book gave']);
  $('#tbl thead').innerHTML = '<tr>' + cols.map(([l, k]) => `<th data-k="${k}" class="${k === sortKey ? 'on' : ''} ${R.has(l) ? 'r' : ''}">${l}</th>`).join('') + '</tr>';
  const tb = $('#tbl tbody'); tb.innerHTML = ''; let n = { s: 0, f: 0, g: 0, hit: 0, exp: 0, units: 0, staked: 0, take: 0, gave: 0 };
  for (const x of list) { const r = x.r, e = store[key(r)] || {};
    if (x.v === 'BET' || x.v === 'STRONG BET') n.s++; if (x.v.startsWith('PASS')) n.f++; if (r.pickHit != null) { n.g++; n.hit += r.pickHit; n.exp += r.pickProb; if (r.units != null) { n.units += r.units; n.staked++; } if (r.bookTake) n.take += r.bookTake; if (r.bookGave) n.gave += r.bookGave; }
    const when = new Date(r.time).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
    const pickTeam = r.pick === 'home' ? r.home : r.away, other = r.pick === 'home' ? r.away : r.home;
    const sharp = r.sharpHome == null ? null : (r.pick === 'home' ? r.sharpHome : 1 - r.sharpHome);
    const skew = r.skewHome == null ? null : (r.pick === 'home' ? r.skewHome : -r.skewHome);
    const tr = document.createElement('tr'); tr.className = 'row';
    tr.innerHTML = `<td><span class="nm">${r.away} @ ${r.home}</span><br><span class="tm">${when}${r.homeSP ? ' · ' + r.awaySP + ' / ' + r.homeSP : ''}${r.homeRec ? ' · ' + r.awayRec + ' / ' + r.homeRec : ''}</span></td>
      <td><span class="nm">${pickTeam}</span></td>
      <td class="num">${pct(r.pickProb)}</td>
      <td class="num">${r.pickOdds == null ? '—' : Math.round(implied(r.pickOdds) * 100) + '¢'} <span class="tm">${fmt(r.pickOdds)}</span></td>
      <td class="num ${r.edge == null ? '' : r.edge >= 0 ? 'pos' : 'neg'}">${r.edge == null ? '—' : (r.edge >= 0 ? '+' : '') + r.edge.toFixed(1)}</td>
      <td class="num"><span class="bar"><i style="width:${x.pub == null ? 0 : x.pub * 100}%"></i></span> ${pct(x.pub)}</td>
      <td class="num">$${r.kvol >= 1000 ? Math.round(r.kvol / 1000) + 'k' : r.kvol}</td>
      <td class="num" title="${x.tpub == null ? 'no trade tape yet' : 'pre-game trade tape: $' + Math.round((r.pick === 'home' ? r['takerHome$'] : r['takerAway$'])).toLocaleString() + ' of taker money on ' + pickTeam + ' vs $' + Math.round((r.pick === 'home' ? r['takerAway$'] : r['takerHome$'])).toLocaleString() + ' on ' + other + ' (' + (r.takerTrades || 0).toLocaleString() + ' trades)'}"><span class="bar"><i style="width:${x.tpub == null ? 0 : x.tpub * 100}%"></i></span> ${pct(x.tpub)}</td>
      <td class="num">${r['takerHome$'] == null ? '—' : '$' + (() => { const t = r['takerHome$'] + r['takerAway$']; return t >= 1e6 ? (t / 1e6).toFixed(1) + 'M' : t >= 1000 ? Math.round(t / 1000) + 'k' : t; })()}</td>
      <td class="num" title="${r.sharpSrc === 'sharp avg' ? 'Pinnacle not posted yet: average of Bovada/BetOnline' : 'Pinnacle de-vigged'}">${pct(sharp)}${r.sharpSrc === 'sharp avg' ? '~' : ''}</td>
      <td><span class="v ${x.v.replace(/[^A-Za-z]/g, '')}">${x.v}</span></td>
      <td><input type="checkbox" class="bet" data-k="${key(r)}" ${e.on ? 'checked' : ''}> <input class="stk" data-k="${key(r)}" data-f="stake" value="${e.stake || ''}" placeholder="1u"></td>
      <td>${r.pickHit == null ? '<span class="res n">—</span>' : r.pickHit ? '<span class="res y">✓ ' + pickTeam + '</span>' : '<span class="res n">✗ ' + other + '</span>'}${r.score ? ' <span class="tm">' + r.score + '</span>' : ''}</td>
      <td class="num" title="${r.bookTake != null ? 'losing side held ' + Math.round(r.loserShare * 100) + '% of $' + r.kvol.toLocaleString() : 'fills in when the game is final'}">${r.bookTake != null ? '$' + (r.bookTake >= 1000 ? Math.round(r.bookTake / 1000) + 'k' : r.bookTake) : '—'}</td>
      <td class="num" title="${r.bookGave != null ? 'winning side held ' + Math.round((1 - r.loserShare) * 100) + '% of $' + r.kvol.toLocaleString() : 'fills in when the game is final'}">${r.bookGave != null ? '$' + (r.bookGave >= 1000 ? Math.round(r.bookGave / 1000) + 'k' : r.bookGave) : '—'}</td>`;
    const det = document.createElement('tr'); det.className = 'det'; det.hidden = true;
    const bk = r.books ? Object.entries(r.books).map(([k, v]) => `<span class="f">${k} ${fmt(v.away)}/${fmt(v.home)}</span>`).join('') : '';
    det.innerHTML = `<td colspan="15">${(r.notes || []).filter(Boolean).join(' &nbsp;|&nbsp; ')}<br>Kalshi: ${r.home} ${pct(r.kalshi)} ($${(r.kvolHome || 0).toLocaleString()}) · ${r.away} ${pct(r.kalshiAway)} ($${(r.kvolAway || 0).toLocaleString()})<br>${bk}</td>`;
    tr.addEventListener('click', ev => { if (ev.target.tagName !== 'INPUT') det.hidden = !det.hidden; });
    tb.appendChild(tr); tb.appendChild(det); }
  $('#kpi').innerHTML = `<div>games<b>${list.length}</b></div>` + (n.g ? `<div>graded<b>${n.g}</b></div><div>model picks<b>${n.hit}-${n.g - n.hit}</b></div><div>expected<b>${n.exp.toFixed(1)}</b></div><div>units, 1u each pick<b class="${n.units >= 0 ? 'pos' : 'neg'}">${n.units >= 0 ? '+' : ''}${n.units.toFixed(2)}</b></div><div>ROI<b class="${n.units >= 0 ? 'pos' : 'neg'}">${n.staked ? (n.units / n.staked * 100).toFixed(1) : '0.0'}%</b></div><div>book take<b class="neg">$${n.take >= 1000 ? Math.round(n.take / 1000) + 'k' : n.take}</b></div><div>book gave<b class="pos">$${n.gave >= 1000 ? Math.round(n.gave / 1000) + 'k' : n.gave}</b></div>` : '');
  tb.querySelectorAll('input').forEach(i => i.addEventListener('change', () => { const k = i.dataset.k; store[k] = store[k] || {}; if (i.type === 'checkbox') store[k].on = i.checked; else store[k][i.dataset.f] = i.value.trim(); save(); render(); }));
  $('#tbl thead').querySelectorAll('th').forEach(th => th.addEventListener('click', () => { const k = th.dataset.k; if (sortKey === k) sortDir = -sortDir; else { sortKey = k; sortDir = -1; } render(); }));
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => { document.querySelectorAll('.tab').forEach(x => x.classList.remove('on')); t.classList.add('on'); tab = t.dataset.t; render(); }));
document.querySelectorAll('nav a.dayl').forEach(a => a.addEventListener('click', ev => { ev.preventDefault(); day = a.dataset.day; tab = 'mlb'; document.querySelectorAll('nav a.dayl').forEach(x => x.classList.remove('on')); a.classList.add('on'); render(); }));
document.querySelectorAll('nav a.weekl').forEach(a => a.addEventListener('click', ev => { ev.preventDefault(); week = a.dataset.week; tab = 'nfl'; document.querySelectorAll('.tab').forEach(x => x.classList.remove('on')); document.querySelector('.tab[data-t=nfl]').classList.add('on'); document.querySelectorAll('nav a.weekl').forEach(x => x.classList.remove('on')); a.classList.add('on'); render(); }));
['#onlyplays', '#hidedone'].forEach(s => $(s).addEventListener('input', render));
// ---- scorecard over every graded game ----
const G = GRADED; const brier = (ps) => ps.length ? ps.reduce((s, [p, y]) => s + (p - y) ** 2, 0) / ps.length : null;
const bm = brier(G.map(r => [r.model, r.homeWin])), bk = brier(G.filter(r => r.kalshi != null).map(r => [r.kalshi, r.homeWin])), bs = brier(G.filter(r => r.sharpHome != null).map(r => [r.sharpHome, r.homeWin]));
const tapeOnPick = r => r.pick === 'home' ? r.takerPubHome : 1 - r.takerPubHome;
const pay = (o, y) => y ? (o > 0 ? o / 100 : 100 / -o) : -1;
const isModelFav = r => r.pickProb >= 0.5, isMarketFav = r => r.pickOdds != null && r.pickOdds < 0, pubOnPick = r => r.pubHome == null ? null : (r.pick === 'home' ? r.pubHome : 1 - r.pubHome);
const strat = {
  'Model favorite, every game': G.filter(r => r.pickOdds != null),
  'STRONG BET only (model fav, public on other side)': G.filter(r => r.pickOdds != null && isModelFav(r) && pubOnPick(r) != null && pubOnPick(r) < 0.5),
  'BET + STRONG BET only (skip PASS: favorite priced in)': G.filter(r => r.pickOdds != null && !(r.edge != null && r.edge < -3)),
  'TAPE VERDICT: STRONG (not priced in, taker $ on the other team)': G.filter(r => r.pickOdds != null && r.takerPubHome != null && !(r.edge != null && r.edge < -3) && tapeOnPick(r) < 0.5),
  'TAPE VERDICT: BET (not priced in, taker $ agrees)': G.filter(r => r.pickOdds != null && r.takerPubHome != null && !(r.edge != null && r.edge < -3) && tapeOnPick(r) >= 0.5),
  'CURRENT VERDICT: STRONG (Public $ on the other team)': G.filter(r => r.pickOdds != null && r.pubHome != null && !(r.edge != null && r.edge < -3) && pubOnPick(r) < 0.5),
  'CURRENT VERDICT: BET (Public $ agrees)': G.filter(r => r.pickOdds != null && !(r.edge != null && r.edge < -3) && !(r.pubHome != null && pubOnPick(r) < 0.5)),
  'TAPE: model pick when taker $ is on the other team': G.filter(r => r.pickOdds != null && r.takerPubHome != null && tapeOnPick(r) < 0.5),
  'TAPE: model pick when taker $ agrees with it': G.filter(r => r.pickOdds != null && r.takerPubHome != null && tapeOnPick(r) >= 0.5),
  'TAPE: ride the team with more taker $': G.filter(r => r.takerPubHome != null && r.oppOdds != null && r.pickOdds != null).map(r => tapeOnPick(r) >= 0.5 ? r : { ...r, pickOdds: r.oppOdds, pickHit: 1 - r.pickHit }),
  'TAPE: fade the team with more taker $': G.filter(r => r.takerPubHome != null && r.oppOdds != null && r.pickOdds != null).map(r => tapeOnPick(r) < 0.5 ? r : { ...r, pickOdds: r.oppOdds, pickHit: 1 - r.pickHit }),
  'Public side (bet the team with more Kalshi $)': G.filter(r => r.pubHome != null && r.oppOdds != null).map(r => pubOnPick(r) >= 0.5 ? r : { ...r, pickOdds: r.oppOdds, pickHit: 1 - r.pickHit }),
  'Fade the public side': G.filter(r => r.pubHome != null && r.oppOdds != null).map(r => pubOnPick(r) < 0.5 ? r : { ...r, pickOdds: r.oppOdds, pickHit: 1 - r.pickHit }),
  'Model favorite that is ALSO the Robinhood favorite': G.filter(r => r.pickOdds != null && isMarketFav(r)),
  'Model favorite priced as the underdog (+ odds)': G.filter(r => r.pickOdds != null && !isMarketFav(r)),
  'Model pick, edge ≥ 2 at Robinhood': G.filter(r => r.edge != null && r.edge >= 2),
  'Model pick, every game with a Robinhood price': G.filter(r => r.pickOdds != null),
  'Fade the public (65%+ of Kalshi $ on the other side)': G.filter(r => r.pubHome != null && r.pickOdds != null && ((r.pick === 'home' ? 1 - r.pubHome : r.pubHome) >= .65)),
  'Ride the public (65%+ of Kalshi $ on the pick)': G.filter(r => r.pubHome != null && r.pickOdds != null && ((r.pick === 'home' ? r.pubHome : 1 - r.pubHome) >= .65)),
};
let sh = '';
for (const [name, b] of Object.entries(strat)) { const w = b.filter(r => r.pickHit).length, pnl = b.reduce((s, r) => s + pay(r.pickOdds, r.pickHit), 0); sh += `<tr><td class="nm">${name}</td><td class="num">${b.length}</td><td class="num">${w}-${b.length - w}</td><td class="num ${pnl >= 0 ? 'pos' : 'neg'}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(1)}u</td></tr>`; }
$('#score').innerHTML = `<div class="kpi"><div>graded games<b>${G.length}</b></div><div>model Brier<b>${bm == null ? '—' : bm.toFixed(4)}</b></div><div>Kalshi Brier<b>${bk == null ? '—' : bk.toFixed(4)}</b></div><div>Pinnacle Brier<b>${bs == null ? '—' : bs.toFixed(4)}</b></div></div>
  <div class="wrap"><table><thead><tr><th>Strategy (flat 1u at Robinhood)</th><th>Bets</th><th>Record</th><th>Units</th></tr></thead><tbody>${sh}</tbody></table></div>
  <p class="note">Brier: lower is better, 0.25 is a coin flip. Who's closest to the truth, the model, the Kalshi crowd, or the sharpest book? Public $ = share of Kalshi/Robinhood dollars on that side before kickoff.</p>`;
render();
"""

def page():
    sub = f"moneyline · model win% vs Robinhood (Kalshi) vs Pinnacle · public money split · built {datetime.datetime.now().isoformat(timespec='minutes')}"
    return f"""{head('Fade The Chalk', sub)}
<div class="tabs"><div class="tab on" data-t="mlb">MLB {today or ''}</div><div class="tab" data-t="nfl">NFL {week.replace('_', ' ') if week else ''}</div></div>
<div class="panel">
<div class="kpi" id="kpi"></div>
<div class="ctl"><label><input type="checkbox" id="onlyplays"> hide PASS</label><label><input type="checkbox" id="hidedone"> hide finished</label></div>
<div class="wrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
<div class="legend"><b>Pick</b> = the side the model likes against Robinhood's price. <b>Model</b> = win chance for that side. <b>Robinhood</b> = what a $1 contract on that side costs right now (the ask), with the equivalent American odds; Robinhood's contracts are Kalshi's. <b>Edge</b> = model minus that price, in points; your fee is about a penny a contract, so +2 is real.
<b>Public $ on pick</b> = share of the Kalshi/Robinhood dollars on the pick side: over 65% is a crowded side. <b>$ traded</b> = total on the game. <b>Tape $ on pick</b> = directional money from Kalshi's pre-game trade tape: every trade credited to the team the aggressor bet on (YES on a team, or NO on its opponent); hover for the dollars. <b>Tape $</b> = total taker dollars before start. Unlike Public $ on pick, which counts both sides of each market's volume, this one says which team the money actually backed.
<b>Book take</b> = once a game is final, the losing side's share of the Kalshi/Robinhood money on it (what the winners took from the losers); the tile sums it for the slate. <b>Units</b> = flat 1u on every model pick at Robinhood's price. <b>Book gave</b> = the winning side's share, the money the public got paid on. <b>Pinnacle</b> = the sharpest book's de-vigged chance (a ~ means Pinnacle hasn't posted yet, so it's the Bovada/BetOnline average until it does).<br>
There are three different "favorites" on every game and they do not agree: the side the <b>model</b> has over 50%, the side <b>Robinhood</b> prices over 50¢, and the side the <b>public's money</b> is on. Only the first one predicts anything. Weekend 1, 28 graded games at Robinhood prices: model's side over 50% went 9-5 (+1.3u); the market's priced favorite went 7-5 but <i>lost</i> 1.0u (short prices); the public's side went 8-8 and lost 2.0u.<br>
The <b>Pick</b> is always the model's favorite, its side over 50%. <b>STRONG BET</b> = the public's money is on the other team, so you're buying the model's favorite at a discount (this was the profitable combination). <b>BET</b> = the public already agrees; right side, crowd's price. <b>PASS (priced in)</b> = Robinhood charges 3+ points more than the model's number; no value on either side. Ignore what Robinhood or the crowd calls the favorite; bet the model's side, preferably when the crowd isn't there.
MLB model: regressed run-differential strength, starting-pitcher runs-allowed adjustment, home field. NFL model: last season's point differential (regressed) plus 2 points for home; weak until 2026 games exist, so lean on Pinnacle vs Kalshi there.</div>
<h2>Scorecard <small>every locked, finished game</small></h2><div id="score"></div>
</div>
<script>const BOARDS = {jd(boards)}; const TODAY = {jd(today)}; const WEEK = {jd(week)}; const GRADED = {jd([{k: r.get(k) for k in ('model', 'kalshi', 'sharpHome', 'homeWin', 'edge', 'pickOdds', 'oppOdds', 'pickHit', 'pick', 'pubHome', 'pickProb', 'takerPubHome')} for r in graded])};{JS}</script>"""

open(os.path.join(SITE, 'ml.html'), 'w', encoding='utf-8', newline='\n').write(page())

# ---------------- archive.html: every day / week, every board, one-line scorecards ----------------
def _hr_summary(tag, sport):
    lock = os.path.join(BT, ('pred_' if sport == 'MLB' else 'nfl_') + tag + '.json'); rp = os.path.join(BT, ('res_' if sport == 'MLB' else 'nflres_') + tag + '.json')
    if not os.path.exists(lock): return None
    rows = J(lock); res = J(rp) if os.path.exists(rp) else {}; gg = set(res.get('_games', []))
    g = []
    for r in rows:
        if sport == 'MLB':
            if r.get('gamePk') not in gg: continue
            x = res.get(str(r['id']))
            if x and x['pa'] > 0: g.append((r['prob'], 1 if x['hr'] > 0 else 0))
        else:
            if r.get('eventId') not in gg: continue
            x = res.get(str(r['id'])); g.append((r['prob'], 1 if x and x['td'] > 0 else 0))
    if not g: return {'n': len(rows), 'graded': 0}
    top = sorted(g, key=lambda t: -t[0])[:5]
    return {'n': len(rows), 'graded': len(g), 'exp': sum(p for p, _ in g), 'act': sum(y for _, y in g), 'top5': sum(y for _, y in top)}
def _ml_summary(tag):
    rows = boards.get(tag, []); g = [r for r in rows if r.get('pickHit') is not None]
    return {'n': len(rows), 'graded': len(g), 'w': sum(r['pickHit'] for r in g), 'exp': sum(r['pickProb'] for r in g)}
def _row(label, href, hr, ml, what):
    hrc = '—' if not hr else (f"{hr['graded']} graded · model {hr['exp']:.1f} / actual {hr['act']} · top-5 {hr['top5']}/5" if hr['graded'] else f"{hr['n']} locked, waiting on results")
    mlc = '—' if not ml else (f"{ml['w']}-{ml['graded'] - ml['w']} picks (expected {ml['exp']:.1f})" if ml['graded'] else f"{ml['n']} locked")
    return f'<tr><td><a href="{href}">{label}</a></td><td class="tm">{what}</td><td class="tm">{hrc}</td><td class="tm">{mlc}</td></tr>'
mlb_tags = sorted({os.path.basename(f)[5:15] for f in glob.glob(os.path.join(BT, 'pred_*.json'))} | {t for t in boards if '_wk' not in t}, reverse=True)
nfl_tags = sorted({os.path.basename(f)[4:-5] for f in glob.glob(os.path.join(BT, 'nfl_*.json'))} | {t for t in boards if '_wk' in t}, reverse=True)
arch = head('Fade The Chalk', 'archive · every locked day and week, both boards, kept forever').replace('href="ml.html" class="on"', 'href="ml.html"').replace('href="archive.html"', 'href="archive.html" class="on"')
arch += '<div class="panel top"><h2>NFL weeks <small>touchdowns page · moneylines tab</small></h2><div class="wrap"><table><thead><tr><th>Week</th><th></th><th>Anytime TD</th><th>Moneyline</th></tr></thead><tbody>'
for t in nfl_tags: arch += _row(t.replace('_', ' '), f'nfl/{t}.html', _hr_summary(t, 'NFL'), _ml_summary(t), 'TD board → nfl page · ML → Moneyline, pick the week')
arch += '</tbody></table></div><h2>MLB days <small>home runs page · moneylines tab</small></h2><div class="wrap"><table><thead><tr><th>Day</th><th></th><th>Home runs</th><th>Moneyline</th></tr></thead><tbody>'
for t in mlb_tags: arch += _row(t, f'days/{t}.html', _hr_summary(t, 'MLB'), _ml_summary(t), 'HR board → day page · ML → Moneyline, pick the day')
arch += '</tbody></table></div><p class="note">Every day and week lives as files in the repo (backtest/), so nothing here expires. Picks are locked before first pitch / kickoff and graded from box scores afterward; results never change a lock.</p></div>'
open(os.path.join(SITE, 'archive.html'), 'w', encoding='utf-8', newline='\n').write(arch)
print(f"archive.html: {len(nfl_tags)} NFL weeks, {len(mlb_tags)} MLB days")
print(f"ml.html: {len(mlb_days)} MLB days, {len(nfl_weeks)} NFL weeks, {len(graded)} graded games")
